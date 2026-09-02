from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone


class JWSessionError(RuntimeError):
    """Erro relacionado à sessão automatizada do JW Player."""


@dataclass
class SessionStatus:
    state: str = "disconnected"
    message: str = "Não conectado"
    current_url: str = ""
    property_id: str = ""
    connected: bool = False


class JWBrowserSession:
    """
    Mantém uma única sessão Playwright em uma única thread.

    O navegador é executado em segundo plano (headless=True).

    A senha existe somente durante o processo de login e não é
    armazenada como atributo da classe.

    O contexto autenticado permanece vivo enquanto a aplicação
    estiver em execução.

    Toda operação Playwright passa pelo mesmo executor/thread para
    evitar problemas de thread com Playwright Sync API.
    """

    LOGIN_TIMEOUT = 120
    NAVIGATION_TIMEOUT = 60
    VERIFY_TIMEOUT = 30
    CAPTURE_TIMEOUT = 180

    def __init__(self):
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="jw-browser",
        )

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

        self._property_id = ""

        self._status = SessionStatus()

        self._lock = threading.Lock()

    # ==========================================================
    # STATUS
    # ==========================================================

    def _set_status(
        self,
        state: str,
        message: str,
        current_url: str = "",
        connected: bool | None = None,
    ) -> None:
        """
        Atualiza o estado da sessão.

        Se connected não for informado, ele é derivado do state.
        """

        if connected is None:
            connected = state == "connected"

        with self._lock:
            self._status = SessionStatus(
                state=state,
                message=message,
                current_url=current_url,
                property_id=self._property_id,
                connected=connected,
            )

    def status(self) -> dict:
        """
        Retorna o status atual sem acessar Playwright.

        Importante:
        status() não executa uma verificação real da sessão.

        Para verificar se a autenticação ainda está válida use
        verify().
        """

        with self._lock:
            status = self._status.__dict__.copy()

        status["property_id"] = (
            status.get("property_id")
            or self._property_id
        )

        status["connected"] = (
            status.get("state") == "connected"
            and bool(
                status.get("property_id")
            )
        )

        return status

    # ==========================================================
    # LOGIN
    # ==========================================================

    def login(
        self,
        email: str,
        password: str,
        property_id: str,
    ) -> dict:

        email = email.strip()
        property_id = property_id.strip()

        if not email or not password:
            raise JWSessionError(
                "Informe e-mail e senha do JW Player."
            )

        if len(property_id) != 8:
            raise JWSessionError(
                "O Property ID deve ter oito caracteres."
            )

        future = self._executor.submit(
            self._login,
            email,
            password,
            property_id,
        )

        try:
            return future.result(
                timeout=self.LOGIN_TIMEOUT
            )

        except JWSessionError:
            raise

        except Exception as exc:
            raise JWSessionError(
                f"Falha durante o login no JW Player: {exc}"
            ) from exc

    # ==========================================================
    # NAVEGADOR
    # ==========================================================

    def _ensure_browser(self) -> None:
        """
        Garante que o navegador e o contexto existam.

        O navegador é criado em modo headless, portanto não abre
        uma janela visível para o usuário.
        """

        if (
            self._page
            and not self._page.is_closed()
            and self._browser
            and self._context
        ):
            return

        self._cleanup_browser()

        try:
            from playwright.sync_api import sync_playwright

        except ImportError as exc:
            raise JWSessionError(
                "Playwright não está instalado."
            ) from exc

        try:
            self._playwright = (
                sync_playwright().start()
            )

            self._browser = (
                self._playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--autoplay-policy=no-user-gesture-required",
                        "--disable-blink-features=AutomationControlled",
                        # Flags de redução de memória para rodar em
                        # instâncias com pouca RAM (ex.: Render 512MB).
                        # Não afetam autoplay/captura de vídeo.
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-extensions",
                        "--disable-background-networking",
                        "--disable-default-apps",
                        "--disable-sync",
                        "--disable-translate",
                        "--metrics-recording-only",
                        "--no-first-run",
                        "--disable-backgrounding-occluded-windows",
                        "--disable-renderer-backgrounding",
                        "--mute-audio",
                    ],
                )
            )

            self._context = (
                self._browser.new_context(
                    viewport={
                        "width": 1440,
                        "height": 900,
                    },
                    ignore_https_errors=False,
                )
            )

            self._page = (
                self._context.new_page()
            )

            self._page.set_default_timeout(
                30000
            )

            self._page.set_default_navigation_timeout(
                self.NAVIGATION_TIMEOUT * 1000
            )

        except Exception as exc:

            self._cleanup_browser()

            raise JWSessionError(
                "Não foi possível abrir o navegador "
                "automatizado. "
                "Verifique se o Playwright/Chromium "
                "está instalado. Execute: "
                "python -m playwright install chromium"
            ) from exc

    # ==========================================================
    # LIMPEZA INTERNA
    # ==========================================================

    def _cleanup_browser(self) -> None:
        """
        Fecha silenciosamente os recursos Playwright existentes.
        """

        try:
            if self._page:
                try:
                    self._page.close()
                except Exception:
                    pass

            if self._context:
                try:
                    self._context.close()
                except Exception:
                    pass

            if self._browser:
                try:
                    self._browser.close()
                except Exception:
                    pass

            if self._playwright:
                try:
                    self._playwright.stop()
                except Exception:
                    pass

        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None

    # ==========================================================
    # LOGIN INTERNO
    # ==========================================================

    def _login(
        self,
        email: str,
        password: str,
        property_id: str,
    ) -> dict:

        self._property_id = property_id

        self._set_status(
            "connecting",
            "Abrindo o JW Player em segundo plano.",
        )

        self._ensure_browser()

        target = (
            "https://dashboard.jwplayer.com/"
            f"p/{property_id}/media"
        )

        try:
            self._page.goto(
                target,
                wait_until="domcontentloaded",
                timeout=self.NAVIGATION_TIMEOUT * 1000,
            )

            self._page.wait_for_timeout(2000)

            current_url = self._page.url

            self._set_status(
                "connecting",
                "Verificando autenticação do JW Player.",
                current_url,
                connected=False,
            )

            # --------------------------------------------------
            # VERIFICAR SE JÁ ESTÁ AUTENTICADO
            # --------------------------------------------------

            if self._is_authenticated_page():
                return self._finish_connected()

            # --------------------------------------------------
            # LOGIN
            # --------------------------------------------------

            if self._is_login_page():

                self._set_status(
                    "connecting",
                    "Preenchendo credenciais do JW Player.",
                    self._page.url,
                    connected=False,
                )

                self._perform_login(
                    email,
                    password,
                )

            # --------------------------------------------------
            # AGUARDAR AUTENTICAÇÃO
            # --------------------------------------------------

            self._set_status(
                "connecting",
                "Aguardando confirmação da autenticação.",
                self._page.url,
                connected=False,
            )

            authenticated = self._wait_for_authentication(
                timeout_seconds=45
            )

            if authenticated:
                return self._finish_connected()

            current = self._page.url
            current_lower = current.lower()

            if (
                "challenge" in current_lower
                or "mfa" in current_lower
                or "captcha" in current_lower
            ):
                self._set_status(
                    "attention",
                    (
                        "O JW Player solicitou MFA ou CAPTCHA. "
                        "A autenticação automática não conseguiu "
                        "concluir essa etapa."
                    ),
                    current,
                    connected=False,
                )

                return self.status()

            if "/login" in current_lower:
                self._set_status(
                    "attention",
                    (
                        "O login do JW Player não foi concluído. "
                        "A página de autenticação ainda está ativa."
                    ),
                    current,
                    connected=False,
                )

                return self.status()

            self._set_status(
                "attention",
                (
                    "O navegador foi aberto, mas não foi possível "
                    "confirmar a autenticação no JW Player."
                ),
                current,
                connected=False,
            )

            return self.status()

        except JWSessionError:
            raise

        except Exception as exc:

            current_url = ""

            try:
                if (
                    self._page
                    and not self._page.is_closed()
                ):
                    current_url = self._page.url
            except Exception:
                pass

            self._set_status(
                "error",
                str(exc),
                current_url,
                connected=False,
            )

            raise JWSessionError(
                str(exc)
            ) from exc

        finally:
            # A senha não fica armazenada.
            password = ""

    # ==========================================================
    # DETECTAR LOGIN
    # ==========================================================

    def _is_login_page(self) -> bool:
        if (
            not self._page
            or self._page.is_closed()
        ):
            return False

        try:
            url = self._page.url.lower()

            if "/login" in url:
                return True

            if "/signin" in url:
                return True

            if "auth0" in url:
                return True

        except Exception:
            pass

        selectors = (
            'input[name="username"]',
            'input[name="email"]',
            'input[type="email"]',
            'input[name="password"]',
        )

        for selector in selectors:
            try:
                locator = self._page.locator(
                    selector
                ).first

                if locator.count() > 0:
                    if locator.is_visible(
                        timeout=500
                    ):
                        return True

            except Exception:
                continue

        return False

    def _is_authenticated_page(self) -> bool:
        """
        Verificação conservadora de autenticação.

        Não considera simplesmente "não estar em /login" como
        autenticado.

        O dashboard da propriedade precisa estar acessível e a
        página não pode apresentar elementos típicos de login.
        """

        if (
            not self._page
            or self._page.is_closed()
        ):
            return False

        try:
            current = self._page.url.lower()

            if (
                "/login" in current
                or "/signin" in current
                or "challenge" in current
                or "captcha" in current
                or "mfa" in current
            ):
                return False

            expected = (
                f"/p/{self._property_id}/"
            ).lower()

            if expected not in current:
                return False

            if self._is_login_page():
                return False

            return True

        except Exception:
            return False

    # ==========================================================
    # EXECUTAR LOGIN
    # ==========================================================

    def _perform_login(
        self,
        email: str,
        password: str,
    ) -> None:

        # --------------------------------------------------
        # E-MAIL / USERNAME
        # --------------------------------------------------

        username_selectors = (
            'input[name="username"]',
            'input[name="email"]',
            'input[type="email"]',
            'input[autocomplete="username"]',
        )

        username = None

        for selector in username_selectors:

            try:
                locator = (
                    self._page.locator(
                        selector
                    ).first
                )

                if locator.count() > 0:
                    locator.wait_for(
                        state="visible",
                        timeout=5000,
                    )

                    username = locator
                    break

            except Exception:
                continue

        if username is None:

            raise JWSessionError(
                "Campo de e-mail do JW Player "
                "não foi encontrado."
            )

        username.fill(email)

        # --------------------------------------------------
        # CONTINUAR
        # --------------------------------------------------

        continue_selectors = (
            'button[type="submit"]',
            'button:has-text("Continue")',
            'button:has-text("Continuar")',
            'input[type="submit"]',
        )

        clicked = False

        for selector in continue_selectors:

            try:

                button = (
                    self._page.locator(
                        selector
                    ).first
                )

                if button.count() > 0:

                    button.wait_for(
                        state="visible",
                        timeout=3000,
                    )

                    button.click(
                        timeout=5000
                    )

                    clicked = True
                    break

            except Exception:
                continue

        if not clicked:

            try:
                username.press(
                    "Enter"
                )
                clicked = True
            except Exception:
                pass

        if not clicked:

            raise JWSessionError(
                "Não foi possível avançar "
                "para a etapa de senha."
            )

        self._page.wait_for_timeout(
            1500
        )

        # --------------------------------------------------
        # SENHA
        # --------------------------------------------------

        password_selectors = (
            'input[name="password"]',
            'input[type="password"]',
            'input[autocomplete="current-password"]',
        )

        password_field = None

        for selector in password_selectors:

            try:

                locator = (
                    self._page.locator(
                        selector
                    ).first
                )

                if locator.count() > 0:

                    locator.wait_for(
                        state="visible",
                        timeout=10000,
                    )

                    password_field = locator
                    break

            except Exception:
                continue

        if password_field is None:

            current = self._page.url.lower()

            if (
                "challenge" in current
                or "mfa" in current
                or "captcha" in current
            ):
                raise JWSessionError(
                    "O JW Player solicitou MFA ou CAPTCHA "
                    "antes da senha."
                )

            raise JWSessionError(
                "Campo de senha do JW Player "
                "não foi encontrado."
            )

        password_field.fill(
            password
        )

        # --------------------------------------------------
        # LOGIN FINAL
        # --------------------------------------------------

        login_selectors = (
            'button[type="submit"]',
            'button:has-text("Login")',
            'button:has-text("Log in")',
            'button:has-text("Entrar")',
            'input[type="submit"]',
        )

        clicked = False

        for selector in login_selectors:

            try:

                button = (
                    self._page.locator(
                        selector
                    ).first
                )

                if button.count() > 0:

                    button.wait_for(
                        state="visible",
                        timeout=3000,
                    )

                    button.click(
                        timeout=5000
                    )

                    clicked = True
                    break

            except Exception:
                continue

        if not clicked:

            try:
                password_field.press(
                    "Enter"
                )
                clicked = True
            except Exception:
                pass

        if not clicked:

            raise JWSessionError(
                "Não foi possível enviar "
                "as credenciais do JW Player."
            )

    # ==========================================================
    # AGUARDAR AUTENTICAÇÃO
    # ==========================================================

    def _wait_for_authentication(
        self,
        timeout_seconds: int = 45,
    ) -> bool:

        deadline = (
            time.monotonic()
            + timeout_seconds
        )

        while time.monotonic() < deadline:

            if (
                not self._page
                or self._page.is_closed()
            ):
                return False

            current = self._page.url.lower()

            if (
                "challenge" in current
                or "captcha" in current
                or "mfa" in current
            ):
                return False

            if self._is_authenticated_page():
                return True

            try:
                self._page.wait_for_timeout(
                    500
                )
            except Exception:
                return False

        return False

    # ==========================================================
    # FINALIZAR CONEXÃO
    # ==========================================================

    def _finish_connected(self) -> dict:

        current = ""

        try:
            current = self._page.url
        except Exception:
            pass

        self._set_status(
            "connected",
            "Sessão JW Player conectada e autenticada.",
            current,
            connected=True,
        )

        return self.status()

    # ==========================================================
    # VERIFICAÇÃO
    # ==========================================================

    def verify(self) -> dict:

        future = self._executor.submit(
            self._verify
        )

        try:
            return future.result(
                timeout=self.VERIFY_TIMEOUT
            )

        except JWSessionError:
            raise

        except Exception as exc:
            raise JWSessionError(
                f"Falha ao verificar sessão JW Player: {exc}"
            ) from exc

    def _verify(self) -> dict:

        if (
            not self._page
            or self._page.is_closed()
        ):

            self._set_status(
                "disconnected",
                "Navegador JW Player fechado.",
                connected=False,
            )

            return self.status()

        try:

            current = self._page.url
            current_lower = current.lower()

            if (
                "challenge" in current_lower
                or "captcha" in current_lower
                or "mfa" in current_lower
            ):

                self._set_status(
                    "attention",
                    (
                        "O JW Player solicitou MFA ou CAPTCHA."
                    ),
                    current,
                    connected=False,
                )

                return self.status()

            if self._is_login_page():

                self._set_status(
                    "disconnected",
                    (
                        "A sessão JW Player "
                        "não está autenticada."
                    ),
                    current,
                    connected=False,
                )

                return self.status()

            # --------------------------------------------------
            # VERIFICAÇÃO REAL
            # --------------------------------------------------

            target = (
                "https://dashboard.jwplayer.com/"
                f"p/{self._property_id}/media"
            )

            if not current.startswith(
                "https://dashboard.jwplayer.com/"
            ):

                self._page.goto(
                    target,
                    wait_until="domcontentloaded",
                    timeout=self.NAVIGATION_TIMEOUT * 1000,
                )

                self._page.wait_for_timeout(
                    1000
                )

                current = self._page.url

            if self._is_authenticated_page():

                self._set_status(
                    "connected",
                    (
                        "Sessão JW Player "
                        "autenticada e ativa."
                    ),
                    current,
                    connected=True,
                )

            else:

                self._set_status(
                    "disconnected",
                    (
                        "A autenticação do JW Player "
                        "não pôde ser confirmada."
                    ),
                    current,
                    connected=False,
                )

            return self.status()

        except Exception as exc:

            current = ""

            try:
                current = self._page.url
            except Exception:
                pass

            self._set_status(
                "error",
                str(exc),
                current,
                connected=False,
            )

            raise JWSessionError(
                str(exc)
            ) from exc

    # ==========================================================
    # DATA "CREATED" DA PÁGINA DE DETALHES DA MÍDIA
    # ==========================================================
    #
    # Fallback usado quando o playback.json não traz pubdate.
    # O painel "Media summary" da página de detalhes do vídeo no
    # JW Player mostra um campo "Created" (ex.: "Apr 03, 2023")
    # — confirmado por captura de tela contra vídeos reais desta
    # conta, sempre coincidindo com o pubdate quando ambos estão
    # disponíveis. Não gera erro: sessão desconectada, página
    # sem esse campo ou data em formato inesperado só resultam
    # em None (fallback silencioso, nunca bloqueia o restante do
    # fluxo de publish_date).

    def fetch_created_date(
        self,
        media_id: str,
    ) -> datetime | None:

        media_id = str(
            media_id or ""
        ).strip()

        if not media_id:
            return None

        if (
            self.status().get("state")
            != "connected"
        ):
            return None

        try:

            future = self._executor.submit(
                self._fetch_created_date,
                media_id,
            )

            return future.result(
                timeout=self.CAPTURE_TIMEOUT
            )

        except Exception:
            return None

    def _fetch_created_date(
        self,
        media_id: str,
    ) -> datetime | None:

        if (
            not self._page
            or self._page.is_closed()
        ):
            return None

        if not self._is_authenticated_page():
            return None

        target = (
            "https://dashboard.jwplayer.com/"
            f"p/{self._property_id}/media/{media_id}"
        )

        try:

            self._page.goto(
                target,
                wait_until="domcontentloaded",
                timeout=self.NAVIGATION_TIMEOUT * 1000,
            )

            self._page.wait_for_timeout(9000)

            date_pattern = re.compile(
                r"^[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}$"
            )

            locator = self._page.get_by_text(
                date_pattern
            )

            for index in range(
                min(locator.count(), 5)
            ):

                text = locator.nth(
                    index
                ).inner_text().strip()

                try:
                    return datetime.strptime(
                        text,
                        "%b %d, %Y",
                    ).replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    continue

            return None

        except Exception:
            return None

    # ==========================================================
    # CAPTURA DA MÍDIA
    # ==========================================================

    def capture_media(
        self,
        media_id: str,
    ) -> dict:

        media_id = str(
            media_id or ""
        ).strip()

        if not media_id:
            raise JWSessionError(
                "JWPlayer ID não informado."
            )

        current_status = self.status()

        if (
            current_status.get("state")
            != "connected"
        ):

            raise JWSessionError(
                "Conecte uma sessão JW Player "
                "antes de acessar a mídia."
            )

        future = self._executor.submit(
            self._capture_media,
            media_id,
        )

        try:
            return future.result(
                timeout=self.CAPTURE_TIMEOUT
            )

        except JWSessionError:
            raise

        except Exception as exc:
            raise JWSessionError(
                f"Falha ao capturar mídia JW Player: {exc}"
            ) from exc

    def _capture_media(
        self,
        media_id: str,
    ) -> dict:

        if (
            not self._page
            or self._page.is_closed()
        ):

            self._set_status(
                "attention",
                (
                    "O navegador JW Player foi fechado. "
                    "Conecte novamente para continuar."
                ),
                connected=False,
            )

            raise JWSessionError(
                "O navegador JW Player foi fechado. "
                "Conecte novamente para continuar."
            )

        # ------------------------------------------------------
        # VERIFICAR SESSÃO ANTES DE ACESSAR A MÍDIA
        # ------------------------------------------------------

        if not self._is_authenticated_page():

            self._set_status(
                "attention",
                (
                    "A sessão JW Player não está "
                    "mais autenticada."
                ),
                self._page.url,
                connected=False,
            )

            raise JWSessionError(
                "A sessão JW Player expirou."
            )

        manifests: list[str] = []
        media_files: list[str] = []

        # ------------------------------------------------------
        # CAPTURA DE REQUESTS
        # ------------------------------------------------------

        def capture(request) -> None:

            url = request.url
            lower = url.lower()

            if (
                ".m3u8" in lower
                and url not in manifests
            ):
                manifests.append(url)

            if (
                ".mp4" in lower
                and url not in media_files
            ):
                media_files.append(url)

        self._page.on(
            "request",
            capture,
        )

        target = (
            "https://dashboard.jwplayer.com/"
            f"p/{self._property_id}/media/{media_id}"
        )

        try:

            # --------------------------------------------------
            # ABRIR MÍDIA
            # --------------------------------------------------

            self._set_status(
                "connected",
                "Abrindo mídia no JW Player.",
                self._page.url,
                connected=True,
            )

            self._page.goto(
                target,
                wait_until="domcontentloaded",
                timeout=self.NAVIGATION_TIMEOUT * 1000,
            )

            self._page.wait_for_timeout(
                3000
            )

            current_url = self._page.url
            current_lower = current_url.lower()

            # --------------------------------------------------
            # SESSÃO EXPIRADA
            # --------------------------------------------------

            if (
                "/login" in current_lower
                or "/signin" in current_lower
            ):

                self._set_status(
                    "attention",
                    "A sessão JW Player expirou.",
                    current_url,
                    connected=False,
                )

                raise JWSessionError(
                    "A sessão JW Player expirou."
                )

            if (
                "challenge" in current_lower
                or "captcha" in current_lower
                or "mfa" in current_lower
            ):

                self._set_status(
                    "attention",
                    (
                        "O JW Player solicitou "
                        "uma nova autenticação."
                    ),
                    current_url,
                    connected=False,
                )

                raise JWSessionError(
                    "A autenticação do JW Player foi interrompida."
                )

            # --------------------------------------------------
            # TENTA INICIAR O PREVIEW
            # --------------------------------------------------

            selectors = (
                'button[aria-label*="Play" i]',
                'button[title*="Play" i]',
                'button:has-text("Play")',
                'button:has-text("Reproduzir")',
                '[data-testid*="play" i]',
            )

            for selector in selectors:

                try:

                    button = (
                        self._page.locator(
                            selector
                        ).first
                    )

                    if (
                        button.count() > 0
                        and button.is_visible(
                            timeout=800
                        )
                    ):

                        button.click(
                            timeout=3000
                        )

                        break

                except Exception:
                    continue

            # --------------------------------------------------
            # TENTA REPRODUZIR ELEMENTO VIDEO
            # --------------------------------------------------

            try:

                video = (
                    self._page.locator(
                        "video"
                    ).first
                )

                if video.count() > 0:

                    video.evaluate(
                        """
                        video => {
                            try {
                                const promise = video.play();

                                if (promise) {
                                    promise.catch(() => {});
                                }
                            } catch (_) {}
                        }
                        """,
                        timeout=2000,
                    )

            except Exception:
                pass

            # --------------------------------------------------
            # AGUARDAR RECURSOS
            # --------------------------------------------------

            self._page.wait_for_timeout(
                10000
            )

            # --------------------------------------------------
            # PERFORMANCE RESOURCE
            # --------------------------------------------------

            try:

                resources = self._page.evaluate(
                    """
                    performance
                        .getEntriesByType('resource')
                        .map(item => item.name)
                    """
                )

                for url in resources:

                    lower = url.lower()

                    if (
                        ".m3u8" in lower
                        and url not in manifests
                    ):
                        manifests.append(url)

                    elif (
                        ".mp4" in lower
                        and url not in media_files
                    ):
                        media_files.append(url)

            except Exception:
                pass

            # --------------------------------------------------
            # VALIDAR HLS
            # --------------------------------------------------

            playable: list[str] = []

            for url in manifests:

                try:

                    response = (
                        self._page.request.get(
                            url,
                            timeout=30000,
                        )
                    )

                    if response.status != 200:
                        continue

                    text = response.text()

                    if (
                        "#EXT-X-STREAM-INF"
                        in text
                        or "#EXTINF"
                        in text
                        or "#EXTM3U"
                        in text
                    ):
                        playable.append(url)

                except Exception:
                    continue

            # --------------------------------------------------
            # ESCOLHER FONTE
            # --------------------------------------------------

            source_url = (
                playable[0]
                if playable
                else (
                    media_files[0]
                    if media_files
                    else None
                )
            )

            if not source_url:

                raise JWSessionError(
                    "Nenhuma fonte HLS ou MP4 foi capturada. "
                    "O login pode estar ativo, mas o player "
                    "não disponibilizou a mídia para captura."
                )

            # Mantém estado conectado.
            self._set_status(
                "connected",
                "Sessão JW Player ativa.",
                self._page.url,
                connected=True,
            )

            return {
                "media_id": media_id,
                "dashboard_url": target,
                "master_url": source_url,
                "captured": (
                    len(manifests)
                    + len(media_files)
                ),
            }

        except JWSessionError:
            raise

        except Exception as exc:

            message = str(
                exc
            ).lower()

            if (
                "target page" in message
                or "browser has been closed" in message
                or "target closed" in message
                or "target closed" in message
                or "page closed" in message
            ):

                self._set_status(
                    "attention",
                    (
                        "O navegador JW Player foi fechado. "
                        "Conecte novamente para continuar."
                    ),
                    connected=False,
                )

                raise JWSessionError(
                    "O navegador JW Player foi fechado. "
                    "Conecte novamente para continuar."
                ) from exc

            raise JWSessionError(
                str(exc)
            ) from exc

        finally:

            if (
                self._page
                and not self._page.is_closed()
            ):

                try:

                    self._page.remove_listener(
                        "request",
                        capture,
                    )

                except Exception:
                    pass

    # ==========================================================
    # FECHAMENTO
    # ==========================================================

    def close(self) -> None:

        try:

            self._executor.submit(
                self._close
            ).result(
                timeout=15
            )

        except Exception:
            pass

        finally:

            try:

                self._executor.shutdown(
                    wait=False,
                    cancel_futures=True,
                )

            except Exception:
                pass

    def _close(self) -> None:

        self._cleanup_browser()

        self._property_id = ""

        self._set_status(
            "disconnected",
            "Sessão encerrada.",
            connected=False,
        )