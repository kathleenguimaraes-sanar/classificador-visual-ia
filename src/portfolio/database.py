from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


# ==========================================================
# CONSTANTES
# ==========================================================

PIPELINE_STATUSES = {
    "pending",
    "downloading",
    "transcribing",
    "classifying",
    "summarizing",
    "done",
    "error",
}

ANALYSIS_STATUSES = {
    "Pendente",
    "Processando",
    "Concluído",
    "Erro",
}


# ==========================================================
# SCHEMA
# ==========================================================

SCHEMA = """
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    filename TEXT NOT NULL,

    imported_at TEXT NOT NULL,

    total_rows INTEGER NOT NULL DEFAULT 0,

    new_rows INTEGER NOT NULL DEFAULT 0,

    updated_rows INTEGER NOT NULL DEFAULT 0
);


CREATE TABLE IF NOT EXISTS videos (
    record_id TEXT PRIMARY KEY,

    id TEXT,

    lesson_name TEXT NOT NULL,

    jwplayer_id TEXT NOT NULL,

    url_path TEXT,

    status TEXT NOT NULL DEFAULT 'pending',

    classificacao TEXT,

    transcricao TEXT,

    resumo TEXT,

    tokens_usados INTEGER NOT NULL DEFAULT 0,

    custo_estimado REAL NOT NULL DEFAULT 0,

    erro_msg TEXT,

    frames_json TEXT,

    criado_em TEXT,

    atualizado_em TEXT,

    keywords TEXT NOT NULL DEFAULT '',

    source_file TEXT NOT NULL,

    imported_at TEXT NOT NULL,

    updated_at TEXT NOT NULL,

    run_id INTEGER
);


CREATE INDEX IF NOT EXISTS idx_videos_jwplayer
ON videos(jwplayer_id);


CREATE INDEX IF NOT EXISTS idx_videos_status
ON videos(status);


CREATE INDEX IF NOT EXISTS idx_videos_lesson
ON videos(lesson_name);


CREATE TABLE IF NOT EXISTS analyses (
    jwplayer_id TEXT PRIMARY KEY,

    status TEXT NOT NULL DEFAULT 'Pendente',

    ai_category TEXT,

    final_category TEXT,

    summary TEXT,

    confidence REAL,

    validation_status TEXT NOT NULL DEFAULT 'Pendente',

    transcript TEXT,

    source_title TEXT,

    professor_name TEXT,

    duration REAL,

    error_message TEXT,

    analyzed_at TEXT,

    updated_at TEXT NOT NULL
);


CREATE INDEX IF NOT EXISTS idx_analyses_status
ON analyses(status);


CREATE INDEX IF NOT EXISTS idx_analyses_category
ON analyses(final_category);


CREATE INDEX IF NOT EXISTS idx_analyses_validation
ON analyses(validation_status);
"""


# ==========================================================
# DATA / HORA
# ==========================================================

def utc_now() -> str:
    """
    Retorna data/hora UTC em formato ISO.
    """
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


# ==========================================================
# DATABASE
# ==========================================================

