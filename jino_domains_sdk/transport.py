"""Direct HTTP transport for Jino's control panel and GraphQL API."""

from __future__ import annotations

import json
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from .exceptions import AuthenticationError, JinoHTTPError, ProtocolError


CONTROL_ORIGIN = "https://cp.jino.ru"
AUTH_ORIGIN = "https://auth.jino.ru"
GRAPHQL_URL = "https://graphql.jino.ru/user/"
NAVIGATION_ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
    "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
)

# Values observed on the signed-in Chrome 154 request. These are ordinary
# HTTP headers; the SDK uses an HTTP client and does not start or emulate Chrome.
OBSERVED_BROWSER_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
    ),
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "ru",
    "sec-ch-ua": '"Chromium";v="154", "Google Chrome";v="154", "Not A(Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}


class _LoginPageParser(HTMLParser):
    """Extract only public login form metadata; never reads user-entered values."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.login_form: dict | None = None
        self._inside_login = False

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        if tag.lower() == "form" and values.get("id") == "login-form-with-history":
            self.login_form = values
            self._inside_login = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "form" and self._inside_login:
            self._inside_login = False


class JinoHTTPTransport:
    """Maintain ephemeral cookies and send direct HTTP/2-capable requests."""

    def __init__(
        self,
        login: str,
        password: str,
        *,
        timeout: float = 30.0,
        browser_headers: dict[str, str] | None = None,
    ) -> None:
        self._login = login
        self._password = password
        self._timeout = timeout
        self.browser_headers = dict(OBSERVED_BROWSER_HEADERS)
        if browser_headers:
            if set(key.lower() for key in browser_headers) - set(OBSERVED_BROWSER_HEADERS):
                raise ValueError("browser_headers accepts only captured non-secret profile headers")
            self.browser_headers.update(
                {key.lower(): value for key, value in browser_headers.items()}
            )
        self._control: httpx.AsyncClient | None = None
        self._graphql: httpx.AsyncClient | None = None
        self._authenticated = False
        self._current_route: str | None = None
        self._access_token: str | None = None
        self.last_http_version: str | None = None

    async def start(self) -> None:
        if self._control is not None:
            return
        timeout = httpx.Timeout(self._timeout)
        self._control = httpx.AsyncClient(
            http2=True,
            follow_redirects=False,
            timeout=timeout,
            headers=self.browser_headers,
        )
        # Browser fetch defaults to same-origin credentials. The GraphQL host is
        # cross-origin, so it receives the bearer header but no cp.jino.ru cookies.
        self._graphql = httpx.AsyncClient(
            http2=True,
            follow_redirects=False,
            timeout=timeout,
            headers={
                "user-agent": self.browser_headers["user-agent"],
                "accept-encoding": self.browser_headers["accept-encoding"],
                "accept-language": self.browser_headers["accept-language"],
            },
        )

    async def close(self) -> None:
        if self._control is not None:
            await self._control.aclose()
        if self._graphql is not None:
            await self._graphql.aclose()
        self._control = None
        self._graphql = None
        self._authenticated = False
        self._current_route = None
        self._access_token = None
        self._login = ""
        self._password = ""

    def invalidate_session(self) -> None:
        self._authenticated = False
        self._access_token = None
        self._current_route = None

    @staticmethod
    def _validate_control_url(url: str) -> None:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname not in {"cp.jino.ru", "auth.jino.ru", "login.jino.ru"}
                or parsed.port not in (None, 443) or parsed.username or parsed.password):
            raise AuthenticationError("Jino login transition points outside the allowed origins.")

    async def _control_send(self, request: httpx.Request) -> httpx.Response:
        for _ in range(11):
            self._validate_control_url(str(request.url))
            response = await self._control.send(request, follow_redirects=False)
            self.last_http_version = response.http_version
            if response.status_code not in {301, 302, 303, 307, 308}:
                return response
            location = response.headers.get("location")
            if not location:
                raise ProtocolError("Jino redirect has no Location header.")
            target = urljoin(str(response.url), location)
            self._validate_control_url(target)
            if request.method == "POST" and response.status_code in {307, 308}:
                raise AuthenticationError("Unexpected redirect would resend login credentials.")
            method = "GET" if response.status_code == 303 or request.method == "POST" and response.status_code in {301, 302} else request.method
            headers = dict(request.headers)
            for key in ("host", "cookie", "content-length"):
                headers.pop(key, None)
            if method == "GET":
                for key in ("content-type", "origin"):
                    headers.pop(key, None)
            request = self._control.build_request(method, target, headers=headers)
        raise AuthenticationError("Jino login exceeded the redirect limit.")

    async def ensure_page(self, domain: str | None, section: str) -> None:
        """Load a control-panel route and authenticate through Jino's HTML form."""
        await self.start()
        route = (
            f"{CONTROL_ORIGIN}/domains/{domain}/{section}"
            if domain
            else f"{CONTROL_ORIGIN}/domains/"
        )
        if self._authenticated and self._current_route == route:
            return
        response = await self._control_get(
            route,
            headers={"upgrade-insecure-requests": "1"},
        )
        self._current_route = route
        if response.status_code >= 400:
            raise JinoHTTPError(response.status_code, "control-panel page request failed")

        if urlsplit(str(response.url)).hostname == "auth.jino.ru":
            self._access_token = None
            await self._submit_login(response)
            if self._current_route != route:
                response = await self._control_get(
                    route,
                    headers={"upgrade-insecure-requests": "1"},
                )
                self._current_route = str(response.url)
                if urlsplit(self._current_route).hostname != "cp.jino.ru":
                    raise AuthenticationError("Jino did not return to the requested domain page.")
        elif urlsplit(str(response.url)).hostname == "cp.jino.ru":
            self._authenticated = True
        else:
            raise AuthenticationError("Jino redirected outside the expected login flow.")

        # Fetch the token once per session, matching the site's cached
        # /api/auth/access-token -> Authorization: Bearer <token> flow.
        if not self._access_token:
            await self._get_access_token(force=True)

    async def _submit_login(self, response: httpx.Response) -> None:
        parser = _LoginPageParser()
        parser.feed(response.text)
        form = parser.login_form
        if not form:
            raise AuthenticationError("The Jino login form was not present in the response.")

        try:
            descriptor = json.loads(form.get("data-form", "{}"))
        except (TypeError, json.JSONDecodeError) as exc:
            raise AuthenticationError("The Jino login form schema could not be parsed.") from exc

        if not isinstance(descriptor, dict):
            raise ProtocolError("Jino login descriptor must be an object.")
        fields = descriptor.get("fields") or []
        if not isinstance(fields, list) or any(not isinstance(field, dict) for field in fields):
            raise ProtocolError("Jino login fields must be objects.")
        if descriptor.get("captcha_type") or any(field.get("name", "").endswith("captcha") for field in fields):
            raise AuthenticationError(
                "Jino requires a CAPTCHA or additional challenge; automatic login stopped."
            )

        data: dict[str, str] = {}
        for field in fields:
            name = field.get("name")
            if name:
                value = field.get("value")
                data[name] = "" if value is None else str(value)
        data["login"] = _browser_login_value(self._login)
        data["password"] = self._password
        # The Vue form renders its optional page-format field before CSRF.
        format_name = form.get("data-page-format-field-name")
        format_value = form.get("data-page-format")
        if format_name and format_value:
            data[format_name] = format_value

        csrf = self._cookie_value("csrftoken", "auth.jino.ru")
        if not csrf:
            raise AuthenticationError("The Jino login page did not set its CSRF cookie.")
        data["csrfmiddlewaretoken"] = csrf

        action = urljoin(str(response.url), form.get("action") or str(response.url))
        self._validate_control_url(action)
        if urlsplit(action).hostname != "auth.jino.ru":
            raise AuthenticationError("Jino login form action is outside the auth origin.")
        headers = {
            "origin": AUTH_ORIGIN,
            "referer": str(response.url),
            "accept": NAVIGATION_ACCEPT,
            "content-type": "application/x-www-form-urlencoded",
            "priority": "u=0, i",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
        }
        result = await self._control_send(self._control.build_request("POST", action, data=data, headers=headers))
        self._current_route = str(result.url)
        if result.status_code >= 400:
            raise AuthenticationError("Jino rejected the login form request.")
        if urlsplit(str(result.url)).hostname != "cp.jino.ru":
            raise AuthenticationError(
                "Jino did not complete login. Check the account details or any required challenge."
            )
        self._authenticated = True

    def _cookie_value(self, name: str, host: str) -> str | None:
        matches = []
        for cookie in self._control.cookies.jar:
            domain = cookie.domain.lstrip(".")
            applicable = domain == host or cookie.domain_specified and host.endswith("." + domain)
            if cookie.name == name and applicable and not cookie.is_expired():
                matches.append(cookie)
        if matches:
            return max(matches, key=lambda cookie: len(cookie.domain)).value
        return None

    async def _control_get(self, url: str, *, headers: dict[str, str] | None = None):
        request = self._control.build_request("GET", url, headers=headers)
        path = urlsplit(url).path
        if path.startswith("/domains/"):
            request.headers.update(
                {
                    "accept": NAVIGATION_ACCEPT,
                    "priority": "u=0, i",
                    "sec-fetch-dest": "document",
                    "sec-fetch-mode": "navigate",
                    "sec-fetch-site": "same-origin",
                    "sec-fetch-user": "?1",
                    "upgrade-insecure-requests": "1",
                }
            )
        elif path == "/api/auth/access-token":
            request.headers.update(
                {
                    "accept": "*/*",
                    "priority": "u=1, i",
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-origin",
                }
            )
        return await self._control_send(request)

    async def _get_access_token(self, *, force: bool = False) -> str:
        if self._access_token and not force:
            return self._access_token
        headers = {}
        if self._current_route:
            headers["referer"] = self._current_route
        response = await self._control_get(
            f"{CONTROL_ORIGIN}/api/auth/access-token",
            headers=headers,
        )
        self.last_http_version = response.http_version
        if urlsplit(str(response.url)).hostname == "auth.jino.ru":
            raise AuthenticationError("Jino cookie session has expired.", recoverable=True)
        if response.status_code >= 400:
            raise AuthenticationError(
                f"Jino access-token endpoint returned HTTP {response.status_code}."
            )
        try:
            token = response.json().get("accessToken")
        except (ValueError, AttributeError) as exc:
            raise AuthenticationError("Jino returned an invalid access-token response.") from exc
        if not isinstance(token, str) or not token:
            raise AuthenticationError("Jino did not return an access token.")
        self._access_token = token
        return token

    async def _send_preflight(self) -> None:
        response = await self._graphql.options(
            GRAPHQL_URL,
            headers={
                "accept": "*/*",
                "origin": CONTROL_ORIGIN,
                "access-control-request-method": "POST",
                "access-control-request-headers": "authorization,content-type",
                "priority": "u=1, i",
                "referer": f"{CONTROL_ORIGIN}/",
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site",
            },
        )
        self.last_http_version = response.http_version
        if response.status_code >= 400:
            raise JinoHTTPError(response.status_code, "GraphQL preflight request failed")

    async def graphql(self, query: str, variables: dict | None) -> dict:
        """POST the browser's GraphQL JSON shape and return the decoded response."""
        request_body = {"query": query}
        if variables is not None:
            request_body["variables"] = variables
        body = json.dumps(
            request_body,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

        for attempt in range(2):
            await self._send_preflight()
            token = await self._get_access_token(force=bool(attempt))
            headers = {
                "accept": "application/json",
                "authorization": f"Bearer {token}",
                "content-type": "application/json",
                "origin": CONTROL_ORIGIN,
                "priority": "u=1, i",
                "referer": f"{CONTROL_ORIGIN}/",
                "sec-ch-ua": self.browser_headers["sec-ch-ua"],
                "sec-ch-ua-mobile": self.browser_headers["sec-ch-ua-mobile"],
                "sec-ch-ua-platform": self.browser_headers["sec-ch-ua-platform"],
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site",
            }
            response = await self._graphql.post(GRAPHQL_URL, content=body, headers=headers)
            self.last_http_version = response.http_version
            if response.status_code != 401 or attempt:
                break
            self._access_token = None

        if response.status_code == 401:
            raise AuthenticationError("Jino rejected the authenticated session.", recoverable=True)
        if response.status_code < 200 or response.status_code >= 300:
            raise JinoHTTPError(response.status_code, "GraphQL request failed")
        try:
            return response.json()
        except ValueError as exc:
            raise JinoHTTPError(response.status_code, "GraphQL response was not valid JSON") from exc


def _browser_login_value(value: str) -> str:
    """Mirror Jino's public form submit handler for the login field."""
    normalized = value.lower()
    if normalized.startswith("+"):
        normalized = normalized[1:]
    return normalized.rstrip()
