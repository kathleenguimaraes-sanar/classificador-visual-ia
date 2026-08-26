from __future__ import annotations

import csv
import io
import logging
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.portfolio.ai import (
    AIError,
    AIResponseError,
    analyze_frames,
    validate_ollama_model,
)
from src.portfolio.database import Database, utc_now
from src.portfolio.ingestion import (
    SpreadsheetValidationError,
    read_spreadsheet,
)
from src.portfolio.jw_session import (
    JWBrowserSession,
    JWSessionError,
)
from src.portfolio.frames import extract_frames
from src.portfolio.transcription import transcribe_hls


# ==========================================================
# CONFIGURAÇÃO
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(
    BASE_DIR / ".env",
    override=False,
)

# Não substitui uma configuração de logging já existente no
# processo (ex.: uvicorn) — é um no-op se o root logger já
# tiver handlers configurados.
logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s "
        "%(levelname)s "
        "%(name)s: "
        "%(message)s"
    ),
)

logger = logging.getLogger(
    "cetrus.portfolio"
)

DATA_DIR = Path(
    os.getenv(
        "CETRUS_DATA_DIR",
        BASE_DIR / "data",
    )
)

DATABASE = Database(
    DATA_DIR / "portfolio.db"
)

WEB_DIR = BASE_DIR / "web"


# ==========================================================
# BIBLIOTECAS JW PLAYER
# ==========================================================

JW_LIBRARIES = {

    "DEV": {
        "name": "DEV",
        "property_id": "FvJr6FNj",
        "url": "https://dashboard.jwplayer.com/p/FvJr6FNj/media",
    },

    "EBSERH": {
        "name": "EBSERH",
        "property_id": "UBP82vRQ",
        "url": "https://dashboard.jwplayer.com/p/UBP82vRQ/media",
    },

    "SANARFLIX": {
        "name": "SANARFLIX",
        "property_id": "XK8A5jD7",
        "url": "https://dashboard.jwplayer.com/p/XK8A5jD7/media",
    },

    "VIDEOSSANAR": {
        "name": "VIDEOS SANAR",
        "property_id": "XdfUPSCL",
        "url": "https://dashboard.jwplayer.com/p/XdfUPSCL/media",
    },
}


DEFAULT_JW_LIBRARY = "VIDEOSSANAR"


# Mantido para compatibilidade com partes antigas do projeto.

JW_PROPERTY_ID = JW_LIBRARIES[
    DEFAULT_JW_LIBRARY
]["property_id"]

JW_LIBRARY_URL = JW_LIBRARIES[
    DEFAULT_JW_LIBRARY
]["url"]


# ==========================================================
# CHAVES DAS IAs
# ==========================================================

AI_API_KEYS = {

    "Gemini":
        os.getenv(
            "GEMINI_API_KEY",
            "",
        ).strip(),

    "Claude":
        os.getenv(
            "ANTHROPIC_API_KEY",
            "",
        ).strip(),
}


# ==========================================================
# OLLAMA (SOMENTE LOCAL)
# ==========================================================
#
# Ollama exige um servidor rodando na própria máquina e não
# faz parte da infraestrutura hospedada (Render). Em produção,
# ENABLE_OLLAMA=false remove essa opção sem remover o código —
# continua disponível normalmente em ambiente local.

ENABLE_OLLAMA = str(
    os.getenv(
        "ENABLE_OLLAMA",
        "true",
    )
).strip().casefold() not in {
    "false",
    "0",
    "no",
}

AVAILABLE_PROVIDERS = (

    {
        "Gemini",
        "Claude",
        "Ollama",
    }

    if ENABLE_OLLAMA

    else {
        "Gemini",
        "Claude",
    }
)

AVAILABLE_PROVIDERS_MESSAGE = (
    "Selecione Gemini, Claude ou Ollama."
    if ENABLE_OLLAMA
    else "Selecione Gemini ou Claude."
)


# ==========================================================
# INSTÂNCIAS
# ==========================================================

JW_SESSION = JWBrowserSession()

PROCESSOR = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="video-processing",
)

ANALYSIS_LOCK = threading.Lock()

JOBS: dict[str, dict] = {}

JOBS_LOCK = threading.Lock()

ACTIVE_BATCH_LOCK = threading.Lock()

ACTIVE_BATCH: threading.Event | None = None

CURRENT_JW_LIBRARY = DEFAULT_JW_LIBRARY

CURRENT_JW_PROPERTY_ID = JW_LIBRARIES[
    DEFAULT_JW_LIBRARY
]["property_id"]


