import unittest
from pathlib import Path

from src.portfolio.database import Database


class DatabaseTests(unittest.TestCase):
    def test_replace_import_removes_previous_spreadsheet(self):
        path = Path("tests/.test_replace_import.db")
        path.unlink(missing_ok=True)
        try:
            database = Database(path)
            database.import_rows(
                [{"record_id": "old", "lesson_name": "Antiga", "jwplayer_id": "Old12345", "keywords": ""}],
                "antiga.xlsx",
            )
            database.update_analysis("Old12345", status="Processando")

            database.import_rows(
                [{"record_id": "new", "lesson_name": "Nova", "jwplayer_id": "New12345", "keywords": ""}],
                "nova.xlsx",
                replace=True,
            )

            portfolio = database.list_portfolio()
            self.assertEqual([row["lesson_name"] for row in portfolio], ["Nova"])
            self.assertEqual(database.pipeline_counts()["pending"], 1)
            self.assertEqual(database.pipeline_counts()["downloading"], 0)
        finally:
            path.unlink(missing_ok=True)

    def test_legacy_ollama_timeout_is_returned_to_pending_queue(self):
        path = Path("tests/.test_timeout_recovery.db")
        path.unlink(missing_ok=True)
        try:
            database = Database(path)
            database.import_rows(
                [{"record_id": "1", "lesson_name": "A", "jwplayer_id": "Ab12Cd34", "keywords": ""}],
                "base.xlsx",
            )
            legacy_error = (
                "HTTPConnectionPool(host='127.0.0.1', port=11434): "
                "Read timed out. (read timeout=360)"
            )
            database.update_analysis("Ab12Cd34", status="Erro", error_message=legacy_error)
            with database.connect() as connection:
                connection.execute(
                    "UPDATE videos SET status='error', erro_msg=? WHERE jwplayer_id=?",
                    (legacy_error, "Ab12Cd34"),
                )

            Database(path)

            with database.connect() as connection:
                analysis = connection.execute(
                    "SELECT status, error_message FROM analyses WHERE jwplayer_id=?",
                    ("Ab12Cd34",),
                ).fetchone()
                video = connection.execute(
                    "SELECT status, erro_msg FROM videos WHERE jwplayer_id=?",
                    ("Ab12Cd34",),
                ).fetchone()
            self.assertEqual((analysis["status"], analysis["error_message"]), ("Pendente", None))
            self.assertEqual((video["status"], video["erro_msg"]), ("pending", None))
        finally:
            path.unlink(missing_ok=True)

    def test_import_is_idempotent_and_analysis_is_shared(self):
        path = Path("tests/.test_portfolio.db")
        path.unlink(missing_ok=True)
        try:
            database = Database(path)
            rows = [
                {"record_id": "1", "lesson_name": "A", "jwplayer_id": "Ab12Cd34", "keywords": "x"},
                {"record_id": "2", "lesson_name": "B", "jwplayer_id": "Ab12Cd34", "keywords": "y"},
            ]
            first = database.import_rows(rows, "base.xlsx")
            second = database.import_rows(rows, "base.xlsx")
            self.assertEqual(first["new"], 2)
            self.assertEqual(second["unchanged"], 2)
            self.assertEqual(len(database.unique_media()), 1)
            database.update_analysis("Ab12Cd34", status="Concluído", summary="Resumo")
            portfolio = database.list_portfolio()
            self.assertEqual([row["summary"] for row in portfolio], ["Resumo", "Resumo"])
        finally:
            path.unlink(missing_ok=True)

    # TESTE 7 — Persistência de macrotema/microtema/nanotema.
    def test_topic_classification_is_persisted_and_readable(self):
        path = Path("tests/.test_topic_classification.db")
        path.unlink(missing_ok=True)
        try:
            database = Database(path)
            database.import_rows(
                [{"record_id": "1", "lesson_name": "A", "jwplayer_id": "Ab12Cd34", "keywords": ""}],
                "base.xlsx",
            )

            database.update_analysis(
                "Ab12Cd34",
                status="Concluído",
                summary="Resumo sobre insuficiência cardíaca.",
                macrotema="Cardiologia",
                microtema="Insuficiência cardíaca",
                nanotema="Medicamentos",
            )

            portfolio = database.list_portfolio()
            self.assertEqual(portfolio[0]["macrotema"], "Cardiologia")
            self.assertEqual(portfolio[0]["microtema"], "Insuficiência cardíaca")
            self.assertEqual(portfolio[0]["nanotema"], "Medicamentos")

            media = database.get_media("Ab12Cd34")
            self.assertEqual(media["macrotema"], "Cardiologia")
            self.assertEqual(media["microtema"], "Insuficiência cardíaca")
            self.assertEqual(media["nanotema"], "Medicamentos")
        finally:
            path.unlink(missing_ok=True)

    # Registros antigos (sem classificação) continuam funcionando: os
    # campos ficam None em vez de quebrar list_portfolio()/get_media().
    def test_video_without_topic_classification_keeps_working(self):
        path = Path("tests/.test_topic_classification_legacy.db")
        path.unlink(missing_ok=True)
        try:
            database = Database(path)
            database.import_rows(
                [{"record_id": "1", "lesson_name": "A", "jwplayer_id": "Ab12Cd34", "keywords": ""}],
                "base.xlsx",
            )
            database.update_analysis(
                "Ab12Cd34", status="Concluído", summary="Resumo antigo."
            )

            portfolio = database.list_portfolio()
            self.assertIsNone(portfolio[0]["macrotema"])
            self.assertIsNone(portfolio[0]["microtema"])
            self.assertIsNone(portfolio[0]["nanotema"])
        finally:
            path.unlink(missing_ok=True)

    # TESTE 12 (backfill) — vídeos concluídos com resumo mas sem
    # classificação aparecem na fila de backfill; vídeos já
    # classificados ou sem resumo não aparecem.
    def test_media_pending_topic_classification(self):
        path = Path("tests/.test_topic_backfill.db")
        path.unlink(missing_ok=True)
        try:
            database = Database(path)
            database.import_rows(
                [
                    {"record_id": "1", "lesson_name": "A", "jwplayer_id": "Ab12Cd34", "keywords": ""},
                    {"record_id": "2", "lesson_name": "B", "jwplayer_id": "Ef56Gh78", "keywords": ""},
                    {"record_id": "3", "lesson_name": "C", "jwplayer_id": "Ij90Kl12", "keywords": ""},
                ],
                "base.xlsx",
            )

            # Já classificado: não deve entrar no backfill.
            database.update_analysis(
                "Ab12Cd34",
                status="Concluído",
                summary="Resumo A",
                macrotema="Cardiologia",
                microtema="Insuficiência cardíaca",
                nanotema="Medicamentos",
            )

            # Concluído, com resumo, ainda sem classificação: deve
            # entrar no backfill.
            database.update_analysis(
                "Ef56Gh78", status="Concluído", summary="Resumo B"
            )

            # Ainda pendente (sem resumo): não deve entrar no backfill.
            database.update_analysis("Ij90Kl12", status="Pendente")

            pending = database.media_pending_topic_classification()
            self.assertEqual(
                [item["jwplayer_id"] for item in pending], ["Ef56Gh78"]
            )
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
