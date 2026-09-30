"""Regression coverage for the observed Jino OIDC redirect chain."""
import unittest
import httpx
from jino_domains_sdk.exceptions import AuthenticationError
from jino_domains_sdk.transport import JinoHTTPTransport


class LoginRedirectTests(unittest.IsolatedAsyncioTestCase):
    def test_known_https_origins(self):
        for host in ("cp.jino.ru", "auth.jino.ru", "login.jino.ru"):
            JinoHTTPTransport._validate_control_url("https://" + host + "/")

    def test_other_origins_rejected(self):
        for url in ("http://login.jino.ru/", "https://login.jino.ru.evil.example/",
                    "https://example.com/", "https://auth.jino.ru:444/",
                    "https://user:password@auth.jino.ru/"):
            with self.subTest(url=url), self.assertRaises(AuthenticationError):
                JinoHTTPTransport._validate_control_url(url)

    async def test_post_redirects_through_oidc_as_get(self):
        seen = []
        def handler(request):
            seen.append((request.method, request.url.host, request.content))
            if request.url.host == "auth.jino.ru":
                return httpx.Response(302, headers={"location": "https://login.jino.ru/auth/realms/jino/protocol/openid-connect/auth"})
            if request.url.host == "login.jino.ru":
                return httpx.Response(302, headers={"location": "https://cp.jino.ru/domains/"})
            return httpx.Response(200)
        transport = JinoHTTPTransport("placeholder", "placeholder")
        transport._control = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            request = transport._control.build_request("POST", "https://auth.jino.ru/login/", data={"password": "placeholder"})
            response = await transport._control_send(request)
            self.assertEqual(response.url.host, "cp.jino.ru")
            self.assertEqual([item[:2] for item in seen], [("POST", "auth.jino.ru"), ("GET", "login.jino.ru"), ("GET", "cp.jino.ru")])
            self.assertEqual([item[2] for item in seen[1:]], [b"", b""])
        finally:
            await transport.close()

    async def test_post_307_not_replayed(self):
        seen = []
        def handler(request):
            seen.append(request)
            return httpx.Response(307, headers={"location": "https://login.jino.ru/auth/realms/jino/"})
        transport = JinoHTTPTransport("placeholder", "placeholder")
        transport._control = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            request = transport._control.build_request("POST", "https://auth.jino.ru/login/", data={"password": "placeholder"})
            with self.assertRaises(AuthenticationError):
                await transport._control_send(request)
            self.assertEqual(len(seen), 1)
        finally:
            await transport.close()

    async def test_form_cannot_send_password_to_oidc_host(self):
        transport = JinoHTTPTransport("placeholder", "placeholder")
        transport._cookie_value = lambda *args: "placeholder"
        page = httpx.Response(200, request=httpx.Request("GET", "https://auth.jino.ru/login/"), text="""<form id="login-form-with-history" action="https://login.jino.ru/auth/realms/jino/" data-form='{"fields":[]}'></form>""")
        with self.assertRaises(AuthenticationError):
            await transport._submit_login(page)


if __name__ == "__main__":
    unittest.main()