# ==========================================================
# EXCEÇÕES
# ==========================================================

class BatchCancelled(Exception):
    pass


# ==========================================================
# LIFESPAN
# ==========================================================

@asynccontextmanager
async def lifespan(_: FastAPI):

    yield

    JW_SESSION.close()

    PROCESSOR.shutdown(
        wait=False,
        cancel_futures=True,
    )


# ==========================================================
# APLICAÇÃO
# ==========================================================

app = FastAPI(
    title="Portfólio de vídeos Cetrus",
    version="2.2.0",
    lifespan=lifespan,
)


app.mount(
    "/assets",
    StaticFiles(
        directory=WEB_DIR,
    ),
    name="assets",
)


# ==========================================================
# MODELOS
# ==========================================================

class LoginRequest(BaseModel):

    library: str = DEFAULT_JW_LIBRARY

    property_id: str = ""

    email: str = ""

    password: str = ""


class ProcessRequest(BaseModel):

    media_ids: list[str] = Field(
        min_length=1,
        max_length=1000,
    )

    provider: str = "Gemini"

    # Uso exclusivamente interno.
    api_key: str = ""

    model: str = "gemini-3.6-flash"

    ollama_url: str = (
        "http://127.0.0.1:11434"
    )

    whisper_model: str = "small"

    analysis_mode: str = "frames"

    frame_count: int = Field(
        default=8,
        ge=4,
        le=16,
    )


class ValidationRequest(BaseModel):

    jwplayer_id: str

    final_category: str

    summary: str = Field(
        max_length=500,
    )

    validated: bool = True


class AnalyzeJWPlayerRequest(BaseModel):

    jwplayer_id: str

    library: str = DEFAULT_JW_LIBRARY

    property_id: str = ""

    provider: str = "Gemini"

    model: str = "gemini-3.6-flash"

    ollama_url: str = (
        "http://127.0.0.1:11434"
    )

    whisper_model: str = "small"

    analysis_mode: str = "frames"

    frame_count: int = Field(
        default=8,
        ge=4,
        le=16,
    )


# ==========================================================
# UTILITÁRIOS JW PLAYER
# ==========================================================

def normalize_library(
    library: str | None,
) -> str:

    key = str(
        library or ""
    ).strip().upper()

    if key not in JW_LIBRARIES:

        raise HTTPException(
            status_code=422,
            detail=(
                "Biblioteca JW Player inválida. "
                "Use DEV, EBSERH, SANARFLIX ou VIDEOSSANAR."
            ),
        )

    return key


def get_library_config(
    library: str | None,
) -> dict:

    key = normalize_library(
        library
    )

    return JW_LIBRARIES[key]


def get_current_library() -> dict:

    return JW_LIBRARIES[
        CURRENT_JW_LIBRARY
    ]


def library_from_property_id(
    property_id: str | None,
) -> str | None:

    value = str(
        property_id or ""
    ).strip()

    if not value:
        return None

    for key, config in JW_LIBRARIES.items():

        if config["property_id"] == value:

            return key

    return None


def update_current_library(
    library: str,
) -> dict:

    global CURRENT_JW_LIBRARY
    global CURRENT_JW_PROPERTY_ID

    config = get_library_config(
        library
    )

    CURRENT_JW_LIBRARY = library

    CURRENT_JW_PROPERTY_ID = config[
        "property_id"
    ]

    return config


# ==========================================================
# CHAVE DA IA
# ==========================================================

def get_provider_api_key(
    provider: str,
) -> str:

    provider = str(
        provider or ""
    ).strip()

    if provider == "Ollama":
        return ""

    if provider not in {
        "Gemini",
        "Claude",
    }:

        raise HTTPException(
            status_code=422,
            detail=(
                "Selecione Gemini, Claude ou Ollama."
            ),
        )

    key = AI_API_KEYS.get(
        provider,
        "",
    )

    if not key:

        env_name = (
            f"{provider.upper()}_API_KEY"
        )

        raise HTTPException(
            status_code=422,
            detail=(
                f"A chave da {provider} "
                f"não está configurada no servidor. "
                f"Configure a variável de ambiente "
                f"{env_name}."
            ),
        )

    return key


# ==========================================================
# CONSTRUIR REQUEST
# ==========================================================

