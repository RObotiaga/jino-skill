# Jino CLI и Python SDK

Async Python client for domain management through Jino's control panel. It uses direct HTTP via HTTPX; it does not start a browser, use browser automation, or persist cookies or tokens. The optional CLI credential profile uses Windows current-user DPAPI encryption.


## CLI для агента

CLI установлен вместе со skill `jino-control`, в отдельном Python окружении:

```powershell
$jino = Join-Path $env:USERPROFILE '.codex/skills/jino-control/scripts/jino.ps1'
& $jino status
& $jino auth configure  # один раз, вручную в интерактивном терминале
& $jino auth check
& $jino dns list example.com --type A
& $jino dns ip example.com --record-id 123 --ip 203.0.113.42
& $jino dns ip example.com --record-id 123 --ip 203.0.113.42 --apply
```

По умолчанию команды изменения показывают план. `--apply` выполняет действие. Для изменения IP имя и тип записи сохраняются; `--expected-value` позволяет проверить старое значение перед записью. Результаты — компактный JSON; списки по умолчанию ограничены 20 элементами. Доступны `--limit`, `--offset`, фильтры DNS `--type` / `--name`, и `--full` для расширенного чтения. Глобальный `--pretty` ставится перед командой.

Подтверждённая запись возвращает `outcome=applied` и `verification=read_back`. `RESULT_UNVERIFIED` / код 6 означает, что запрос завершился, но изменение не подтверждено автоматически. Прочитайте текущее состояние перед повтором. Полная справка: [docs/CLI.md](CLI.md).

SDK можно установить обычным `py -m pip install .`; это добавит команду `jino`. При установленном skill переустановка его окружения выполняется скриптом `scripts/install.ps1 -Source <папка SDK>`.

## Coverage

- Any domain name as an explicit method argument
- Add an existing domain to the account (does not register or buy a domain)
- DNS listing and create/update/delete for A, AAAA, CNAME, MX, TXT, NS, SRV, CAA, SPF, SSHFP, and NAPTR where the Jino UI exposes that operation
- Basic domain settings, name servers, IPv6, and WWW redirect
- Domain contacts, SSL details/actions, and subdomain creation

The read-only `DnsRecords` request and authenticated GraphQL transport were observed in the signed-in Jino browser. The mutation documents and other page operations were recovered from the site's loaded JavaScript. No live DNS, SSL, contact, or domain setting was changed to validate a write. Login submission has not yet been captured from a live browser request; the current login implementation follows the public Jino HTML form schema and CSRF cookie. The live HTTP login and read-only domain/DNS/settings/nameserver/SSL commands have now been verified with the user's stored credentials; the OIDC redirect through `login.jino.ru` is supported. See [the evidence matrix](evidence.md).

## Install

```powershell
py -m pip install -e .
```

HTTPX's HTTP/2 support is enabled in the SDK. HTTPX documents that `http2=True` negotiates HTTP/2 only when the peer also supports it; the SDK exposes the last negotiated version as `jino.last_http_version`. [HTTPX HTTP/2 documentation](https://www.python-httpx.org/http2/)

The install extra also enables Brotli and Zstandard decoding because those encodings were present in the browser's `Accept-Encoding` header.

## Credentials

The SDK accepts a login and password, and keeps them in process memory only. Prefer environment variables or a secret manager:

```powershell
$env:JINO_LOGIN = "your-login"
$env:JINO_PASSWORD = "your-password"
```

```python
import asyncio

from jino_domains_sdk import JinoClient


async def main():
    async with JinoClient.from_env() as jino:
        await jino.login()  # optional; API calls also authenticate lazily
        records = await jino.list_dns_records("example.com")
        print(records)

        # This changes live DNS when called:
        # await jino.create_a_record("example.com", ip="203.0.113.10")


asyncio.run(main())
```

You can also pass `login=` and `password=` directly to `JinoClient`. The login form POST uses cookies and CSRF values from the current control-panel responses. The implementation stops if Jino requires a CAPTCHA or another challenge.

## Main operations

```python
await jino.list_domains()
await jino.add_existing_domain("example.com")
await jino.list_dns_records(domain)
await jino.create_a_record(domain, ip="203.0.113.10")
await jino.update_a_record(domain, record_id, ip="203.0.113.11")
await jino.delete_dns_record(domain, record_id)
await jino.get_domain_settings(domain)
await jino.save_domain_settings(domain, www_mode="off", ipv6_enabled=True)
await jino.get_contacts(domain)
await jino.get_ssl(domain)
await jino.add_subdomain(domain, "api")
```

See method docstrings in `jino_domains_sdk/client.py` for field names. Read the current `www_mode` with `get_domain_settings()` before choosing a replacement. DNS mutations, SSL changes, contact edits, and settings changes act immediately on the supplied domain.

## Request parity

The client sends direct HTTP requests to the observed endpoints. It uses the Jino GraphQL operation documents, compact JSON body ordering, bearer-token bootstrap, cookies for the control-panel login/token request, captured non-secret Chrome header values (including `Origin`, `Sec-Fetch-*`, `Accept-Encoding`, and `Accept-Language`), and HTTP/2 negotiation where supported. For the observed `DnsRecords` query, the browser method, URL, operation, variables shape, effective headers, and response protocol were captured. The login POST and mutating GraphQL bodies remain inferred from the public form and frontend source.

Direct HTTP does not produce Chrome's TLS fingerprint. The login form POST and mutating GraphQL bodies have not yet been captured as live browser requests, so those are marked inferred/static-source evidence rather than verified parity. The SDK does not claim byte-for-byte identity of the entire TLS session.

## Safety

- SDK credentials, cookies, CSRF values, and bearer tokens are not written to disk or logs. The CLI can explicitly save login/password encrypted with Windows current-user DPAPI; `auth clear` removes that encrypted profile.
- DNS and settings write methods act immediately.
- `reset_dns_zone` requires `confirm=True` because it replaces the full zone.
- Domain deletion, registration, transfer, and paid renewal are not exposed.
