# Jino domain SDK: capture and parity evidence

Capture date: 2026-09-30. The target domain is anonymized as `example.com` in this public report. The account was used only for read-only inspection. No DNS, contact, SSL, nameserver, IPv6, redirect, or domain mutation was sent.

## Sources

- Signed-in control-panel page: `https://cp.jino.ru/domains/example.com/settings`
- DNS page: `https://cp.jino.ru/domains/example.com/dns`
- GraphQL endpoint observed in the page: `https://graphql.jino.ru/user/`
- Access-token endpoint observed in the page: `https://cp.jino.ru/api/auth/access-token`
- Public login form: `https://auth.jino.ru/login/?next=...`
- Frontend bundles inspected from the current page: `DM3HAFH9.js` (DNS), `DOnO3kb3.js` (settings), `k6G1aeCs.js` (contacts), `DDvMFQwB.js` (SSL), `4zBolJQc.js` (domain list/renewal), and `obY2JHxH.js` (subdomains).

## Live browser observations

| Request | Observed evidence | Values retained |
|---|---|---|
| `GET /domains/{domain}/dns` on `cp.jino.ru` | HTTP 200 over HTTP/2; navigation `Accept`, `Accept-Encoding`, `Accept-Language`, Chrome client hints, and `Sec-Fetch-*` captured from `requestWillBeSentExtraInfo` | No cookie value |
| `GET /api/auth/access-token` on `cp.jino.ru` | HTTP 200; JSON contains `accessToken`; request uses current control-panel cookies, `Accept: */*`, same-origin CORS fetch headers, and the current page as `Referer` | No token or cookie value |
| `POST /user/` on `graphql.jino.ru`, `DnsRecords` | HTTP 200 over HTTP/2 (`h2`); JSON body keys are `query` and `variables`; variables contain `id`; response contains DNS records and a `changeable` flag | No record values, record IDs, domain ID, or bearer token |
| `OPTIONS /user/` on `graphql.jino.ru` | Browser CORS preflight observed with `Origin: https://cp.jino.ru`, method `POST`, requested headers `authorization,content-type`, and mode `cors` | No account data |
| Browser request headers on GraphQL | `accept: application/json`, `content-type: application/json`, `Origin: https://cp.jino.ru`, `Referer: https://cp.jino.ru/`, `Accept-Language: ru`, `Accept-Encoding: gzip, deflate, br, zstd`, same-site CORS fetch metadata, Chrome 154 UA and client hints | Authorization and cookie values omitted |
| Browser request headers on access-token GET | `Accept: */*`, current-page `Referer`, same-origin CORS fetch metadata, Chrome 154 UA/client hints, `Accept-Language: ru` | Cookie values omitted |

The inspected browser connection negotiated TLS 1.3 and HTTP/2. `Network.requestWillBeSentExtraInfo` exposed the effective HTTP headers for the read-only page, token, preflight, and GraphQL requests. The capture did not expose a Chrome TLS ClientHello fingerprint or HTTP/2 frame-level bytes.

The `DnsRecords($id: ID!)` document was visible in the DNS page bundle and matched the live operation name and shape. Its captured query text is 453 UTF-8 bytes with SHA-256 `ce3eec40b589ebe1d4500708965e91d18d90e1c3d8a0019293661f51033ba248`; the SDK document has the same length and digest. The browser's domain ID matched the SDK's base64 encoding of `UserDomain:<domain>`; only the match result and length were retained, not the ID.

## Offline SDK request-shape check

The SDK's HTTPX methods were run against in-memory `MockTransport` handlers, with placeholder credentials, token, cookie, and domain ID and no network access. The generated GraphQL request matched the captured browser request on method, URL, 542-byte body length, `query`/`variables` order and keys, exact query digest, and captured effective non-secret headers. It included an authorization header and no cookie header. The page navigation GET, access-token GET, and OPTIONS preflight also matched their captured effective non-secret header values. A separate mock-form run checked the inferred login form action resolution, POST field order, frontend login normalization, CSRF-cookie use, and redirect handling. These checks verify SDK request construction only: neither mock made a request to Jino, and no mutation was run. The initial Python environment lacked the optional `h2` package, so HTTP/2 negotiation was not exercised during that offline check; the package declares `httpx[http2]` for installation.

## Login evidence

