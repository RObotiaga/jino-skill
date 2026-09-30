"""Compact command line interface. All network operations use the HTTP SDK."""
from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import os
import sys
from pathlib import Path

import httpx

from .client import JinoClient, _copy_record_fields
from . import credentials
from .operations import UPDATE_RECORD
from .exceptions import AuthenticationError, JinoError, NotFoundError, PartialUpdateError, OperationRejectedError
from .responses import check_legacy
from .validation import RECORD_FIELDS, infer_record_name, normalize_domain, normalize_record_name
from .validation import record_id, record_type, validate_fields

VERSION = "0.2.1"


class CommandError(Exception):
    def __init__(self, code, message, *, exit_code=2, **details):
        super().__init__(message)
        self.code, self.exit_code, self.details = code, exit_code, details


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's message can contain supplied secrets or arbitrary file contents.
        raise CommandError("USAGE", "Invalid command arguments; use --help for this command.")


def parser():
    root = Parser(prog="jino", description="Jino direct HTTP CLI; compact JSON by default.")
    root.add_argument("--version", action="version", version=VERSION)
    root.add_argument("--pretty", action="store_true", help="indent JSON (place before command)")
    root.add_argument("--timeout", type=float, default=30, help="HTTP timeout seconds")
    groups = root.add_subparsers(dest="group", required=True)
    groups.add_parser("status", help="local configuration and evidence; no network")

    def group(name):
        return groups.add_parser(name).add_subparsers(dest="action", required=True)

    def command(subs, name, *, domain=True, write=False, listing=False):
        item = subs.add_parser(name)
        if domain:
            item.add_argument("domain", type=normalize_domain)
        if write:
            item.add_argument("--apply", action="store_true", help="execute; default only returns a plan")
        if listing:
            item.add_argument("--limit", type=int, default=20)
            item.add_argument("--offset", type=int, default=0)
        if not write:
            item.add_argument("--full", action="store_true", help="return full read result")
        return item

    auth = group("auth")
    command(auth, "configure", domain=False)
    command(auth, "clear", domain=False)
    check = command(auth, "check", domain=False)
    check.add_argument("--domain", type=normalize_domain)
    domains = group("domains")
    item = command(domains, "list", domain=False, listing=True)
    item.add_argument("--filter", default="", help="substring of domain name")
    item = command(domains, "add", write=True)
    item.add_argument("--send-email", action="store_true")
    domain = group("domain")
    for action in ("show", "renewal", "nameservers"):
        command(domain, action)

    dns = group("dns")
    item = command(dns, "list", listing=True)
    item.add_argument("--type", type=record_type)
    item.add_argument("--name", type=str)
    for action in ("add", "update", "ip", "delete", "reset"):
        item = command(dns, action, write=True)
        if action in ("update", "ip", "delete"):
            item.add_argument("--record-id", type=int, required=True)
            item.add_argument("--expected-value", help="abort if current display value/IP differs")
        if action in ("add", "update"):
            item.add_argument("--type", type=record_type, required=action == "add")
            item.add_argument("--name", help="relative name or @; omitted update preserves name")
            for field in sorted({f for fields in RECORD_FIELDS.values() for f in fields}):
                flag = "--hash-type" if field == "hashType" else "--" + field
                item.add_argument(flag, dest=field)
        if action == "ip":
            item.add_argument("--ip", required=True)
        if action == "reset":
            item.add_argument("--confirm-domain", type=normalize_domain,
                              help="must match domain for --apply")

    settings = group("settings")
    command(settings, "get")
    item = command(settings, "set", write=True)
    item.add_argument("--www-mode")
    item.add_argument("--ipv6", choices=("on", "off"))
    item.add_argument("--nameserver", action="append", type=normalize_domain)
    contacts = group("contacts")
    command(contacts, "get")
    item = command(contacts, "update", write=True)
    item.add_argument("--type", required=True, dest="contact_type")
    item.add_argument("--file", required=True, type=Path)
    ssl = group("ssl")
    command(ssl, "get")
    item = command(ssl, "request", write=True)
    item.add_argument("--wildcard", action="store_true")
    command(ssl, "delete", write=True)
    item = command(ssl, "upload", write=True)
    item.add_argument("--cert-file", required=True, type=Path)
    item.add_argument("--key-file", required=True, type=Path)
    item.add_argument("--subdomain", action="append")
    item.add_argument("--password-env", help="environment variable containing key password")
    https = group("https")
    item = command(https, "set", write=True)
    item.add_argument("--enabled", required=True, choices=("on", "off"))
    subdomain = group("subdomain")
    item = command(subdomain, "add", write=True)
    item.add_argument("--name", required=True)
    return root