class Database:

    def __init__(
        self,
        path: str | Path,
    ):
        self.path = Path(path)

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.initialize()

    # ======================================================
    # CONEXÃO
    # ======================================================

    @contextmanager
    def connect(self):

        connection = sqlite3.connect(
            self.path,
            timeout=30,
        )

        connection.row_factory = sqlite3.Row

        try:

            # ------------------------------------------------
            # SQLite mais resistente a concorrência
            # ------------------------------------------------

            connection.execute(
                "PRAGMA foreign_keys = ON"
            )

            connection.execute(
                "PRAGMA busy_timeout = 30000"
            )

            connection.execute(
                "PRAGMA journal_mode = WAL"
            )

            connection.execute(
                "PRAGMA synchronous = NORMAL"
            )

            yield connection

            connection.commit()

        except Exception:

            connection.rollback()

            raise

        finally:

            connection.close()

    # ======================================================
    # INICIALIZAÇÃO
    # ======================================================

    def initialize(self) -> None:

        with self.connect() as connection:

            connection.executescript(
                SCHEMA
            )

            self._migrate_videos(
                connection
            )
            self._migrate_analyses(
                connection
            )

            self._recover_interrupted_analyses(
                connection
            )

            self._synchronize_pipeline_status(
                connection
            )

    # ======================================================
    # MIGRAÇÃO DA TABELA VIDEOS
    # ======================================================

    @staticmethod
    def _migrate_videos(
        connection: sqlite3.Connection,
    ) -> None:

        existing = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(videos)"
            )
        }

        additions = {

            "id":
                "TEXT",

            "url_path":
                "TEXT",

            "status":
                "TEXT NOT NULL DEFAULT 'pending'",

            "classificacao":
                "TEXT",

            "transcricao":
                "TEXT",

            "resumo":
                "TEXT",

            "tokens_usados":
                "INTEGER NOT NULL DEFAULT 0",

            "custo_estimado":
                "REAL NOT NULL DEFAULT 0",

            "erro_msg":
                "TEXT",

            "frames_json":
                "TEXT",

            "criado_em":
                "TEXT",

            "atualizado_em":
                "TEXT",

            "run_id":
                "INTEGER",
        }

        for column, definition in additions.items():

            if column not in existing:

                connection.execute(
                    f"""
                    ALTER TABLE videos
                    ADD COLUMN {column} {definition}
                    """
                )

        now = utc_now()

        # --------------------------------------------------
        # Corrige valores antigos
        # --------------------------------------------------

        connection.execute(
            """
            UPDATE videos

            SET
                id = COALESCE(
                    NULLIF(id, ''),
                    record_id
                ),

                criado_em = COALESCE(
                    criado_em,
                    imported_at
                ),

                atualizado_em = COALESCE(
                    atualizado_em,
                    updated_at,
                    imported_at,
                    ?
                ),

                status =
                    CASE

                        WHEN status IN (
                            'pending',
                            'downloading',
                            'transcribing',
                            'classifying',
                            'summarizing',
                            'done',
                            'error'
                        )
                        THEN status

                        ELSE 'pending'

                    END
            """,
            (now,),
        )

        # --------------------------------------------------
        # Índices adicionais
        # --------------------------------------------------

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_videos_status
            ON videos(status)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_videos_lesson
            ON videos(lesson_name)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_videos_run
            ON videos(run_id)
            """
        )

        # --------------------------------------------------
        # Vincula vídeos pré-existentes (de antes da criação
        # do conceito de execução/run_id) a uma execução
        # "legado", para que continuem visíveis na Etapa 4
        # até que uma nova execução real os substitua.
        # --------------------------------------------------

        legacy_count = connection.execute(
            """
            SELECT COUNT(*)

            FROM videos

            WHERE run_id IS NULL
            """
        ).fetchone()[0]

        if legacy_count:

            cursor = connection.execute(
                """
                INSERT INTO imports (

                    filename,
                    imported_at,
                    total_rows,
                    new_rows,
                    updated_rows

                )

                VALUES (
                    ?,
                    ?,
                    ?,
                    ?,
                    0
                )
                """,
                (
                    "Execuções anteriores "
                    "(migração para controle "
                    "de execução)",
                    now,
                    legacy_count,
                    legacy_count,
                ),
            )

            legacy_run_id = (
                cursor.lastrowid
            )

            connection.execute(
                """
                UPDATE videos

                SET run_id = ?

                WHERE run_id IS NULL
                """,
                (legacy_run_id,),
            )

    # ======================================================
    # MIGRAÇÃO DA TABELA ANALYSES
    # ======================================================

    @staticmethod
    def _migrate_analyses(
        connection: sqlite3.Connection,
    ) -> None:
        existing = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(analyses)"
            )
        }

        if "professor_name" not in existing:
            connection.execute(
                "ALTER TABLE analyses ADD COLUMN professor_name TEXT"
            )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_analyses_professor
            ON analyses(professor_name)
            """
        )

    # ======================================================
    # RECUPERAR PROCESSAMENTOS INTERROMPIDOS
    # ======================================================

    @staticmethod
    def _recover_interrupted_analyses(
        connection: sqlite3.Connection,
    ) -> None:

        now = utc_now()

        connection.execute(
            """
            UPDATE analyses

            SET
                status = 'Pendente',

                error_message = NULL,

                updated_at = ?

            WHERE
                status = 'Processando'

                OR error_message LIKE
                    '%sessão JW Player%'

                OR error_message LIKE
                    '%navegador JW Player%'

                OR error_message LIKE
                    '%sessão expirou%'

                OR error_message LIKE
                    'OpenAI:%'

                OR error_message LIKE
                    'Gemini:%'

                OR error_message LIKE
                    'Claude:%'

                OR error_message LIKE
                    'Ollama:%'

                OR (
                    error_message LIKE
                        '%127.0.0.1%'

                    AND error_message LIKE
                        '%11434%'

                    AND error_message LIKE
                        '%Read timed out%'
                )
            """,
            (now,),
        )

    # ======================================================
    # SINCRONIZAR PIPELINE
    # ======================================================

    @staticmethod
    def _synchronize_pipeline_status(
        connection: sqlite3.Connection,
    ) -> None:

        now = utc_now()

        connection.execute(
            """
            UPDATE videos

            SET
                status = 'pending',

                erro_msg = NULL,

                atualizado_em = ?

            WHERE jwplayer_id IN (

                SELECT jwplayer_id

                FROM analyses

                WHERE status = 'Pendente'

                  AND error_message IS NULL

            )

            AND status = 'error'
            """,
            (now,),
        )

        # --------------------------------------------------
        # Sincroniza resultados existentes
        # --------------------------------------------------

        connection.execute(
            """
            UPDATE videos

            SET
                classificacao =
                    COALESCE(
                        classificacao,
                        (
                            SELECT
                                final_category

                            FROM analyses a

                            WHERE
                                a.jwplayer_id =
                                    videos.jwplayer_id
                        )
                    ),

                transcricao =
                    COALESCE(
                        transcricao,
                        (
                            SELECT
                                transcript

                            FROM analyses a

                            WHERE
                                a.jwplayer_id =
                                    videos.jwplayer_id
                        )
                    ),

                resumo =
                    COALESCE(
                        resumo,
                        (
                            SELECT
                                summary

                            FROM analyses a

                            WHERE
                                a.jwplayer_id =
                                    videos.jwplayer_id
                        )
                    ),

                erro_msg =
                    COALESCE(
                        erro_msg,
                        (
                            SELECT
                                error_message

                            FROM analyses a

                            WHERE
                                a.jwplayer_id =
                                    videos.jwplayer_id
                        )
                    ),

                atualizado_em = ?

            WHERE EXISTS (

                SELECT 1

                FROM analyses a

                WHERE
                    a.jwplayer_id =
                        videos.jwplayer_id
            )
            """,
            (now,),
        )

        # --------------------------------------------------
        # Status da análise -> pipeline
        # --------------------------------------------------

        connection.execute(
            """
            UPDATE videos

            SET status = 'done'

            WHERE jwplayer_id IN (

                SELECT jwplayer_id

                FROM analyses

                WHERE status = 'Concluído'
            )
            """
        )

        connection.execute(
            """
            UPDATE videos

            SET status = 'error'

            WHERE jwplayer_id IN (

                SELECT jwplayer_id

                FROM analyses

                WHERE status = 'Erro'
            )
            """
        )

        connection.execute(
            """
            UPDATE videos

            SET status = 'pending'

            WHERE jwplayer_id IN (

                SELECT jwplayer_id

                FROM analyses

                WHERE status = 'Processando'
            )
            """
        )

    # ======================================================
    # IMPORTAÇÃO
    # ======================================================

    def import_rows(
        self,
        rows: list[dict],
        filename: str,
        *,
        replace: bool = False,
    ) -> dict:

        now = utc_now()

        created = 0
        updated = 0
        unchanged = 0

        with self.connect() as connection:

            # ------------------------------------------------
            # Substituir portfólio
            # ------------------------------------------------

            if replace:

                connection.execute(
                    "DELETE FROM videos"
                )

                connection.execute(
                    "DELETE FROM analyses"
                )

            # ------------------------------------------------
            # Registrar esta importação como uma nova
            # execução (run_id). Os totais são preenchidos
            # ao final, quando created/updated são conhecidos.
            # ------------------------------------------------

            run_cursor = connection.execute(
                """
                INSERT INTO imports (

                    filename,
                    imported_at,
                    total_rows,
                    new_rows,
                    updated_rows

                )

                VALUES (?, ?, ?, 0, 0)
                """,
                (
                    filename,
                    now,
                    len(rows),
                ),
            )

            run_id = run_cursor.lastrowid

            # ------------------------------------------------
            # Importar registros
            # ------------------------------------------------

            for row in rows:

                record_id = str(
                    row["record_id"]
                ).strip()

                lesson_name = str(
                    row["lesson_name"]
                ).strip()

                jwplayer_id = str(
                    row["jwplayer_id"]
                ).strip()

                keywords = str(
                    row.get("keywords") or ""
                ).strip()

                current = connection.execute(
                    """
                    SELECT
                        lesson_name,
                        jwplayer_id,
                        keywords

                    FROM videos

                    WHERE record_id = ?
                    """,
                    (record_id,),
                ).fetchone()

                values = (
                    lesson_name,
                    jwplayer_id,
                    keywords,
                )

                # --------------------------------------------
                # NOVO
                # --------------------------------------------

                if current is None:

                    connection.execute(
                        """
                        INSERT INTO videos (

                            record_id,
                            id,
                            lesson_name,
                            jwplayer_id,
                            keywords,
                            status,
                            source_file,
                            imported_at,
                            updated_at,
                            criado_em,
                            atualizado_em,
                            run_id

                        )

                        VALUES (
                            ?,
                            ?,
                            ?,
                            ?,
                            ?,
                            'pending',
                            ?,
                            ?,
                            ?,
                            ?,
                            ?,
                            ?
                        )
                        """,
                        (
                            record_id,
                            record_id,
                            lesson_name,
                            jwplayer_id,
                            keywords,
                            filename,
                            now,
                            now,
                            now,
                            now,
                            run_id,
                        ),
                    )

                    self._ensure_analysis(
                        connection,
                        jwplayer_id,
                        now,
                    )

                    created += 1

                # --------------------------------------------
                # ALTERADO
                # --------------------------------------------

                elif tuple(current) != values:

                    connection.execute(
                        """
                        UPDATE videos

                        SET
                            lesson_name = ?,
                            jwplayer_id = ?,
                            keywords = ?,
                            source_file = ?,
                            updated_at = ?,
                            atualizado_em = ?,
                            run_id = ?

                        WHERE record_id = ?
                        """,
                        (
                            lesson_name,
                            jwplayer_id,
                            keywords,
                            filename,
                            now,
                            now,
                            run_id,
                            record_id,
                        ),
                    )

                    self._ensure_analysis(
                        connection,
                        jwplayer_id,
                        now,
                    )

                    updated += 1

                # --------------------------------------------
                # IGUAL
                # --------------------------------------------
                #
                # O conteúdo não mudou, mas o registro ainda
                # pertence a esta execução (ex.: reenvio da
                # mesma planilha) — por isso o run_id também
                # é atualizado, para que continue aparecendo
                # na Etapa 4 como parte da execução atual.

                else:

                    connection.execute(
                        """
                        UPDATE videos

                        SET run_id = ?

                        WHERE record_id = ?
                        """,
                        (
                            run_id,
                            record_id,
                        ),
                    )

                    unchanged += 1

                    self._ensure_analysis(
                        connection,
                        jwplayer_id,
                        now,
                    )

            # ------------------------------------------------
            # Atualizar contagens da execução
            # ------------------------------------------------

            connection.execute(
                """
                UPDATE imports

                SET
                    new_rows = ?,
                    updated_rows = ?

                WHERE id = ?
                """,
                (
                    created,
                    updated,
                    run_id,
                ),
            )

        return {
            "total": len(rows),
            "new": created,
            "updated": updated,
            "unchanged": unchanged,
        }

    # ======================================================
    # GARANTIR ANÁLISE
    # ======================================================

    @staticmethod
    def _ensure_analysis(
        connection: sqlite3.Connection,
        jwplayer_id: str,
        now: str,
    ) -> None:

        connection.execute(
            """
            INSERT OR IGNORE INTO analyses (

                jwplayer_id,
                status,
                validation_status,
                updated_at

            )

            VALUES (
                ?,
                'Pendente',
                'Pendente',
                ?
            )
            """,
            (
                jwplayer_id,
                now,
            ),
        )

    # ======================================================
    # GARANTIR VÍDEO (ANÁLISE INDIVIDUAL POR JWPLAYER ID)
    # ======================================================
    #
    # list_portfolio() é ancorada em `videos` (FROM videos
    # LEFT JOIN analyses). Uma análise individual que nunca
    # passou por import_rows() não tem linha em `videos` e,
    # por isso, nunca aparece na Etapa 4 mesmo com o resultado
    # já salvo em `analyses`. Este método garante essa linha,
    # reaproveitando a mesma tabela/campo jwplayer_id usados
    # pela importação via planilha, sem criar estrutura paralela.
    #
    # Cada chamada também registra sua própria execução em
    # `imports` (o mesmo mecanismo de execução usado pela
    # planilha) e marca o vídeo com esse run_id, para que a
    # Etapa 4 passe a exibir somente esta análise individual.

    def ensure_video_for_jwplayer_id(
        self,
        jwplayer_id: str,
    ) -> None:

        jwplayer_id = str(
            jwplayer_id
        ).strip()

        now = utc_now()

        with self.connect() as connection:

            run_cursor = connection.execute(
                """
                INSERT INTO imports (

                    filename,
                    imported_at,
                    total_rows,
                    new_rows,
                    updated_rows

                )

                VALUES (?, ?, 1, 0, 0)
                """,
                (
                    f"Análise individual: {jwplayer_id}",
                    now,
                ),
            )

            run_id = run_cursor.lastrowid

            reattached = connection.execute(
                """
                UPDATE videos

                SET run_id = ?

                WHERE jwplayer_id = ?
                """,
                (
                    run_id,
                    jwplayer_id,
                ),
            )

            self._ensure_analysis(
                connection,
                jwplayer_id,
                now,
            )

            if reattached.rowcount > 0:

                connection.execute(
                    """
                    UPDATE imports

                    SET updated_rows = 1

                    WHERE id = ?
                    """,
                    (run_id,),
                )

                return

            connection.execute(
                """
                UPDATE imports

                SET new_rows = 1

                WHERE id = ?
                """,
                (run_id,),
            )

            record_id = (
                f"jwplayer:{jwplayer_id}"
            )

            connection.execute(
                """
                INSERT OR IGNORE INTO videos (

                    record_id,
                    id,
                    lesson_name,
                    jwplayer_id,
                    keywords,
                    status,
                    source_file,
                    imported_at,
                    updated_at,
                    criado_em,
                    atualizado_em,
                    run_id

                )

                VALUES (
                    ?,
                    ?,
                    ?,
                    ?,
                    '',
                    'pending',
                    ?,
                    ?,
                    ?,
                    ?,
                    ?,
                    ?
                )
                """,
                (
                    record_id,
                    record_id,
                    jwplayer_id,
                    jwplayer_id,
                    "Análise individual",
                    now,
                    now,
                    now,
                    now,
                    run_id,
                ),
            )

    # ======================================================
    # LISTAR PORTFÓLIO
    # ======================================================

    def list_portfolio(
        self,
    ) -> list[dict]:

        query = """
        SELECT

            v.record_id,

            v.lesson_name,

            v.jwplayer_id,

            v.keywords,

            a.status,

            a.ai_category,

            a.final_category,

            a.summary,

            a.confidence,

            a.validation_status,

            a.transcript,

            a.source_title,

            a.professor_name,

            a.duration,

            a.analyzed_at,

            a.error_message

        FROM videos v

        LEFT JOIN analyses a
            ON a.jwplayer_id =
                v.jwplayer_id

        WHERE v.run_id = (
            SELECT MAX(id) FROM imports
        )

        ORDER BY
            v.lesson_name COLLATE NOCASE
        """

        with self.connect() as connection:

            return [
                dict(row)

                for row in connection.execute(
                    query
                )
            ]

    # ======================================================
    # MÍDIAS ÚNICAS
    # ======================================================

    def unique_media(
        self,
        statuses: tuple[str, ...] | None = None,
    ) -> list[dict]:

        query = """
        SELECT

            v.jwplayer_id,

            MIN(v.lesson_name)
                AS lesson_name,

            COUNT(*)
                AS record_count,

            a.status,

            a.transcript,

            a.summary

        FROM videos v

        JOIN analyses a
            ON a.jwplayer_id =
                v.jwplayer_id
        """

        params: tuple = ()

        if statuses:

            placeholders = ",".join(
                "?"
                for _ in statuses
            )

            query += (
                f" WHERE a.status "
                f"IN ({placeholders})"
            )

            params = statuses

        query += """
        GROUP BY
            v.jwplayer_id,
            a.status,
            a.transcript,
            a.summary

        ORDER BY
            lesson_name COLLATE NOCASE
        """

        with self.connect() as connection:

            return [
                dict(row)

                for row in connection.execute(
                    query,
                    params,
                )
            ]

    # ======================================================
    # ATUALIZAR ANÁLISE
    # ======================================================

    def update_analysis(
        self,
        jwplayer_id: str,
        **values,
    ) -> None:

        allowed = {
            "status",
            "ai_category",
            "final_category",
            "summary",
            "confidence",
            "validation_status",
            "transcript",
            "source_title",
            "professor_name",
            "duration",
            "error_message",
            "analyzed_at",
        }

        clean = {
            key: value

            for key, value in values.items()

            if key in allowed
        }

        now = utc_now()

        clean["updated_at"] = now

        with self.connect() as connection:

            # ------------------------------------------------
            # Garantir registro
            # ------------------------------------------------

            self._ensure_analysis(
                connection,
                jwplayer_id,
                now,
            )

            # ------------------------------------------------
            # Atualizar análise
            # ------------------------------------------------

            assignments = ", ".join(
                f"{key} = ?"

                for key in clean
            )

            connection.execute(
                f"""
                UPDATE analyses

                SET {assignments}

                WHERE jwplayer_id = ?
                """,
                (
                    *clean.values(),
                    jwplayer_id,
                ),
            )

            # ------------------------------------------------
            # Status pipeline
            # ------------------------------------------------

            pipeline_status = {
                "Pendente":
                    "pending",

                "Processando":
                    "downloading",

                "Concluído":
                    "done",

                "Erro":
                    "error",
            }.get(
                values.get("status")
            )

            # ------------------------------------------------
            # Campos espelhados
            # ------------------------------------------------

            mirrored = {

                "classificacao":
                    values.get(
                        "final_category"
                    )
                    or values.get(
                        "ai_category"
                    ),

                "transcricao":
                    values.get(
                        "transcript"
                    ),

                "resumo":
                    values.get(
                        "summary"
                    ),

                "erro_msg":
                    values.get(
                        "error_message"
                    ),
            }

            if pipeline_status:

                mirrored["status"] = (
                    pipeline_status
                )

            mirror_clean = {
                key: value

                for key, value
                in mirrored.items()

                if (
                    key == "erro_msg"
                    or value is not None
                )
            }

            mirror_clean[
                "atualizado_em"
            ] = now

            assignments = ", ".join(
                f"{key} = ?"

                for key in mirror_clean
            )

            connection.execute(
                f"""
                UPDATE videos

                SET {assignments}

                WHERE jwplayer_id = ?
                """,
                (
                    *mirror_clean.values(),
                    jwplayer_id,
                ),
            )

    # ======================================================
    # PIPELINE
    # ======================================================

    def pipeline_items(
        self,
        statuses: tuple[str, ...] = (
            "pending",
        ),
    ) -> list[dict]:

        if not statuses:

            return []

        invalid = set(statuses) - PIPELINE_STATUSES

        if invalid:

            raise ValueError(
                "Status de pipeline inválido: "
                + ", ".join(
                    sorted(invalid)
                )
            )

        placeholders = ",".join(
            "?"
            for _ in statuses
        )

        query = f"""
        SELECT

            jwplayer_id AS id,

            MIN(lesson_name)
                AS lesson_name,

            MIN(url_path)
                AS url_path,

            MIN(status)
                AS status,

            MIN(classificacao)
                AS classificacao,

            MIN(transcricao)
                AS transcricao,

            MIN(resumo)
                AS resumo,

            MAX(tokens_usados)
                AS tokens_usados,

            MAX(custo_estimado)
                AS custo_estimado,

            MIN(erro_msg)
                AS erro_msg,

            MIN(frames_json)
                AS frames_json

        FROM videos

        WHERE status IN (
            {placeholders}
        )

        GROUP BY
            jwplayer_id

        ORDER BY
            lesson_name COLLATE NOCASE
        """

        with self.connect() as connection:

            return [
                dict(row)

                for row in connection.execute(
                    query,
                    statuses,
                )
            ]

    # ======================================================
    # ATUALIZAR PIPELINE
    # ======================================================

    def update_pipeline(
        self,
        video_id: str,
        **values,
    ) -> None:

        allowed = {
            "url_path",
            "status",
            "classificacao",
            "transcricao",
            "resumo",
            "tokens_usados",
            "custo_estimado",
            "erro_msg",
            "frames_json",
        }

        clean = {
            key: value

            for key, value
            in values.items()

            if key in allowed
        }

        if not clean:

            return

        if (
            "status" in clean
            and clean["status"]
            not in PIPELINE_STATUSES
        ):

            raise ValueError(
                "Status de pipeline inválido: "
                f"{clean['status']}"
            )

        clean["atualizado_em"] = utc_now()

        assignments = ", ".join(
            f"{key} = ?"

            for key in clean
        )

        with self.connect() as connection:

            connection.execute(
                f"""
                UPDATE videos

                SET {assignments}

                WHERE
                    jwplayer_id = ?

                    OR id = ?

                    OR record_id = ?
                """,
                (
                    *clean.values(),
                    video_id,
                    video_id,
                    video_id,
                ),
            )

    # ======================================================
    # RETRY DOS ERROS
    # ======================================================

    def retry_errors(self) -> int:

        now = utc_now()

        with self.connect() as connection:

            cursor = connection.execute(
                """
                UPDATE videos

                SET
                    status = 'pending',

                    erro_msg = NULL,

                    atualizado_em = ?

                WHERE status = 'error'
                """,
                (now,),
            )

            # Também recupera a tabela de análises.
            connection.execute(
                """
                UPDATE analyses

                SET
                    status = 'Pendente',

                    error_message = NULL,

                    updated_at = ?

                WHERE status = 'Erro'
                """,
                (now,),
            )

            return cursor.rowcount

    # ======================================================
    # CONTADORES DO PIPELINE
    # ======================================================

    def pipeline_counts(
        self,
    ) -> dict[str, int]:

        with self.connect() as connection:

            rows = connection.execute(
                """
                SELECT

                    status,

                    COUNT(
                        DISTINCT jwplayer_id
                    ) AS total

                FROM videos

                GROUP BY status
                """
            )

            counts = {
                status: 0

                for status
                in sorted(
                    PIPELINE_STATUSES
                )
            }

            counts.update(
                {
                    row["status"]:
                        row["total"]

                    for row in rows
                }
            )

            return counts

    # ======================================================
    # ESTATÍSTICAS
    # ======================================================

    def stats(
        self,
    ) -> dict:

        with self.connect() as connection:

            row = connection.execute(
                """
                SELECT

                    COUNT(*)
                        AS records,

                    COUNT(
                        DISTINCT v.jwplayer_id
                    ) AS media,

                    COALESCE(
                        SUM(
                            CASE
                                WHEN a.status =
                                    'Concluído'
                                THEN 1
                                ELSE 0
                            END
                        ),
                        0
                    ) AS analyzed_records,

                    COUNT(
                        DISTINCT CASE

                            WHEN a.status =
                                'Concluído'

                            THEN v.jwplayer_id

                        END
                    ) AS analyzed_media,

                    COUNT(
                        DISTINCT CASE

                            WHEN a.validation_status =
                                'Validado'

                            THEN v.jwplayer_id

                        END
                    ) AS validated_media

                FROM videos v

                LEFT JOIN analyses a
                    ON a.jwplayer_id =
                        v.jwplayer_id
                """
            ).fetchone()

            return dict(row)

    # ======================================================
    # BUSCAR UMA MÍDIA
    # ======================================================

    def get_media(
        self,
        jwplayer_id: str,
    ) -> dict | None:

        query = """
        SELECT

            v.record_id,

            v.lesson_name,

            v.jwplayer_id,

            v.keywords,

            v.status AS pipeline_status,

            a.status,

            a.ai_category,

            a.final_category,

            a.summary,

            a.confidence,

            a.validation_status,

            a.transcript,

            a.source_title,

            a.professor_name,

            a.duration,

            a.analyzed_at,

            a.error_message

        FROM videos v

        LEFT JOIN analyses a
            ON a.jwplayer_id =
                v.jwplayer_id

        WHERE v.jwplayer_id = ?

        LIMIT 1
        """

        with self.connect() as connection:

            row = connection.execute(
                query,
                (jwplayer_id,),
            ).fetchone()

            return (
                dict(row)
                if row
                else None
            )

    # ======================================================
    # HISTÓRICO DE IMPORTAÇÕES
    # ======================================================

    def import_history(
        self,
        limit: int = 20,
    ) -> list[dict]:

        limit = max(
            1,
            min(
                int(limit),
                100,
            ),
        )

        with self.connect() as connection:

            rows = connection.execute(
                """
                SELECT

                    id,

                    filename,

                    imported_at,

                    total_rows,

                    new_rows,

                    updated_rows

                FROM imports

                ORDER BY
                    id DESC

                LIMIT ?
                """,
                (limit,),
            )

            return [
                dict(row)

                for row in rows
            ]