An anonymous GET of the public login page returned the `login-form-with-history` form. Its method is `POST`; the form schema names the `login` and `password` fields, and the frontend renders `csrfmiddlewaretoken` from the `csrftoken` cookie. The page also set cookies named `csrftoken`, `jlang`, and `sid`; their values were not retained. The raw form `action` is `/login/`, so the inferred submit endpoint is `https://auth.jino.ru/login/`; the actual submit was not captured.

In that anonymous response, the `csrftoken` cookie value matched the CSRF value rendered for the form; neither value was retained. The public form JavaScript lowercases the login value and removes a leading `+` and trailing whitespace before native form submission. The SDK mirrors that transformation and the rendered field order. The live POST headers, exact encoded body, response, and redirect chain remain unverified.

The retained CDP events do **not** contain the submitted login POST, its response, or its redirect chain. Accordingly, the SDK's automatic login is implemented from the public form schema and is not marked as live-request verified. It stops when a CAPTCHA or extra challenge is presented. Do not treat this implementation as validated until a read-only login/query run confirms it.

## Operation coverage

| Operation | Evidence source | SDK status | Parity status |
|---|---|---|---|
| Login with login/password | Public login HTML/JS, CSRF cookie names; submitted POST not captured | Implemented using direct form POST and current cookies; offline mock form flow exercised | Inferred; live request headers/response/redirect unverified |
| Access-token refresh | Live GET and response key | Implemented with in-memory token cache | Browser response observed; effective request headers matched in offline MockTransport; no SDK network call |
| List domains | `4zBolJQc.js` GraphQL document | Implemented read-only | Static-source only |
| Add an existing domain to the account | `vsQkNF5i.js` `AddDomain` mutation | Implemented; optional ownership email defaults off | Static-source only; no live mutation sent |
| Read domain info and name servers | `DOnO3kb3.js` GraphQL documents | Implemented read-only | Static-source only |
| Read DNS records | Live `DnsRecords` request/response and `DM3HAFH9.js` | Implemented read-only | Browser request and offline MockTransport serialization match at the recorded HTTP/body layers; no live SDK network call |
| Create DNS records (A, AAAA, CNAME, MX, TXT, NS, SRV, CAA, SPF, SSHFP, NAPTR) | Mutation documents and form variable construction in `DM3HAFH9.js` | Implemented | Static-source only; no live mutation sent |
| Update DNS records (A, AAAA, CNAME, MX, TXT, NS, SRV, CAA, SPF) | Mutation documents and form variable construction in `DM3HAFH9.js` | Implemented | Static-source only; no live mutation sent |
| Delete DNS record / reset zone | Mutation documents in `DM3HAFH9.js` | Implemented; reset requires explicit `confirm=True` | Static-source only; no live mutation sent |
| WWW redirect, IPv6, name servers | Mutation documents in `DOnO3kb3.js` | Implemented | Static-source only; no live mutation sent |
| Contacts read/update | Query and mutation in `k6G1aeCs.js` | Implemented | Static-source only; no personal data retained |
| SSL read/request/upload/delete and force HTTPS | Query and mutations in `DDvMFQwB.js` | Implemented | Static-source only; no live mutation sent |
| Create subdomain | Mutation in `obY2JHxH.js` | Implemented | Static-source only; no live mutation sent |
| Register, transfer, delete domain, or paid renewal | Separate flows, outside the settings API scope | Not exposed | Not inspected or implemented |

## Direct HTTP implementation and limits

The SDK uses `httpx.AsyncClient(http2=True)` and direct HTTP calls; it does not start Selenium, Playwright, Puppeteer, or another browser runtime. It constructs the GraphQL JSON body as compact UTF-8 JSON with `query` before `variables`, sends the captured non-secret request headers (including `Origin` and fetch metadata), obtains `accessToken` dynamically, and keeps cookies/tokens in memory. The install extras enable HTTP/2 and Brotli/Zstandard response decoding so `Accept-Encoding` can match the browser.

HTTPX can negotiate HTTP/2 when the server supports it. The direct HTTP client's TLS fingerprint is not Chrome's, so full TLS-session identity is not claimed. The captured login POST is missing, and write operation bodies have not been compared against live browser requests. Those gaps remain visible above rather than being inferred as verified parity.