def build_process_request(
    *,
    media_ids: list[str],
    provider: str,
    model: str,
    ollama_url: str,
    whisper_model: str,
    analysis_mode: str,
    frame_count: int,
) -> ProcessRequest:

    provider = str(
        provider or ""
    ).strip()

    if provider not in AVAILABLE_PROVIDERS:

        raise HTTPException(
            status_code=422,
            detail=AVAILABLE_PROVIDERS_MESSAGE,
        )

    if not model.strip():

        raise HTTPException(
            status_code=422,
            detail=(
                "Informe o modelo da IA."
            ),
        )

    return ProcessRequest(

        media_ids=media_ids,

        provider=provider,

        api_key=get_provider_api_key(
            provider
        ),

        model=model.strip(),

        ollama_url=ollama_url.strip(),

        whisper_model=whisper_model.strip(),

        analysis_mode=analysis_mode.strip(),

        frame_count=frame_count,
    )


# ==========================================================
# PÁGINA PRINCIPAL
# ==========================================================

@app.get("/")
def home():

    return FileResponse(
        WEB_DIR / "index.html"
    )


# ==========================================================
# HEALTH CHECK
# ==========================================================
#
# Usado pelo Render (e por qualquer monitor externo) para
# saber se o serviço está de pé. Não consulta banco nem
# JW Player — só confirma que o processo respondeu.

@app.get("/health")
def health():

    return {
        "ok": True
    }


# ==========================================================
# STATUS DOS SERVIÇOS
# ==========================================================
#
# Nunca retorna chave, token, senha ou cookie — apenas se
# cada integração está configurada/conectada.

@app.get("/api/status")
def service_status():

    session_state = JW_SESSION.status().get(
        "state"
    )

    return {

        "gemini":
            bool(
                AI_API_KEYS.get("Gemini")
            ),

        "claude":
            bool(
                AI_API_KEYS.get("Claude")
            ),

        "ollama_enabled":
            ENABLE_OLLAMA,

        "jw_agent":
            session_state == "connected",
    }


# ==========================================================
# ESTATÍSTICAS
# ==========================================================

@app.get("/api/stats")
def stats():

    library = get_current_library()

    return {

        **DATABASE.stats(),

        "jw_library": library["name"],

        "jw_property_id":
            library["property_id"],

        "jw_library_url":
            library["url"],
    }


# ==========================================================
# VÍDEOS
# ==========================================================

@app.get("/api/videos")
def videos(
    search: str = "",
    status: str = "",
    category: str = "",
):

    rows = DATABASE.list_portfolio()

    needle = search.casefold().strip()

    if needle:

        rows = [

            row

            for row in rows

            if needle in " ".join(

                str(
                    row.get(key) or ""
                )

                for key in (
                    "lesson_name",
                    "keywords",
                    "jwplayer_id",
                )

            ).casefold()

        ]

    if status:

        rows = [

            row

            for row in rows

            if (
                row.get("status")
                or "Pendente"
            ) == status

        ]

    if category:

        rows = [

            row

            for row in rows

            if row.get(
                "final_category"
            ) == category

        ]

    return {
        "items": rows,
        "total": len(rows),
    }


# ==========================================================
# IMPORTAÇÃO DA PLANILHA
# ==========================================================

@app.post("/api/import")
async def import_spreadsheet(
    file: UploadFile = File(...),
):

    content = await file.read()

    try:

        rows, report = read_spreadsheet(
            content,
            file.filename or "planilha.xlsx",
        )

    except SpreadsheetValidationError as exc:

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    cancel_active_batch()

    outcome = DATABASE.import_rows(
        rows,
        file.filename or "planilha.xlsx",
        # Não usa replace=True (que apaga fisicamente o
        # histórico): cada importação agora gera sua própria
        # execução (run_id) em `imports`, e a Etapa 4 mostra
        # somente a execução mais recente. O histórico
        # permanece no banco para auditoria/consulta.
        replace=False,
    )

    return {
        **report,
        **outcome,
    }


# ==========================================================
# IMPORTAR E PROCESSAR
# ==========================================================

