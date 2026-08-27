import unittest

from src.portfolio.jw_session import JWBrowserSession


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


if __name__ == "__main__":
    unittest.main()