def page(rows, args):
    if not 1 <= args.limit <= 200 or args.offset < 0:
        raise ValueError("limit must be 1..200 and offset must be nonnegative")
    end = args.offset + args.limit
    return {"total": len(rows), "items": rows[args.offset:end],
            "next_offset": end if end < len(rows) else None}


def select(row, keys):
    return {key: row[key] for key in keys if key in row}


def safe_read(value):
    """Defense in depth for upstream responses; never output key/token fields."""
    if isinstance(value, dict):
        return {key: safe_read(item) for key, item in value.items()
                if not any(word in key.lower().replace("_", "")
                           for word in ("password", "privatekey", "token", "cookie", "secret"))}
    if isinstance(value, list):
        return [safe_read(item) for item in value]
    return value


def value_of(row):
    return (row.get("details") or {}).get("ip", row.get("value"))


def compact_record(row, domain):
    return {"id": row.get("id"), "type": row.get("type"),
            "name": infer_record_name(row, domain), "value": value_of(row),
            "changeable": not bool(row.get("unchangeable"))}


def unverified(action, domain):
    raise CommandError("RESULT_UNVERIFIED", "Request completed; the resulting state is not confirmed.",
                       exit_code=6, action=action, domain=domain, outcome="unverified",
                       next_action="Read current state before deciding whether to retry.")