@app.post("/api/import-and-process")
async def import_and_process(
    file: UploadFile = File(...),

    property_id: str = Form(""),

    library: str = Form(DEFAULT_JW_LIBRARY),

    provider: str = Form(
        "Gemini"
    ),

    model: str = Form(
        "gemini-3.6-flash"
    ),

    ollama_url: str = Form(
        "http://127.0.0.1:11434"
    ),

    whisper_model: str = Form(
        "small"
    ),

    analysis_mode: str = Form(
        "frames"
    ),

    frame_count: int = Form(
        8
    ),
):
    if provider not in AVAILABLE_PROVIDERS:

        raise HTTPException(
            status_code=422,
            detail=AVAILABLE_PROVIDERS_MESSAGE,
        )

    library_key = normalize_library(library)
    library_config = JW_LIBRARIES[library_key]

    if (
        property_id
        and property_id.strip()
        != library_config["property_id"]
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "O Property ID informado não corresponde "
                "à biblioteca selecionada."
            ),
        )

    current_status = JW_SESSION.verify()

    if current_status.get("state") != "connected":
        raise HTTPException(
            status_code=409,
            detail=(
                "A biblioteca JW Player não está autenticada. "
                "Conecte a biblioteca selecionada antes de enviar a planilha."
            ),
        )

    session_property_id = str(
        current_status.get("property_id") or ""
    ).strip()

    if (
        session_property_id
        and session_property_id
        != library_config["property_id"]
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "A sessão JW Player está conectada a outra biblioteca. "
                "Selecione a biblioteca correta e conecte novamente."
            ),
        )

    update_current_library(library_key)

    content = await file.read()

    try:

        rows, report = read_spreadsheet(
            content,
            file.filename or "planilha.xlsx",
        )

    except SpreadsheetValidationError as exc:

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    cancel_active_batch()

    outcome = DATABASE.import_rows(
        rows,
        file.filename or "planilha.xlsx",
        # Não usa replace=True (que apaga fisicamente o
        # histórico): cada importação agora gera sua própria
        # execução (run_id) em `imports`, e a Etapa 4 mostra
        # somente a execução mais recente. O histórico
        # permanece no banco para auditoria/consulta.
        replace=False,
    )

    imported_media = list(
        dict.fromkeys(
            row["jwplayer_id"]
            for row in rows
        )
    )

    states = {

        item["jwplayer_id"]:
            item["status"]

        for item in DATABASE.unique_media()

    }

    pending_media = [

        media_id

        for media_id in imported_media

        if states.get(
            media_id
        ) != "Concluído"

    ]

    request = (

        build_process_request(

            media_ids=pending_media,

            provider=provider,

            model=model,

            ollama_url=ollama_url,

            whisper_model=whisper_model,

            analysis_mode=analysis_mode,

            frame_count=frame_count,

        )

        if pending_media

        else None

    )

    queued = (
        enqueue_jobs(request)
        if request
        else []
    )

    return {

        **report,

        **outcome,

        "pending_media":
            len(pending_media),

        "jobs":
            queued,

        "library":
            CURRENT_JW_LIBRARY,

        "property_id":
            CURRENT_JW_PROPERTY_ID,
    }


# ==========================================================
# LOGIN JW PLAYER
# ==========================================================

@app.post("/api/jw/login")
def jw_login(
    request: LoginRequest,
):
    global CURRENT_JW_LIBRARY
    global CURRENT_JW_PROPERTY_ID

    library_key = normalize_library(request.library)
    library = JW_LIBRARIES[library_key]

    sent_property_id = str(
        request.property_id or ""
    ).strip()

    if (
        sent_property_id
        and sent_property_id != library["property_id"]
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "O Property ID informado não corresponde "
                "à biblioteca selecionada."
            ),
        )

    try:
        update_current_library(library_key)

        result = JW_SESSION.login(
            email=request.email,
            password=request.password,
            property_id=library["property_id"],
        )

        result = dict(result or {})
        result["library"] = library_key
        result["library_name"] = library["name"]
        result["property_id"] = library["property_id"]
        result["library_url"] = library["url"]
        result["connected"] = (
            result.get("state") == "connected"
            or result.get("connected") is True
        )

        return result

    except JWSessionError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Não foi possível conectar ao JW Player: {exc}",
        ) from exc


# ==========================================================
# STATUS JW PLAYER
# ==========================================================

@app.get("/api/jw/status")
def jw_status(
    property_id: str = "",
    library: str = "",
    verify: bool = True,
):
    requested_library_key = (
        normalize_library(library)
        if library
        else CURRENT_JW_LIBRARY
    )

    requested_library = JW_LIBRARIES[
        requested_library_key
    ]

    if (
        property_id
        and property_id.strip()
        != requested_library["property_id"]
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "O Property ID não corresponde à "
                "biblioteca selecionada."
            ),
        )

    try:
        status = (
            JW_SESSION.verify()
            if verify
            else JW_SESSION.status()
        )
    except JWSessionError as exc:
        status = {
            "state": "error",
            "connected": False,
            "message": str(exc),
            "property_id": "",
        }

    status = dict(status or {})

    session_property_id = str(
        status.get("property_id") or ""
    ).strip()

    session_library_key = library_from_property_id(
        session_property_id
    )

    status["selected_library"] = requested_library_key
    status["selected_property_id"] = (
        requested_library["property_id"]
    )
    status["library"] = requested_library_key
    status["library_name"] = requested_library["name"]
    status["library_url"] = requested_library["url"]

    if (
        status.get("state") == "connected"
        and session_property_id
        and session_property_id
        != requested_library["property_id"]
    ):
        status["state"] = "disconnected"
        status["connected"] = False
        status["message"] = (
            "A sessão JW Player está conectada à "
            f"biblioteca {session_library_key or session_property_id}, "
            f"mas a biblioteca selecionada é "
            f"{requested_library['name']}."
        )

    status["property_id"] = (
        session_property_id
        or requested_library["property_id"]
    )

    return status


