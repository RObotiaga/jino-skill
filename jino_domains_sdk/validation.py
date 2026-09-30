"""Shared validation for Jino names and DNS fields."""
from __future__ import annotations
import ipaddress
import re

RECORD_FIELDS = {
    "A": ("ip",), "AAAA": ("ip",), "CNAME": ("cname",),
    "MX": ("mx", "priority"), "TXT": ("txt",), "NS": ("ns",),
    "SRV": ("service", "priority", "weight", "port", "target"),
    "CAA": ("flags", "tag", "caa"), "SPF": ("spf",),
    "SSHFP": ("algorithm", "hashType", "fingerprint"),
    "NAPTR": ("order", "preference", "flags", "service", "regexp", "replacement"),
}

def normalize_domain(domain: str) -> str:
    value = domain.strip().removesuffix(".")
    try:
        name = value.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("domain must be a valid IDNA name") from exc
    labels = name.split(".")
    if len(name) > 253 or len(labels) < 2 or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels
    ):
        raise ValueError("domain must be a bare domain, without URL, port or spaces")
    try:
        ipaddress.ip_address(name)
    except ValueError:
        return name
    raise ValueError("domain must not be an IP address")

def normalize_record_name(value: str, domain: str | None = None) -> str:
    name = value.strip().removesuffix(".")
    if name == "@":
        return ""
    if domain:
        if name.lower() == domain:
            return ""
        if name.lower().endswith("." + domain):
            name = name[:-(len(domain) + 1)]
    if not name:
        return ""
    labels = []
    for index, label in enumerate(name.split(".")):
        if label == "*" and index == 0:
            labels.append(label)
            continue
        try:
            item = label.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValueError("invalid DNS record name") from exc
        if not re.fullmatch(r"[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?", item):
            raise ValueError("invalid DNS record name")
        labels.append(item)
    result = ".".join(labels)
    if len(result) + (len(domain) + 1 if domain else 0) > 253:
        raise ValueError("DNS record name is too long")
    return result

def record_id(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 2147483647:
        raise ValueError("record ID must be a positive GraphQL integer")
    return value

def record_type(value: str) -> str:
    kind = value.upper().strip().removeprefix("IN ").strip()
    if kind not in RECORD_FIELDS:
        raise ValueError("unsupported DNS record type")
    return kind

def infer_record_name(record: dict, domain: str) -> str:
    for key in ("subdomainDisplay", "domain"):
        value = record.get(key)
        if isinstance(value, str):
            return normalize_record_name(value, domain)
    raise ValueError("record has no usable name; supply subdomain explicitly")

def validate_fields(kind: str, fields: dict) -> dict:
    unknown = set(fields) - set(RECORD_FIELDS[kind])
    if unknown:
        raise ValueError("unexpected record fields: " + ",".join(sorted(unknown)))
    values = {key: value for key, value in fields.items() if value is not None}
    required = {"A": "ip", "AAAA": "ip", "CNAME": "cname", "MX": "mx",
                "TXT": "txt", "NS": "ns", "SPF": "spf"}.get(kind)
    if required and required not in values:
        raise ValueError("missing required field: " + required)
    if kind in {"A", "AAAA"}:
        address = ipaddress.ip_address(str(values["ip"]).strip())
        if address.version != (4 if kind == "A" else 6):
            raise ValueError("IP address family does not match the record type")
        # Validate without rewriting the spelling submitted by the browser form.
        values["ip"] = str(values["ip"]).strip()
    numeric = {"priority", "weight", "port", "algorithm", "hashType", "order", "preference"}
    if kind == "CAA":
        numeric.add("flags")
    for key in numeric & values.keys():
        value = values[key]
        if isinstance(value, bool) or not (isinstance(value, int) or
                isinstance(value, str) and re.fullmatch(r"[0-9]+", value)):
            raise ValueError(key + " must be an integer")
        maximum = 255 if key in {"flags", "algorithm", "hashType"} else 65535
        if not 0 <= int(value) <= maximum:
            raise ValueError(key + " is out of range")
        values[key] = int(value)
    if kind == "NAPTR" and "flags" in values and not isinstance(values["flags"], str):
        raise ValueError("NAPTR flags must be text")
    return values