async def dns_write(client, args):
    domain, action = args.domain, args.action
    zone = await client.list_dns_records(domain)
    if zone.get("changeable") is not True:
        raise CommandError("NOT_CHANGEABLE", "Jino does not allow changing this DNS zone.", exit_code=4)
    before = None
    if action in ("update", "ip", "delete"):
        identifier = record_id(args.record_id)
        matches = [row for row in zone["records"] if row.get("id") == identifier]
        if len(matches) != 1:
            raise NotFoundError("Record not found in the specified domain.")
        before = matches[0]
        if before.get("unchangeable"):
            raise CommandError("NOT_CHANGEABLE", "Jino protects this DNS record.", exit_code=4)
        if args.expected_value is not None and str(value_of(before)) != args.expected_value:
            raise CommandError("PRECONDITION_FAILED", "Record value changed; read it again.", exit_code=4)
    fields, name, kind = {}, None, None
    if action in ("add", "update", "ip"):
        kind = record_type(before["type"]) if before else args.type
        if getattr(args, "type", None) and args.type != kind:
            raise ValueError("type differs from the current record")
        if action == "ip" and kind not in {"A", "AAAA"}:
            raise ValueError("dns ip requires an A or AAAA record")
        if action in {"update", "ip"} and kind not in UPDATE_RECORD:
            raise ValueError("the frontend does not expose update for this record type")
        fields = {field: getattr(args, field) for field in
                  {f for names in RECORD_FIELDS.values() for f in names}
                  if getattr(args, field, None) is not None}
        fields = validate_fields(kind, fields)
        # The read query has no structured fields for these types. Requiring all
        # form fields on edit avoids silently clearing omitted nullable fields.
        if action == "update" and kind not in {"A", "AAAA", "CNAME", "TXT", "NS", "SPF"}:
            if set(fields) != set(RECORD_FIELDS[kind]):
                raise ValueError("complex record update requires all type-specific fields")
        if kind in {"SRV", "CAA", "SSHFP", "NAPTR"} and set(fields) != set(RECORD_FIELDS[kind]):
            raise ValueError("supply all fields for this record type")
        requested = getattr(args, "name", None)
        if kind == "SRV" and requested is not None:
            raise ValueError("SRV uses --service instead of --name")
        name = normalize_record_name(requested, domain) if requested is not None else (
            infer_record_name(before, domain) if before else "")
        # Validate browser transformations (including Latin-1 btoa) before plan.
        wire = {}
        _copy_record_fields(wire, kind, fields)
    plan = {"outcome": "planned", "action": "dns." + action, "domain": domain}
    if before:
        plan["before"] = compact_record(before, domain)
    if kind:
        plan["after"] = {"type": kind, "name": name, **fields}
    if action == "reset":
        plan["replaces_entire_zone"] = True
        if args.apply and args.confirm_domain != domain:
            raise ValueError("--confirm-domain must match the domain for reset")
    if not args.apply:
        return plan
    if action == "add":
        result = await client.create_dns_record(domain, kind, subdomain=name, **fields)
    elif action in ("update", "ip"):
        result = await client.update_dns_record(domain, args.record_id, kind, subdomain=name, **fields)
    elif action == "delete":
        result = await client.delete_dns_record(domain, args.record_id)
    else:
        result = await client.reset_dns_zone(domain, confirm=True)
    check_legacy(result)
    after = await client.list_dns_records(domain)
    if action == "delete":
        verified = all(row.get("id") != args.record_id for row in after["records"])
    elif kind in {"A", "AAAA"}:
        old_ids = {row.get("id") for row in zone["records"]}
        candidates = [row for row in after["records"] if
                      (row.get("id") == args.record_id if before else row.get("id") not in old_ids)]
        verified = any(record_type(row["type"]) == kind and
                       infer_record_name(row, domain) == name and
                       ipaddress.ip_address(value_of(row)) == ipaddress.ip_address(fields["ip"])
                       for row in candidates)
    else:
        # Display strings for complex records cannot reliably prove all fields.
        verified = False
    if not verified:
        unverified("dns." + action, domain)
    return {**plan, "outcome": "applied", "verification": "read_back"}