# ==========================================================
# ATUALIZAR JOB
# ==========================================================

def update_job(
    job_id: str,
    **values,
) -> None:

    with JOBS_LOCK:

        if job_id in JOBS:

            JOBS[job_id].update(
                values
            )


# ==========================================================
# CANCELAR LOTE ATIVO
# ==========================================================

def cancel_active_batch() -> None:

    global ACTIVE_BATCH

    with ACTIVE_BATCH_LOCK:

        if ACTIVE_BATCH is not None:

            ACTIVE_BATCH.cancelled = True

            ACTIVE_BATCH.reason = (
                "Lote substituído por uma nova planilha."
            )

            ACTIVE_BATCH.set()

        ACTIVE_BATCH = None

    with JOBS_LOCK:

        JOBS.clear()


# ==========================================================
# VALIDAR LOTE
# ==========================================================

def ensure_batch_active(
    batch_abort: threading.Event,
) -> None:

    if getattr(
        batch_abort,
        "cancelled",
        False,
    ):

        raise BatchCancelled(
            "Lote substituído por uma nova planilha."
        )


# ==========================================================
# INTERRUPÇÃO JW PLAYER
# ==========================================================

def is_session_interruption(
    exc: Exception,
) -> bool:

    if not isinstance(
        exc,
        JWSessionError,
    ):

        return False

    message = str(
        exc
    ).casefold()

    return any(

        marker in message

        for marker in (

            "conecte uma sessão",

            "navegador jw player foi fechado",

            "sessão jw player expirou",

            "sessão expirou",

            "autenticação",

        )

    )


# ==========================================================
# EXECUTAR JOB
# ==========================================================

def run_media_job(
    job_id: str,
    media_id: str,
    request: ProcessRequest,
    batch_abort: threading.Event,
) -> None:

    with ANALYSIS_LOCK:

        _run_media_job_serial(

            job_id,

            media_id,

            request,

            batch_abort,
        )


# ==========================================================
# EXECUÇÃO SERIAL
# ==========================================================

