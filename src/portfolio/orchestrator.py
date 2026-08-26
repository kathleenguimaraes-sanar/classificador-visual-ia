from __future__ import annotations

import asyncio
import base64
import json
import time
from pathlib import Path
from typing import Any, Callable, Awaitable

from .classify import classify_frame
from .config import Settings
from .database import Database
from .frames import extract_frames
from .jw_session import JWBrowserSession, JWSessionError
from .jwplayer import JWPlayerClient
from .retry import with_backoff
from .run_logging import RunLogger
from .summarize import summarize_video
from .transcription import transcribe_hls


ACTIVE_STATUSES = (
    "pending",
    "downloading",
    "transcribing",
    "classifying",
    "summarizing",
)


class AsyncVideoPipeline:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        logger: RunLogger,
        jw_session: JWBrowserSession | None = None,
    ):
        self.database = database
        self.settings = settings
        self.logger = logger

        # Sessão Playwright autenticada do JW Player.
        #
        # A instância deve ser compartilhada com a aplicação para que
        # o login realizado em background seja reutilizado durante
        # o processamento dos vídeos.
        self.jw_session = jw_session

        self.semaphore = asyncio.Semaphore(
            settings.max_concurrency
        )

    async def run_pending(self) -> dict[str, int]:
        items = self.database.pipeline_items(ACTIVE_STATUSES)

        self.logger.log(
            "run_started",
            total=len(items),
            concurrency=self.settings.max_concurrency,
            jw_browser_session=self.jw_session is not None,
        )

        await asyncio.gather(
            *(self._guarded(item) for item in items)
        )

        counts = self.database.pipeline_counts()

        self.logger.log(
            "run_finished",
            counts=counts,
        )

        return counts

    async def _guarded(self, item: dict) -> None:
        async with self.semaphore:
            await self._process(item)

    async def _stage(
        self,
        video_id: str,
        stage: str,
        operation: Callable[[], Awaitable[Any]],
    ):
        started = time.perf_counter()

        self.logger.log(
            "stage_started",
            video_id=video_id,
            stage=stage,
        )

        def retry_log(
            attempt: int,
            delay: float,
            exc: Exception,
        ) -> None:
            self.logger.log(
                "stage_retry",
                video_id=video_id,
                stage=stage,
                attempt=attempt,
                delay_seconds=round(delay, 3),
                error=str(exc),
            )

        try:
            result = await with_backoff(
                operation,
                attempts=self.settings.max_retries,
                on_retry=retry_log,
            )

        except Exception as exc:
            self.logger.log(
                "stage_error",
                video_id=video_id,
                stage=stage,
                duration_seconds=round(
                    time.perf_counter() - started,
                    3,
                ),
                error=str(exc),
            )
            raise

        self.logger.log(
            "stage_finished",
            video_id=video_id,
            stage=stage,
            duration_seconds=round(
                time.perf_counter() - started,
                3,
            ),
        )

        return result

    async def _process(self, item: dict) -> None:
        video_id = str(item["id"])

        try:
            state = item["status"]

            frames = self._existing_frames(
                item.get("frames_json")
            )

            source = item.get("url_path")

            # ======================================================
            # DOWNLOAD / CAPTURA DA MÍDIA
            # ======================================================

            if (
                state in {"pending", "downloading"}
                or not source
                or not frames
            ):
                self.database.update_pipeline(
                    video_id,
                    status="downloading",
                    erro_msg=None,
                )

                async def download_stage():
                    return await self._capture_and_extract(
                        video_id
                    )

                source, frames = await self._stage(
                    video_id,
                    "downloading",
                    download_stage,
                )

                next_status = (
                    "transcribing"
                    if self.settings.transcribe
                    else "classifying"
                )

                self.database.update_pipeline(
                    video_id,
                    url_path=source,
                    frames_json=json.dumps(
                        frames,
                        ensure_ascii=False,
                    ),
                    status=next_status,
                    erro_msg=None,
                )

                state = next_status

            # ======================================================
            # TRANSCRIÇÃO
            # ======================================================

            transcript = item.get("transcricao") or ""

            if state == "transcribing":

                async def transcription_stage():
                    return await asyncio.to_thread(
                        transcribe_hls,
                        source,
                        self.settings.data_dir
                        / "artifacts"
                        / video_id,
                        self.settings.whisper_model,
                    )

                transcript = await self._stage(
                    video_id,
                    "transcribing",
                    transcription_stage,
                )

                self.database.update_pipeline(
                    video_id,
                    transcricao=transcript,
                    status="classifying",
                    erro_msg=None,
                )

                state = "classifying"

            # ======================================================
            # CLASSIFICAÇÃO
            # ======================================================

            classification = (
                item.get("classificacao") or ""
            )

            total_input = int(
                item.get("tokens_usados") or 0
            )

            total_output = 0

            existing_cost = float(
                item.get("custo_estimado") or 0
            )

            if state == "classifying":

                async def classification_stage():
                    results = []

                    for frame in frames:
                        result = await asyncio.to_thread(
                            classify_frame,
                            frame,
                            self.settings,
                        )

                        results.append(result)

                    return results

                results = await self._stage(
                    video_id,
                    "classifying",
                    classification_stage,
                )

                classification = json.dumps(
                    [
                        result["classification"]
                        for result in results
                    ],
                    ensure_ascii=False,
                )

                total_input += sum(
                    result.get("input_tokens", 0)
                    for result in results
                )

                total_output += sum(
                    result.get("output_tokens", 0)
                    for result in results
                )

                self.database.update_pipeline(
                    video_id,
                    classificacao=classification,
                    tokens_usados=(
                        total_input + total_output
                    ),
                    status="summarizing",
                    erro_msg=None,
                )

                state = "summarizing"

            # ======================================================
            # RESUMO
            # ======================================================

            if state == "summarizing":

                async def summary_stage():
                    return await asyncio.to_thread(
                        summarize_video,
                        classification,
                        transcript,
                        item.get("lesson_name")
                        or video_id,
                        self.settings,
                    )

                summary = await self._stage(
                    video_id,
                    "summarizing",
                    summary_stage,
                )

                total_input += summary.get(
                    "input_tokens",
                    0,
                )

                total_output += summary.get(
                    "output_tokens",
                    0,
                )

                cost = existing_cost + (
                    total_input
                    * self.settings.input_cost_per_million
                    + total_output
                    * self.settings.output_cost_per_million
                ) / 1_000_000

                self.database.update_pipeline(
                    video_id,
                    resumo=summary["summary"],
                    tokens_usados=(
                        total_input + total_output
                    ),
                    custo_estimado=cost,
                    status="done",
                    erro_msg=None,
                )

        except Exception as exc:
            self.database.update_pipeline(
                video_id,
                status="error",
                erro_msg=str(exc),
            )

            self.logger.log(
                "video_error",
                video_id=video_id,
                stage="pipeline",
                error=str(exc),
            )

    # ==========================================================
    # CAPTURA DA MÍDIA PELO JW PLAYER
    # ==========================================================

    async def _capture_and_extract(
        self,
        video_id: str,
    ) -> tuple[str, list[str]]:

        source_url: str | None = None

        # ------------------------------------------------------
        # CAMINHO PRINCIPAL
        # ------------------------------------------------------
        #
        # Utiliza a sessão Playwright autenticada.
        #
        # Isso significa:
        #
        # Central
        #   ↓
        # JWBrowserSession
        #   ↓
        # navegador headless
        #   ↓
        # JW Player autenticado
        #   ↓
        # mídia
        #   ↓
        # HLS / MP4
        #

        if self.jw_session is not None:

            status = self.jw_session.status()

            if status.get("state") != "connected":
                raise JWSessionError(
                    "A sessão do JW Player não está autenticada. "
                    "Conecte o JW Player antes de iniciar o processamento."
                )

            self.logger.log(
                "jw_browser_capture_started",
                video_id=video_id,
            )

            captured = await asyncio.to_thread(
                self.jw_session.capture_media,
                video_id,
            )

            source_url = (
                captured.get("master_url")
                or captured.get("source_url")
            )

            if not source_url:
                raise JWSessionError(
                    f"Nenhuma fonte de vídeo foi capturada "
                    f"para o JWPlayer ID {video_id}."
                )

            self.logger.log(
                "jw_browser_capture_finished",
                video_id=video_id,
                source_url=source_url,
                captured=captured.get("captured", 0),
            )

        # ------------------------------------------------------
        # FALLBACK
        # ------------------------------------------------------
        #
        # Mantemos o JWPlayerClient para compatibilidade.
        #
        # Ele só será utilizado se nenhuma sessão de navegador
        # tiver sido fornecida ao pipeline.
        #

        else:

            self.logger.log(
                "jw_api_fallback",
                video_id=video_id,
                message=(
                    "JWBrowserSession não configurada. "
                    "Usando JWPlayerClient como fallback."
                ),
            )

            asset = await asyncio.to_thread(
                JWPlayerClient(
                    self.settings.jw_site_id,
                    self.settings.jw_delivery_token,
                ).playback,
                video_id,
            )

            source_url = asset.source_url

            if not source_url:
                raise RuntimeError(
                    "JW Player não retornou uma fonte de vídeo."
                )

        # ======================================================
        # EXTRAÇÃO DOS FRAMES
        # ======================================================

        artifact_directory = (
            self.settings.data_dir
            / "artifacts"
            / video_id
        )

        extracted, _ = await asyncio.to_thread(
            extract_frames,
            source_url,
            artifact_directory,
            self.settings.frame_count,
        )

        paths = self._persist_frames(
            video_id,
            extracted,
        )

        return source_url, paths

    # ==========================================================
    # PERSISTÊNCIA DOS FRAMES
    # ==========================================================

    def _persist_frames(
        self,
        video_id: str,
        frames: list[dict],
    ) -> list[str]:

        directory = (
            self.settings.data_dir
            / "artifacts"
            / video_id
            / "frames"
        )

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        paths: list[str] = []

        for index, frame in enumerate(frames, 1):

            path = (
                directory
                / f"frame_{index:02d}.jpg"
            )

            path.write_bytes(
                base64.b64decode(
                    frame["data"]
                )
            )

            paths.append(
                str(path.resolve())
            )

        return paths

    # ==========================================================
    # FRAMES EXISTENTES
    # ==========================================================

    @staticmethod
    def _existing_frames(
        value: str | None,
    ) -> list[str]:

        if not value:
            return []

        try:
            paths = json.loads(value)

            if (
                paths
                and all(
                    Path(path).exists()
                    for path in paths
                )
            ):
                return paths

            return []

        except (
            TypeError,
            json.JSONDecodeError,
        ):
            return []