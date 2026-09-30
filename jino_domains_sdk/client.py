"""High-level async API for Jino domain settings and DNS records."""

from __future__ import annotations

import base64
import asyncio
import json
import os

from . import operations as op
from .exceptions import AuthenticationError, JinoGraphQLError, NotFoundError, PartialUpdateError, ProtocolError
from .transport import JinoHTTPTransport
from .responses import check_legacy
from .validation import normalize_domain, normalize_record_name, infer_record_name, record_id as valid_record_id
from .validation import record_type as valid_record_type, RECORD_FIELDS, validate_fields


def _domain_id(domain: str) -> str:
    raw = f"UserDomain:{normalize_domain(domain)}".encode("ascii")
    return base64.b64encode(raw).decode("ascii")


def _browser_btoa(value: str) -> str:
    """Match ``btoa(value.trim())`` from the Jino frontend."""
    try:
        raw = value.strip().encode("latin-1")
    except UnicodeEncodeError as exc:
        raise ValueError("Jino's browser form only base64-encodes Latin-1 text") from exc
    return base64.b64encode(raw).decode("ascii")


def _unwrap(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ProtocolError("GraphQL response must be an object.")
    errors = payload.get("errors")
    if errors:
        raise JinoGraphQLError(errors)
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ProtocolError("GraphQL response has no data object.")
    return data


class JinoClient:
    """Async Jino SDK client.

    Args:
        login: Jino login, e-mail, phone number, or account domain.
        password: Jino account password. Held only in process memory.
        timeout: Per-request timeout in seconds.
        browser_headers: Optional overrides for captured non-secret headers.
    """

    def __init__(
        self,
        login: str,
        password: str,
        *,
        timeout: float = 30.0,
        browser_headers: dict[str, str] | None = None,
    ) -> None:
        if not login or not password:
            raise ValueError("login and password are required")
        self._operation_lock = asyncio.Lock()
        self._transport = JinoHTTPTransport(
            login,
            password,
            timeout=timeout,
            browser_headers=browser_headers,
        )

    @classmethod
    def from_env(cls, **kwargs) -> "JinoClient":
        """Create a client from ``JINO_LOGIN`` and ``JINO_PASSWORD``."""
        login = os.environ.get("JINO_LOGIN")
        password = os.environ.get("JINO_PASSWORD")
        if not login or not password:
            raise ValueError("set JINO_LOGIN and JINO_PASSWORD environment variables")
        return cls(login, password, **kwargs)

    async def __aenter__(self) -> "JinoClient":
        await self._transport.start()
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.close()

    async def close(self) -> None:
        """Close HTTP sessions and discard in-memory cookies and tokens."""
        await self._transport.close()

    async def login(self, domain: str | None = None) -> None:
        """Log in with the supplied credentials; later methods also log in lazily."""
        name = normalize_domain(domain) if domain else None
        async with self._operation_lock:
            await self._transport.ensure_page(name, "settings")

    @property
    def last_http_version(self) -> str | None:
        """HTTP version negotiated for the most recent HTTP operation."""
        return self._transport.last_http_version

    async def _query(
        self,
        domain: str | None,
        section: str,
        document: str,
        variables: dict | None,
    ) -> dict:
        name = normalize_domain(domain) if domain else None
        async with self._operation_lock:
            for attempt in range(2):
                try:
                    await self._transport.ensure_page(name, section)
                    return _unwrap(await self._transport.graphql(document, variables))
                except AuthenticationError as exc:
                    if attempt or not exc.recoverable:
                        raise
                    self._transport.invalidate_session()
        raise AuthenticationError("Could not establish the Jino session.")

    async def list_domains(self) -> list[dict]:
        """List domains visible to the authenticated Jino account."""
        data = await self._query(None, "settings", op.DOMAINS_LIST, {})
        edges = data.get("me", {}).get("domain", {}).get("edges", [])
        return [edge.get("node", {}) for edge in edges]

    async def add_existing_domain(self, domain: str, *, send_email: bool = False) -> dict:
        """Add an existing domain to the account; this does not register or buy it.

        Jino may require ownership verification. ``send_email=True`` asks Jino to
        send its verification email.
        """
        name = normalize_domain(domain)
        return await self._query(
            None,
            "settings",
            op.ADD_EXISTING_DOMAIN,
            {"domainName": name, "sendEmail": send_email},
        )

    async def get_domain_settings(self, domain: str) -> dict:
        """Read legacy basic settings for *domain*."""
        name = normalize_domain(domain)
        data = await self._query(name, "settings", op.DOMAIN_INFO, {"domain": name})
        raw = data.get("me", {}).get("legacy", {}).get("domains", {}).get("getDomainInfo")
        return json.loads(raw) if isinstance(raw, str) else (raw or {})

    async def get_domain_renewal_info(self, domain: str) -> dict:
        """Read expiry and renewal metadata; this method does not renew the domain."""
        name = normalize_domain(domain)
        data = await self._query(
            name,
            "settings",
            op.DOMAIN_RENEWAL_INFO,
            {"id": _domain_id(name)},
        )
        return data.get("node") or {}

    async def get_nameservers(self, domain: str) -> dict:
        """Read name servers and whether Jino allows changing them."""
        name = normalize_domain(domain)
        data = await self._query(
            name,
            "settings",
            op.DOMAIN_NS,
            {"id": _domain_id(name)},
        )
        info = (data.get("node") or {}).get("registrarInfo") or {}
        return {"nameservers": info.get("nservers", []), "changeable": info.get("nsChangeable")}

    async def list_dns_records(self, domain: str) -> dict:
        """Return DNS changeability and records for *domain*."""
        name = normalize_domain(domain)
        data = await self._query(
            name,
            "dns",
            op.DNS_RECORDS,
            {"id": _domain_id(name)},
        )
        node = data.get("node")
        if node is None:
            raise NotFoundError("The domain is unavailable to this account.")
        dns = node.get("dns")
        if not isinstance(dns, dict) or not isinstance(dns.get("records"), list):
            raise ProtocolError("Jino returned no DNS records object.")
        return dns

    async def create_dns_record(
        self,
        domain: str,
        record_type: str,
        *,
        subdomain: str = "",
        **fields,
    ) -> dict:
        """Create a DNS record using the corresponding Jino UI mutation.

        Field names are the mutation names: ``ip``, ``cname``, ``mx``, ``priority``,
        ``txt``, ``ns``, ``service``, ``weight``, ``port``, ``target``, ``flags``,
        ``tag``, ``caa``, ``spf``, ``algorithm``, ``hashType``, ``fingerprint``,
        ``order``, ``preference``, ``regexp``, and ``replacement``.
        """
        name = normalize_domain(domain)
        kind = valid_record_type(record_type)
        document = op.ADD_RECORD.get(kind)
        if document is None:
            raise ValueError(f"unsupported DNS record type: {record_type}")
        variables = {"domain": name}
        if kind not in {"SRV"}:
            variables["subdomain"] = normalize_record_name(subdomain, name)
        _copy_record_fields(variables, kind, fields)
        if kind == "SRV" and not variables.get("service"):
            raise ValueError("SRV record requires service")
        return await self._query(name, "dns", document, variables)

    async def update_dns_record(
        self,
        domain: str,
        record_id: int,
        record_type: str,
        *,
        subdomain: str | None = None,
        **fields,
    ) -> dict:
        """Edit a DNS record by its integer record ID and type."""
        name = normalize_domain(domain)
        kind = valid_record_type(record_type)
        document = op.UPDATE_RECORD.get(kind)
        if document is None:
            raise ValueError(f"the Jino UI does not expose update for record type {kind}")
        identifier = valid_record_id(record_id)
        if subdomain is None and kind != "SRV":
            zone = await self.list_dns_records(name)
            matches = [row for row in zone["records"] if row.get("id") == identifier]
            if len(matches) != 1:
                raise NotFoundError("DNS record was not found in the supplied domain.")
            existing = matches[0]
            if valid_record_type(existing["type"]) != kind:
                raise ValueError("record type does not match the existing record")
            if zone.get("changeable") is not True or existing.get("unchangeable"):
                raise ValueError("Jino does not allow changing this record")
            subdomain = infer_record_name(existing, name)
        variables = {"domain": name, "recordId": identifier}
        if kind != "SRV":
            variables["subdomain"] = normalize_record_name(subdomain, name)
        _copy_record_fields(variables, kind, fields)
        return await self._query(name, "dns", document, variables)

    async def create_a_record(self, domain: str, *, ip: str, subdomain: str = "") -> dict:
        """Create an IPv4 A record."""
        return await self.create_dns_record(domain, "A", ip=ip, subdomain=subdomain)

    async def update_a_record(
        self, domain: str, record_id: int, *, ip: str, subdomain: str | None = None
    ) -> dict:
        """Change the IPv4 address of an existing A record."""
        return await self.update_dns_record(
            domain, record_id, "A", ip=ip, subdomain=subdomain
        )

    async def create_aaaa_record(self, domain: str, *, ip: str, subdomain: str = "") -> dict:
        return await self.create_dns_record(domain, "AAAA", ip=ip, subdomain=subdomain)

    async def update_aaaa_record(
        self, domain: str, record_id: int, *, ip: str, subdomain: str | None = None
    ) -> dict:
        return await self.update_dns_record(
            domain, record_id, "AAAA", ip=ip, subdomain=subdomain
        )

    async def create_cname_record(
        self, domain: str, *, cname: str, subdomain: str = ""
    ) -> dict:
        return await self.create_dns_record(
            domain, "CNAME", cname=cname, subdomain=subdomain
        )

    async def create_mx_record(
        self, domain: str, *, mx: str, priority: int | None = None, subdomain: str = ""
    ) -> dict:
        return await self.create_dns_record(
            domain, "MX", mx=mx, priority=priority, subdomain=subdomain
        )

    async def create_txt_record(self, domain: str, *, txt: str, subdomain: str = "") -> dict:
        return await self.create_dns_record(
            domain, "TXT", txt=txt, subdomain=subdomain
        )

    async def delete_dns_record(self, domain: str, record_id: int) -> dict:
        """Delete a DNS record by ID."""
        name = normalize_domain(domain)
        return await self._query(
            name,
            "dns",
            op.DELETE_RECORD,
            {"domain": name, "recordId": valid_record_id(record_id)},
        )

    async def reset_dns_zone(self, domain: str, *, confirm: bool = False) -> dict:
        """Reset the full DNS zone. Requires ``confirm=True``."""
        if not confirm:
            raise ValueError("pass confirm=True to replace the entire DNS zone")
        name = normalize_domain(domain)
        return await self._query(
            name, "dns", op.RESET_ZONE, {"domain": name}
        )

    async def save_domain_settings(
        self,
        domain: str,
        *,
        www_mode: str | None = None,
        ipv6_enabled: bool | None = None,
        nameservers: list[str] | None = None,
    ) -> dict:
        """Save WWW redirect, IPv6, and optionally name servers.

        Calls run sequentially in the same order as the Jino settings form.
        ``www_mode`` is the mode string returned as ``www_mode`` by
        ``get_domain_settings``; consult it before changing the redirect.
        """
        name = normalize_domain(domain)
        steps = []
        if www_mode is not None:
            if not isinstance(www_mode, str) or not www_mode.strip():
                raise ValueError("www_mode must be a nonempty mode returned by Jino")
            steps.append(("www", op.SET_WWW, {"domain": name, "mode": www_mode}))
        if ipv6_enabled is not None:
            if not isinstance(ipv6_enabled, bool):
                raise ValueError("ipv6_enabled must be a boolean")
            action = "enableDomainIPv6" if ipv6_enabled else "disableDomainIPv6"
            steps.append(("ipv6", op.SET_IPV6_TEMPLATE.replace("{action}", action), {"domain": name}))
        if nameservers is not None:
            if not nameservers:
                raise ValueError("nameservers must not be empty")
            servers = [normalize_domain(item) for item in nameservers]
            if len(set(servers)) != len(servers):
                raise ValueError("nameservers must be distinct")
            steps.append(("nameservers", op.UPDATE_NAMESERVERS, {"domain": name, "nservers": servers}))
        results = {}
        for key, document, variables in steps:
            try:
                response = await self._query(name, "settings", document, variables)
                check_legacy(response)
                results[key] = response
            except Exception as exc:
                states = {step[0]: "request_completed" if step[0] in results else "not_attempted" for step in steps}
                states[key] = "failed_or_unknown"
                raise PartialUpdateError(states, exc) from exc
        return results

    async def get_contacts(self, domain: str):
        """Read contact data returned by the Jino contacts page."""
        name = normalize_domain(domain)
        data = await self._query(name, "contacts", op.CONTACTS, {"domain": name})
        raw = data.get("me", {}).get("legacy", {}).get("domains", {}).get("getContacts")
        return json.loads(raw) if isinstance(raw, str) else raw

    async def update_contact(self, domain: str, contact_type: str, data: dict) -> dict:
        """Update one contact group; ``data`` is JSON-encoded as by the Jino UI."""
        name = normalize_domain(domain)
        variables = {
            "domain": name,
            "contactType": contact_type,
            "data": json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        }
        return await self._query(name, "contacts", op.UPDATE_CONTACT, variables)

    async def get_ssl(self, domain: str) -> dict:
        """Read the current certificate and any pending SSL request."""
        name = normalize_domain(domain)
        data = await self._query(
            name,
            "ssl",
            op.SSL_INFO,
            {"id": _domain_id(name)},
        )
        return data.get("node") or {}

    async def request_ssl(self, domain: str, *, wildcard: bool = False) -> dict:
        """Request a Jino SSL certificate."""
        name = normalize_domain(domain)
        return await self._query(
            name,
            "ssl",
            op.REQUEST_SSL,
            {"domain": name, "wildcard": wildcard},
        )

    async def upload_ssl_certificate(
        self,
        domain: str,
        *,
        certificate: str,
        private_key: str,
        subdomains: list[str] | None = None,
        password: str | None = None,
    ) -> dict:
        """Upload a certificate. Certificate/key values are sent in the HTTP request."""
        name = normalize_domain(domain)
        variables = {"domain": name, "crt": certificate.strip(), "key": private_key.strip()}
        if subdomains:
            variables["subs"] = [item.strip() for item in subdomains if item.strip()]
        if password:
            variables["password"] = password
        return await self._query(name, "ssl", op.ADD_SSL_CERT, variables)

    async def set_force_https(self, domain: str, enabled: bool) -> dict:
        """Enable or disable HTTPS redirect."""
        name = normalize_domain(domain)
        action = "enableDomainHTTPSRedirect" if enabled else "disableDomainHTTPSRedirect"
        document = op.SET_FORCE_HTTPS_TEMPLATE.replace("{action}", action)
        return await self._query(name, "ssl", document, {"domain": name})

    async def delete_ssl_certificate(self, domain: str) -> dict:
        """Delete the configured SSL certificate."""
        name = normalize_domain(domain)
        return await self._query(
            name, "ssl", op.DELETE_SSL, {"domain": name}
        )

    async def add_subdomain(self, domain: str, subdomain: str) -> dict:
        """Create a subdomain under *domain* (for example ``api.example.com``)."""
        name = normalize_domain(domain)
        label = subdomain.strip().strip(".")
        if not label or "." in label or "/" in label:
            raise ValueError("subdomain must be a single DNS label")
        child = normalize_domain(f"{label}.{name}")
        data = await self._query(
            name,
            "subdomains",
            op.ADD_SUBDOMAIN,
            {"domainName": child},
        )
        return data


def _copy_record_fields(variables: dict, kind: str, fields: dict) -> None:
    values = validate_fields(kind, fields)
    for field in RECORD_FIELDS[kind]:
        if field not in values:
            continue
        value = values[field]
        if isinstance(value, int):
            variables[field] = value
        elif field in {"txt", "spf", "caa"}:
            variables[field] = _browser_btoa(str(value))
        else:
            variables[field] = str(value).strip()