def _run_media_job_serial(
    job_id: str,
    media_id: str,
    request: ProcessRequest,
    batch_abort: threading.Event,
) -> None:

    if getattr(
        batch_abort,
        "cancelled",
        False,
    ):

        update_job(

            job_id,

            state="cancelled",

            stage="Cancelado",

            message=(
                "Lote substituído "
                "por uma nova planilha."
            ),
        )

        return

    if batch_abort.is_set():

        reason = getattr(

            batch_abort,

            "reason",

            (
                "Corrija a conexão "
                "ou configuração "
                "e tente novamente."
            ),
        )

        DATABASE.update_analysis(

            media_id,

            status="Pendente",

            error_message=None,
        )

        update_job(

            job_id,

            state="paused",

            stage="Aguardando",

            message=(
                f"Lote pausado: {reason}"
            ),
        )

        return

    update_job(

        job_id,

        state="running",

        stage="Validando vídeo",

        message=(
            "Capturando o vídeo no JW Player"
        ),
    )

    DATABASE.update_analysis(

        media_id,

        status="Processando",

        error_message=None,
    )

    work_dir = (
        DATA_DIR
        / "work"
        / media_id
    )

    try:

        # --------------------------------------------------
        # CAPTURAR VÍDEO
        # --------------------------------------------------

        captured = JW_SESSION.capture_media(
            media_id
        )

        ensure_batch_active(
            batch_abort
        )

        master_url = (
            captured.get(
                "master_url"
            )
            or captured.get(
                "url"
            )
        )

        if not master_url:

            raise JWSessionError(
                "Não foi possível obter a URL do vídeo no JW Player."
            )

        update_job(

            job_id,

            stage="Extraindo informações",

            message=(
                "Vídeo validado. "
                "Obtendo informações do JW Player"
            ),
        )

        # --------------------------------------------------
        # FRAMES
        # --------------------------------------------------

        update_job(

            job_id,

            stage="Extraindo frames",

            message=(
                f"Extraindo "
                f"{request.frame_count} "
                f"frames distribuídos"
            ),
        )

        frames, duration = extract_frames(

            master_url,

            work_dir,

            request.frame_count,
        )

        ensure_batch_active(
            batch_abort
        )

        # --------------------------------------------------
        # TRANSCRIÇÃO
        # --------------------------------------------------

        transcript = ""

        if request.analysis_mode == "hybrid":

            update_job(

                job_id,

                stage="Transcrevendo áudio",

                message=(
                    "Transcrevendo áudio "
                    "complementar "
                    "(modo híbrido)"
                ),
            )

            transcript = transcribe_hls(

                master_url,

                work_dir,

                request.whisper_model,
            )

            ensure_batch_active(
                batch_abort
            )

        # --------------------------------------------------
        # TÍTULO
        # --------------------------------------------------

        title = next(

            (

                item["lesson_name"]

                for item
                in DATABASE.unique_media()

                if item["jwplayer_id"]
                == media_id

            ),

            media_id,
        )

        # --------------------------------------------------
        # IA
        # --------------------------------------------------

        update_job(

            job_id,

            stage="Analisando conteúdo visual",

            message=(
                f"Classificando e "
                f"resumindo com "
                f"{request.provider}"
            ),
        )

        if (
            request.provider != "Ollama"
            and not request.api_key
        ):

            raise AIError(

                f"A chave da "
                f"{request.provider} "
                f"não está configurada "
                f"no servidor."
            )

        result = analyze_frames(

            request.provider,

            request.api_key,

            request.model,

            title,

            frames,

            transcript=transcript,

            ollama_url=request.ollama_url,
        )

        ensure_batch_active(
            batch_abort
        )

        update_job(

            job_id,

            stage="Confirmando professor",

            message=(
                "Cruzando evidências visuais "
                "e de fala para confirmar o professor"
            ),
        )

        update_job(

            job_id,

            stage="Gerando resumo",

            message=(
                "Gerando resumo e nome da aula"
            ),
        )

        # --------------------------------------------------
        # SALVAR RESULTADO
        # --------------------------------------------------

        DATABASE.update_analysis(

            media_id,

            status="Concluído",

            ai_category=result[
                "category"
            ],

            final_category=result[
                "category"
            ],

            summary=result[
                "summary"
            ],

            confidence=result[
                "confidence"
            ],

            professor_name=result[
                "professor_name"
            ],

            validation_status="Pendente",

            transcript=transcript,

            source_title=title,

            duration=duration,

            analyzed_at=utc_now(),

            error_message=None,
        )

        update_job(

            job_id,

            state="completed",

            stage="Concluído",

            message=(
                "Processamento concluído"
            ),

            result={

                **result,

                "title":
                    title,

                "duration":
                    duration,
            },
        )

    except BatchCancelled:

        update_job(

            job_id,

            state="cancelled",

            stage="Cancelado",

            message=(
                "Lote substituído "
                "por uma nova planilha."
            ),
        )

    except Exception as exc:

        message = str(
            exc
        )

        if is_session_interruption(
            exc
        ):

            batch_abort.reason = (

                "A sessão do JW Player "
                "foi interrompida. "
                "Reconecte para retomar."
            )

            batch_abort.set()

            DATABASE.update_analysis(

                media_id,

                status="Pendente",

                error_message=message,
            )

            update_job(

                job_id,

                state="paused",

                stage="Aguardando",

                message=(

                    "Processamento pausado. "
                    "Reconecte o JW Player "
                    "e envie novamente "
                    "a planilha para retomar."
                ),
            )

        elif isinstance(
            exc,
            AIResponseError,
        ):

            # A IA respondeu, mas o texto não pôde ser
            # interpretado como o JSON esperado (já foi
            # tentado novamente algumas vezes dentro de
            # analyze_frames, sem sucesso). Isso é uma falha
            # deste vídeo específico, não da configuração do
            # provedor — por isso NÃO pausa o lote: apenas
            # este vídeo fica com status "Erro" e o próximo
            # vídeo da fila continua normalmente.

            logger.warning(
                "Resposta da IA nao pode ser interpretada "
                "como JSON | job_id=%s jwplayer_id=%s "
                "provider=%s model=%s erro=%s "
                "resposta_bruta=%r",
                job_id,
                media_id,
                request.provider,
                request.model,
                message,
                exc.raw_text,
            )

            DATABASE.update_analysis(

                media_id,

                status="Erro",

                error_message=message,
            )

            update_job(

                job_id,

                state="error",

                stage="Erro",

                message=(
                    "Resposta da IA inválida."
                ),
            )

        elif isinstance(
            exc,
            AIError,
        ):

            batch_abort.reason = message

            batch_abort.set()

            DATABASE.update_analysis(

                media_id,

                status="Pendente",

                error_message=message,
            )

            update_job(

                job_id,

                state="paused",

                stage="Aguardando",

                message=(

                    "Lote pausado por "
                    "configuração da IA: "
                    f"{message}"
                ),
            )

        else:

            DATABASE.update_analysis(

                media_id,

                status="Erro",

                error_message=message,
            )

            update_job(

                job_id,

                state="error",

                stage="Erro",

                message=message,
            )

    finally:

        request.api_key = ""