async def dispatch(client, args):
    g, a, d = args.group, getattr(args, "action", None), getattr(args, "domain", None)
    if g == "auth":
        await client.login(d)
        return {"authenticated": True, "http_version": client.last_http_version}
    if g == "domains" and a == "list":
        rows = await client.list_domains()
        rows = [row for row in rows if args.filter.lower() in row.get("domain", "").lower()]
        if not args.full:
            rows = [select(row, ("domain", "canBeManaged", "hasDnsZone", "expireDate")) for row in rows]
        return page(rows, args)
    if g == "dns" and a == "list":
        zone = await client.list_dns_records(d)
        rows = zone["records"]
        if args.type:
            rows = [row for row in rows if record_type(row["type"]) == args.type]
        if args.name is not None:
            wanted = normalize_record_name(args.name, d)
            rows = [row for row in rows if infer_record_name(row, d) == wanted]
        if not args.full:
            rows = [compact_record(row, d) for row in rows]
        return {"domain": d, "changeable": zone.get("changeable"), **page(rows, args)}
    if g == "dns":
        return await dns_write(client, args)
    if g == "domain":
        method = {"show": client.get_domain_settings, "renewal": client.get_domain_renewal_info,
                  "nameservers": client.get_nameservers}[a]
        return await method(d)
    if g == "settings" and a == "get":
        return await client.get_domain_settings(d)
    if g == "ssl" and a == "get":
        return await client.get_ssl(d)
    if g == "contacts" and a == "get":
        result = await client.get_contacts(d)
        if args.full:
            return result
        return {"groups": list(result) if isinstance(result, dict) else [],
                "details_omitted": True, "hint": "Use --full only when contact fields are needed."}

    plan = {"outcome": "planned", "action": g + "." + a, "domain": d}
    if g == "settings":
        kwargs = {"www_mode": args.www_mode,
                  "ipv6_enabled": None if args.ipv6 is None else args.ipv6 == "on",
                  "nameservers": args.nameserver}
        kwargs = {key: value for key, value in kwargs.items() if value is not None}
        if not kwargs:
            raise ValueError("specify at least one setting")
        if args.www_mode is not None and not args.www_mode.strip():
            raise ValueError("www mode must not be empty")
        if args.nameserver and len(set(args.nameserver)) != len(args.nameserver):
            raise ValueError("nameservers must be distinct")
        plan["changes"] = kwargs
        plan["before"] = await client.get_domain_settings(d)
        if args.nameserver:
            ns = await client.get_nameservers(d)
            if ns.get("changeable") is not True:
                raise CommandError("NOT_CHANGEABLE", "Jino does not allow changing nameservers.", exit_code=4)
        call = lambda: client.save_domain_settings(d, **kwargs)
    elif g == "domains":
        plan["send_email"] = args.send_email
        call = lambda: client.add_existing_domain(d, send_email=args.send_email)
    elif g == "contacts":
        content = read_file(args.file)
        try:
            data = json.loads(content)
        except ValueError as exc:
            raise ValueError("contact file must contain valid JSON") from exc
        if not isinstance(data, dict) or not data:
            raise ValueError("contact file must contain a nonempty object")
        plan["contact_type"] = args.contact_type
        plan["fields"] = list(data)
        call = lambda: client.update_contact(d, args.contact_type, data)
    elif g == "ssl":
        plan["before"] = await client.get_ssl(d)
        if a == "request":
            plan["wildcard"] = args.wildcard
            call = lambda: client.request_ssl(d, wildcard=args.wildcard)
        elif a == "delete":
            call = lambda: client.delete_ssl_certificate(d)
        else:
            cert, key = read_file(args.cert_file), read_file(args.key_file)
            if "-----BEGIN CERTIFICATE-----" not in cert or "PRIVATE KEY-----" not in key:
                raise ValueError("certificate and private key must be PEM files")
            password = os.environ.get(args.password_env) if args.password_env else None
            if args.password_env and not password:
                raise ValueError("key password environment variable is not set")
            plan["certificate_from_file"] = True
            call = lambda: client.upload_ssl_certificate(d, certificate=cert, private_key=key,
                                                         subdomains=args.subdomain, password=password)
    elif g == "https":
        plan["enabled"] = args.enabled == "on"
        call = lambda: client.set_force_https(d, plan["enabled"])
    elif g == "subdomain":
        label = normalize_record_name(args.name, d)
        if not label or "." in label or label == "*":
            raise ValueError("subdomain requires a single non-wildcard label")
        child = normalize_domain(label + "." + d)
        plan["subdomain"] = child
        call = lambda: client.add_subdomain(d, label)
    else:
        raise ValueError("unsupported command")
    if not args.apply:
        return plan
    result = await call()
    check_legacy(result)
    # Only a matching independent read can prove that a mutation took effect.
    if g in {"domains", "subdomain", "https"}:
        rows = await client.list_domains()
        wanted = plan.get("subdomain", d)
        matching = [row for row in rows if row.get("domain") == wanted]
        if matching and (g != "https" or matching[0].get("forceHttps") is plan["enabled"]):
            return {**plan, "outcome": "applied", "verification": "read_back"}
    if g == "settings":
        current = await client.get_domain_settings(d)
        verified = []
        if "www_mode" in kwargs:
            verified.append(current.get("www_mode") == kwargs["www_mode"])
        if "ipv6_enabled" in kwargs:
            rows = await client.list_domains()
            verified.append(any(row.get("domain") == d and
                                row.get("ipv6Enabled") is kwargs["ipv6_enabled"] for row in rows))
        if "nameservers" in kwargs:
            ns = await client.get_nameservers(d)
            verified.append({str(item).lower().rstrip(".") for item in ns["nameservers"]} ==
                            set(kwargs["nameservers"]))
        if verified and all(verified):
            return {**plan, "outcome": "applied", "verification": "read_back"}
    unverified(g + "." + a, d)