No HAR, CDP dump, credential, cookie, CSRF value, bearer token, account ID, domain-node ID, DNS record value, or contact value is included in this deliverable.


## CLI 0.2.0 delivery (2026-09-30)

The MCP proposal was superseded by the requested CLI and installed `jino-control` skill. The CLI uses the same HTTP SDK; no browser emulator or MCP server was added.

Changes include a console entry point and module launcher, compact JSON and paginated output, direct environment credentials or an optional current-Windows-user DPAPI credential profile, explicit write plans / `--apply`, pre-write record lookup and protection checks, preservation of omitted record names, type/IP/domain validation, NAPTR flags as text, and step reporting for partial settings updates. Login targets and redirects are restricted to the two known HTTPS control/auth origins. Explicit legacy errors stop settings processing. Write timeouts do not cause automatic mutation retries.

Independent read-back is implemented for A/AAAA, deletion, domain/subdomain addition, HTTPS, and settings when the returned fields are recognized. Complex DNS, contacts, SSL and zone reset currently report an unverified result after submitting a mutation; no successful HTTP response is presented as proof of application.

Local delivery observations:

- All 10 Python modules parsed with `ast.parse`; this is a syntax check, not a behavioral test suite.
- Installation into a dedicated skill venv completed and included HTTP/2, Brotli and Zstandard dependencies. No live HTTP/2 negotiation was exercised.
- Installed `status`, root `--help`, and `dns ip --help` executed locally. `status` reported that credentials were not configured.
- `domains list` without credentials returned compact `AUTH_REQUIRED` JSON before contacting Jino.
- The skill creator validator accepted the installed skill (Python UTF-8 mode was required on this Windows host).
- The retained DnsRecords document remains 453 UTF-8 bytes, SHA-256 `ce3eec40b589ebe1d4500708965e91d18d90e1c3d8a0019293661f51033ba248`.

No unit or integration test suite was added or executed for this delivery. DPAPI persistence has been implemented but not exercised with account credentials. No live CLI login, DNS query, or mutation was sent. The earlier SDK MockTransport observations describe the initial SDK version; they were not repeated against the changed transport. Request parity remains bounded by the browser capture and static-source evidence above.


## Live credential verification and redirect fix, CLI 0.2.1 (2026-09-30)

The user configured the encrypted credential profile and explicitly requested verification. Credentials were loaded in memory, and the installed CLI performed HTTP login and read-only queries. No browser emulator was used. No DNS/settings/SSL/contact/domain mutation was submitted.

The initial live login exposed a real redirect to `https://login.jino.ru/auth/realms/jino/protocol/openid-connect/auth`, rejected by the previous two-host allowlist. Allowing this exact additional HTTPS host fixed login. Credential POST remains restricted to `auth.jino.ru`; POST 307/308 redirects are still rejected. Only scheme/host/path were printed during diagnosis; redirect query values, cookies, credentials, CSRF and tokens were omitted.

| Live installed CLI operation | Result | Evidence limit |
| --- | --- | --- |
| `auth check --domain <domain>` | Success, authenticated; negotiated HTTP/2 | Valid HTTP login/access token; no browser POST comparison |
| `domains list --limit 1` | Success; account domain list returned | Returned names and account identifiers not retained in this report |
| `dns list <domain> --limit 1` | Success; records returned, zone changeable | Read-only; values/record IDs not retained |
| `settings get <domain>` | Success, expected settings keys including WWW and IPv6 | No settings changed |
| `domain nameservers <domain>` | Success, expected nameserver/changeable fields | No nameservers changed |
| `ssl get <domain>` | Success, certificate/request fields | No certificate request/upload/deletion |

Five offline regression cases pass for known-host acceptance, foreign/HTTP/userinfo/port rejection, OIDC GET redirect handling, prevention of POST replay after 307, and restriction of the password form action to the auth host. These use placeholder values and HTTPX MockTransport, never stored account credentials. The installed credential profile was successfully decrypted for live login; its plaintext was not output or written to a project file.

`status` now reports `live_login_verified=true`, `live_reads_verified=true`, `live_mutations_verified=false` as implementation evidence from this run. This does not promise current connectivity for every future call or browser-request parity. The earlier absence of live SDK verification describes the initial delivery and is superseded for the read operations above. Contact/renewal reads and all mutations remain unverified on the real account.