# ==========================================================
# ENFILEIRAR JOBS
# ==========================================================

def enqueue_jobs(
    request: ProcessRequest,
) -> list[dict]:

    global ACTIVE_BATCH

    if request.provider not in AVAILABLE_PROVIDERS:

        raise HTTPException(

            status_code=422,

            detail=AVAILABLE_PROVIDERS_MESSAGE,
        )

    current_status = JW_SESSION.status()

    if current_status.get(
        "state"
    ) != "connected":

        raise HTTPException(

            status_code=409,

            detail=(
                "Conecte o JW Player "
                "antes de processar."
            ),
        )

    request.api_key = (
        get_provider_api_key(
            request.provider
        )
    )

    if request.provider == "Ollama":

        try:

            validate_ollama_model(

                request.ollama_url,

                request.model,
            )

        except AIError as exc:

            raise HTTPException(

                status_code=422,

                detail=str(exc),

            ) from exc

    jobs = []

    batch_abort = (
        threading.Event()
    )

    batch_abort.cancelled = False

    with ACTIVE_BATCH_LOCK:

        ACTIVE_BATCH = (
            batch_abort
        )

    # NÃO chamar DATABASE.ensure_video_for_jwplayer_id() aqui
    # dentro do loop: essa função cria uma NOVA execução
    # (run_id) a cada chamada. Se fosse chamada uma vez por
    # media_id, uma planilha com várias linhas fragmentaria a
    # própria execução em uma linha por vídeo, e a Etapa 4
    # (filtrada pela execução mais recente) passaria a mostrar
    # somente o último vídeo da lista, perdendo os demais
    # resultados já concluídos. Cada chamador de enqueue_jobs()
    # é responsável por garantir a linha/execução UMA vez para
    # todo o conjunto que está enviando (import_rows() já faz
    # isso para a planilha; analyze_jwplayer() faz isso para a
    # análise individual).

    for media_id in dict.fromkeys(
        request.media_ids
    ):

        job_id = uuid.uuid4().hex

        job_data = {

            "id": job_id,

            "media_id": media_id,

            "jwplayer_id": media_id,

            "state": "queued",

            "stage": "Aguardando",

            "message": "Na fila",

            "provider": request.provider,

            "model": request.model,

            "created_at": utc_now(),

        }

        with JOBS_LOCK:

            JOBS[job_id] = (
                job_data
            )

        PROCESSOR.submit(

            run_media_job,

            job_id,

            media_id,

            request.model_copy(
                deep=True
            ),

            batch_abort,
        )

        jobs.append(
            job_data
        )

    request.api_key = ""

    return jobs


# ==========================================================
# ANALISAR JWPLAYER ID INDIVIDUAL
# ==========================================================

