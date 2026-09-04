import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app as app_module


class SecurityTests(unittest.TestCase):
    def setUp(self):
        app_module.LOGIN_FAILURES.clear()

    def auth_config(self):
        return patch.multiple(
            app_module,
            AUTH_ENABLED=True,
            AUTH_USERNAME="operador",
            AUTH_PASSWORD="senha-segura-de-teste",
            AUTH_SESSION_SECRET="s" * 32,
            AUTH_SESSION_TTL_SECONDS=3600,
            AUTH_COOKIE_SECURE=False,
            AUTH_COOKIE_SAMESITE="lax",
            CORS_ALLOWED_ORIGINS=("https://frontend.example",),
        )

    def test_protected_api_requires_authentication(self):
        with self.auth_config():
            response = TestClient(app_module.app).get("/api/status")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["detail"],
            "Autenticação necessária.",
        )

    def test_login_session_and_logout(self):
        with self.auth_config():
            client = TestClient(app_module.app)
            login = client.post(
                "/api/auth/login",
                headers={"Origin": "https://frontend.example"},
                json={
                    "username": "operador",
                    "password": "senha-segura-de-teste",
                },
            )

            self.assertEqual(login.status_code, 200)
            self.assertIn("HttpOnly", login.headers["set-cookie"])
            self.assertIn("SameSite=lax", login.headers["set-cookie"])

            session = client.get("/api/auth/session")
            self.assertEqual(
                session.json(),
                {
                    "auth_enabled": True,
                    "authenticated": True,
                    "username": "operador",
                },
            )
            self.assertEqual(client.get("/api/status").status_code, 200)

            copied_session = client.cookies.get(
                app_module.AUTH_COOKIE_NAME
            )
            second_client = TestClient(app_module.app)
            second_client.cookies.set(
                app_module.AUTH_COOKIE_NAME,
                copied_session,
            )

            logout = client.post(
                "/api/auth/logout",
                headers={"Origin": "https://frontend.example"},
            )
            self.assertEqual(logout.status_code, 200)
            self.assertFalse(logout.json()["authenticated"])
            self.assertEqual(client.get("/api/status").status_code, 401)
            self.assertEqual(
                second_client.get("/api/status").status_code,
                401,
            )

    def test_invalid_credentials_do_not_create_session(self):
        with self.auth_config():
            client = TestClient(app_module.app)
            response = client.post(
                "/api/auth/login",
                headers={"Origin": "https://frontend.example"},
                json={
                    "username": "operador",
                    "password": "incorreta",
                },
            )

        self.assertEqual(response.status_code, 401)
        self.assertNotIn(app_module.AUTH_COOKIE_NAME, client.cookies)

    def test_unicode_credentials_are_supported(self):
        with self.auth_config(), patch.multiple(
            app_module,
            AUTH_USERNAME="usuário",
            AUTH_PASSWORD="senha-com-acentuação",
        ):
            response = TestClient(app_module.app).post(
                "/api/auth/login",
                headers={"Origin": "https://frontend.example"},
                json={
                    "username": "usuário",
                    "password": "senha-com-acentuação",
                },
            )

        self.assertEqual(response.status_code, 200)

    def test_mutating_request_rejects_unknown_origin(self):
        with self.auth_config():
            response = TestClient(app_module.app).post(
                "/api/auth/login",
                headers={"Origin": "https://malicioso.example"},
                json={
                    "username": "operador",
                    "password": "senha-segura-de-teste",
                },
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Origem não autorizada.")

    def test_mutating_request_requires_origin_when_auth_is_enabled(self):
        with self.auth_config():
            response = TestClient(app_module.app).post(
                "/api/auth/login",
                json={
                    "username": "operador",
                    "password": "senha-segura-de-teste",
                },
            )

        self.assertEqual(response.status_code, 403)

    def test_login_is_rate_limited(self):
        with self.auth_config(), patch.object(
            app_module,
            "AUTH_LOGIN_MAX_ATTEMPTS",
            2,
        ):
            client = TestClient(app_module.app)
            request = {
                "headers": {"Origin": "https://frontend.example"},
                "json": {
                    "username": "operador",
                    "password": "incorreta",
                },
            }
            self.assertEqual(
                client.post("/api/auth/login", **request).status_code,
                401,
            )
            self.assertEqual(
                client.post("/api/auth/login", **request).status_code,
                401,
            )
            response = client.post("/api/auth/login", **request)

        self.assertEqual(response.status_code, 429)

    def test_tampered_session_is_rejected(self):
        with self.auth_config():
            client = TestClient(app_module.app)
            client.cookies.set(app_module.AUTH_COOKIE_NAME, "payload.invalida")
            response = client.get("/api/status")

        self.assertEqual(response.status_code, 401)

    def test_cors_preflight_allows_configured_origin(self):
        cors_app = FastAPI()
        app_module.add_cors_middleware(
            cors_app,
            ("https://frontend.example",),
        )

        @cors_app.post("/resource")
        def resource():
            return {"ok": True}

        response = TestClient(cors_app).options(
            "/resource",
            headers={
                "Origin": "https://frontend.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "https://frontend.example",
        )
        self.assertEqual(
            response.headers["access-control-allow-credentials"],
            "true",
        )
        self.assertIn(
            "content-type",
            response.headers["access-control-allow-headers"].casefold(),
        )

        resource_response = TestClient(cors_app).post(
            "/resource",
            headers={"Origin": "https://frontend.example"},
        )
        self.assertEqual(
            resource_response.headers["access-control-expose-headers"],
            "Content-Disposition",
        )

    def test_configured_origins_normalizes_values(self):
        with patch.dict(
            os.environ,
            {
                "CORS_ALLOWED_ORIGINS": (
                    "https://app.example/, https://preview.example"
                )
            },
        ):
            origins = app_module.configured_origins()

        self.assertEqual(
            origins,
            (
                "https://app.example",
                "https://preview.example",
            ),
        )

    def test_configured_origins_rejects_wildcard(self):
        with patch.dict(
            os.environ,
            {"CORS_ALLOWED_ORIGINS": "*"},
        ):
            with self.assertRaises(RuntimeError):
                app_module.configured_origins()


if __name__ == "__main__":
    unittest.main()