def read_file(path):
    if path.stat().st_size > 1_000_000:
        raise ValueError("input file exceeds 1 MB")
    return path.read_text(encoding="utf-8-sig")


async def run(args):
    if args.timeout <= 0 or args.timeout > 300:
        raise ValueError("timeout must be 0..300 seconds")
    configured = credentials.configured()
    if args.group == "status":
        return {"version": VERSION, "credentials_configured": configured,
                "transport": "direct_http", "browser_required": False,
                "live_login_verified": True, "live_reads_verified": True,
                "live_mutations_verified": False}
    if args.group == "auth" and args.action == "configure":
        if not sys.stdin.isatty():
            raise CommandError("INTERACTIVE_REQUIRED", "Run auth configure yourself in an interactive terminal.")
        from getpass import getpass
        login = input("Jino login: ")
        password = getpass("Jino password: ")
        credentials.save(login, password)
        return {"credentials_configured": True, "storage": "windows_user_dpapi",
                "authentication_checked": False}
    if args.group == "auth" and args.action == "clear":
        credentials.profile_path().unlink(missing_ok=True)
        return {"stored_profile_removed": True, "environment_variables_unchanged": True}
    if not configured:
        raise AuthenticationError("Run auth configure locally, or set JINO_LOGIN and JINO_PASSWORD.")
    login, password = credentials.load()
    async with JinoClient(login, password, timeout=args.timeout) as client:
        return await dispatch(client, args)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = None
    exit_code = 0
    try:
        args = parser().parse_args(argv)
        result = {"ok": True, "data": safe_read(asyncio.run(run(args)))}
    except CommandError as exc:
        exit_code = exc.exit_code
        result = {"ok": False, "error": {"code": exc.code, "message": str(exc), **exc.details}}
    except PartialUpdateError as exc:
        exit_code = 6
        result = {"ok": False, "error": {"code": exc.code, "message": str(exc),
                  "steps": exc.steps, "next_action": "Read settings before retrying."}}
    except AuthenticationError as exc:
        exit_code = 3
        result = {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
    except OperationRejectedError as exc:
        exit_code = 5
        result = {"ok": False, "error": {"code": exc.code, "message": str(exc),
                  "next_action": "Read current state before retrying a write."}}
    except (ValueError, OSError) as exc:
        exit_code = 2
        # Do not print exception text: it may contain raw values or file data.
        result = {"ok": False, "error": {"code": "INVALID_INPUT", "message":
                  "Invalid input or unreadable file; check command help and input fields."}}
    except (httpx.HTTPError, JinoError) as exc:
        writing = bool(args and getattr(args, "apply", False))
        exit_code = 6 if writing else (4 if isinstance(exc, NotFoundError) else 5)
        result = {"ok": False, "error": {"code": "WRITE_RESULT_UNKNOWN" if writing else
                  getattr(exc, "code", "NETWORK_ERROR"), "message":
                  "Read current state before retrying this write." if writing else "Jino request failed."}}
    except KeyboardInterrupt:
        exit_code = 130
        result = {"ok": False, "error": {"code": "INTERRUPTED", "message":
                  "Interrupted; read current state before retrying any write."}}
    except Exception:
        exit_code = 6 if args and getattr(args, "apply", False) else 5
        result = {"ok": False, "error": {"code": "UNEXPECTED_RESPONSE", "message":
                  "Unexpected response; read current state before retrying any write."}}
    sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":"),
                               indent=2 if args and args.pretty else None) + "\n")
    return exit_code