@app.post("/api/analyze-jwplayer")
def analyze_jwplayer(
    request: AnalyzeJWPlayerRequest,
):

    jwplayer_id = str(
        request.jwplayer_id or ""
    ).strip()

    if not jwplayer_id:

        raise HTTPException(

            status_code=422,

            detail=(
                "Informe o JWPlayer ID "
                "do vídeo."
            ),
        )

    library_key = normalize_library(
        request.library
    )

    library = JW_LIBRARIES[
        library_key
    ]

    # ------------------------------------------------------
    # VALIDAR PROPERTY ID
    # ------------------------------------------------------

    if request.property_id:

        sent_property_id = str(
            request.property_id
        ).strip()

        if (
            sent_property_id
            != library["property_id"]
        ):

            raise HTTPException(

                status_code=422,

                detail=(
                    "O Property ID informado "
                    "não corresponde à "
                    "biblioteca selecionada."
                ),
            )

    # ------------------------------------------------------
    # VALIDAR SESSÃO
    # ------------------------------------------------------

    session_status = (
        JW_SESSION.status()
    )

    if session_status.get(
        "state"
    ) != "connected":

        raise HTTPException(

            status_code=409,

            detail=(
                "Conecte primeiro "
                "a biblioteca JW Player."
            ),
        )

    session_property_id = str(

        session_status.get(
            "property_id"
        )

        or session_status.get(
            "propertyId"
        )

        or ""

    ).strip()

    # Se o backend conseguiu identificar
    # a biblioteca da sessão, garante que
    # é a mesma escolhida no frontend.

    if (
        session_property_id
        and session_property_id
        != library["property_id"]
    ):

        raise HTTPException(

            status_code=409,

            detail=(

                "A sessão JW Player atual "
                "está conectada à biblioteca "
                f"{session_property_id}, "
                "mas a biblioteca selecionada "
                f"é {library['name']}."
                " Conecte novamente."
            ),
        )

    # ------------------------------------------------------
    # GARANTIR BIBLIOTECA ATUAL
    # ------------------------------------------------------

    update_current_library(
        library_key
    )

    # ------------------------------------------------------
    # CRIAR REQUEST
    # ------------------------------------------------------

    process_request = (
        build_process_request(

            media_ids=[
                jwplayer_id
            ],

            provider=request.provider,

            model=request.model,

            ollama_url=request.ollama_url,

            whisper_model=request.whisper_model,

            analysis_mode=request.analysis_mode,

            frame_count=request.frame_count,

        )
    )

    # ------------------------------------------------------
    # GARANTIR VÍDEO/EXECUÇÃO
    # ------------------------------------------------------

    # Uma análise individual é a sua própria execução (run_id).
    # Chamado uma única vez aqui — não dentro de enqueue_jobs(),
    # que é compartilhado com a planilha (que já garante sua
    # própria execução via DATABASE.import_rows()).
    DATABASE.ensure_video_for_jwplayer_id(
        jwplayer_id
    )

    # ------------------------------------------------------
    # ENFILEIRAR
    # ------------------------------------------------------

    queued = enqueue_jobs(
        process_request
    )

    return {

        "ok": True,

        "message": (
            f"JWPlayer ID "
            f"{jwplayer_id} "
            "enviado para análise."
        ),

        "jwplayer_id":
            jwplayer_id,

        "library":
            library_key,

        "library_name":
            library["name"],

        "property_id":
            library["property_id"],

        "jobs":
            queued,
    }


# ==========================================================
# PROCESSAMENTO DIRETO
# ==========================================================

@app.post("/api/process")
def process(
    request: ProcessRequest,
):

    request.api_key = (
        get_provider_api_key(
            request.provider
        )
    )

    return {
        "jobs":
            enqueue_jobs(
                request
            )
    }


# ==========================================================
# JOBS
# ==========================================================

@app.get("/api/jobs")
def jobs():

    with JOBS_LOCK:

        return {
            "items":
                list(
                    JOBS.values()
                )[-100:]
        }


# ==========================================================
# VALIDAÇÃO
# ==========================================================

@app.post("/api/validate")
def validate(
    request: ValidationRequest,
):

    DATABASE.update_analysis(

        request.jwplayer_id,

        final_category=(
            request.final_category
        ),

        summary=(
            " ".join(
                request.summary.split()
            )
        ),

        validation_status=(
            "Validado"
            if request.validated
            else "Pendente"
        ),
    )

    return {
        "ok": True
    }


# ==========================================================
# EXPORTAÇÃO CSV
# ==========================================================

@app.get("/api/export.csv")
def export_csv():

    output = io.StringIO()

    fields = [

        "lesson_name",

        "final_category",

        "professor_name",

        "summary",

        "jwplayer_id",

        "duration",

        "status",

        "validation_status",

        "confidence",

        "keywords",

    ]

    writer = csv.DictWriter(

        output,

        fieldnames=fields,

        extrasaction="ignore",
    )

    writer.writerow({

        "lesson_name":
            "Nome da aula",

        "final_category":
            "Modelo de aula",

        "professor_name":
            "Professor",

        "summary":
            "Resumo do conteúdo",

        "jwplayer_id":
            "JWPlayer ID",

        "duration":
            "Duração",

        "status":
            "Status",

        "validation_status":
            "Validação",

        "confidence":
            "Confiança",

        "keywords":
            "Palavras-chave",
    })

    writer.writerows(
        DATABASE.list_portfolio()
    )

    return Response(

        content=(
            "\ufeff"
            + output.getvalue()
        ),

        media_type=(
            "text/csv; charset=utf-8"
        ),

        headers={

            "Content-Disposition":
                (
                    'attachment; '
                    'filename='
                    '"portfolio_cetrus.csv"'
                )
        },
    )