import unittest

from src.portfolio.jw_session import JWBrowserSession, JWSessionError


class WaitForAuthenticationTests(unittest.TestCase):
    def test_does_not_raise_name_error_for_time_module(self):
        # Regressão: _wait_for_authentication() usava time.monotonic()
        # sem "import time" no topo do arquivo, o que derrubava
        # POST /api/jw/login com 409 "name 'time' is not defined"
        # assim que o login chegava na etapa de aguardar autenticação.
        session = JWBrowserSession()

        try:
            result = session._wait_for_authentication(timeout_seconds=0)
        except NameError as exc:
            self.fail(f"_wait_for_authentication levantou NameError: {exc}")

        # Sem página/navegador aberto, o método deve apenas
        # retornar False (não autenticado), nunca explodir.
        self.assertFalse(result)


# ==========================================================
# FAKES DE PÁGINA PLAYWRIGHT
# ==========================================================
#
# Simulam só o suficiente da API do Playwright usada por
# _switch_property()/_is_authenticated_page() para testar a
# troca de biblioteca sem abrir um navegador real.

class _FakeLocator:
    """Nunca encontra campos de login (sessão não está na tela de login)."""

    @property
    def first(self):
        return self

    def count(self):
        return 0


class _FakePage:
    def __init__(self, url: str):
        self._url = url
        self._closed = False
        self.goto_calls: list[str] = []

    def is_closed(self) -> bool:
        return self._closed

    @property
    def url(self) -> str:
        return self._url

    def goto(self, url, **kwargs):
        self.goto_calls.append(url)
        self._url = url

    def wait_for_timeout(self, _ms):
        pass

    def locator(self, _selector):
        return _FakeLocator()


class _FakePageRedirectsToLogin(_FakePage):
    """Simula uma sessão expirada: qualquer navegação cai no login."""

    def goto(self, url, **kwargs):
        self.goto_calls.append(url)
        self._url = "https://dashboard.jwplayer.com/login?returnTo=" + url


# ==========================================================
# TROCA DE BIBLIOTECA (MESMA SESSÃO)
# ==========================================================

class SwitchPropertyTests(unittest.TestCase):
    def test_validates_property_id_length(self):
        session = JWBrowserSession()

        with self.assertRaises(JWSessionError):
            session.switch_property("short")

    def test_without_open_browser_returns_disconnected_without_raising(self):
        # TESTE 4 (variação): nunca logado / navegador fechado — a
        # troca de biblioteca não deve inventar uma conexão, e
        # também não deve levantar exceção.
        session = JWBrowserSession()

        result = session.switch_property("AbCdEfGh")

        self.assertEqual(result["state"], "disconnected")
        self.assertFalse(result["connected"])

    def test_reuses_authenticated_session_across_libraries(self):
        # TESTE 1/2/3: sessão já autenticada na biblioteca A troca
        # para B reaproveitando a MESMA página/contexto — sem
        # login novo — e passa a reportar a biblioteca B.
        session = JWBrowserSession()
        session._property_id = "LibraryA"
        session._page = _FakePage(
            "https://dashboard.jwplayer.com/p/LibraryA/media"
        )

        result = session.switch_property("LibraryB")

        self.assertEqual(result["state"], "connected")
        self.assertTrue(result["connected"])
        self.assertEqual(session._property_id, "LibraryB")

        # Nenhuma página/navegador novo foi criado: a mesma
        # instância de página apenas navegou para a nova property.
        self.assertIn(
            "https://dashboard.jwplayer.com/p/LibraryB/media",
            session._page.goto_calls,
        )

    def test_switching_back_to_the_original_library_still_reuses_session(self):
        session = JWBrowserSession()
        session._property_id = "LibraryA"
        session._page = _FakePage(
            "https://dashboard.jwplayer.com/p/LibraryA/media"
        )

        session.switch_property("LibraryB")
        result = session.switch_property("LibraryA")

        self.assertEqual(result["state"], "connected")
        self.assertEqual(session._property_id, "LibraryA")

    def test_expired_session_reports_disconnected_and_keeps_previous_library(self):
        # TESTE 4: sessão expirada — a troca não pode fingir sucesso;
        # precisa reportar desconectado para permitir um novo login.
        session = JWBrowserSession()
        session._property_id = "LibraryA"
        session._page = _FakePageRedirectsToLogin(
            "https://dashboard.jwplayer.com/p/LibraryA/media"
        )

        result = session.switch_property("LibraryB")

        self.assertEqual(result["state"], "disconnected")
        self.assertFalse(result["connected"])

        # A troca não é confirmada: a biblioteca anterior é mantida
        # em vez de assumir silenciosamente a nova.
        self.assertEqual(session._property_id, "LibraryA")


if __name__ == "__main__":
    unittest.main()
