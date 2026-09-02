import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app as app_module
from src.portfolio.database import Database
from src.portfolio.jwplayer import JWPlayerError, MediaAsset


def make_asset(media_id, publish_date):
    return MediaAsset(
        media_id=media_id,
        title="Aula",
        duration=100.0,
        source_url=None,
        transcript_url=None,
        publish_date=publish_date,
    )


class ClassifyPublishDateTests(unittest.TestCase):
    def test_recent_video_is_eligible(self):
        status, reason, eligible = app_module.classify_publish_date(
            datetime(2025, 6, 1, tzinfo=timezone.utc), date(2024, 1, 1), False,
        )
        self.assertEqual((status, eligible), ("eligible", True))
        self.assertEqual(reason, "within_date_range")

    def test_old_video_is_not_eligible(self):
        status, reason, eligible = app_module.classify_publish_date(
            datetime(2021, 6, 1, tzinfo=timezone.utc), date(2024, 1, 1), False,
        )
        self.assertEqual((status, eligible), ("filtered", False))
        self.assertEqual(reason, "published_before_cutoff")

    def test_same_day_as_cutoff_is_eligible(self):
        status, reason, eligible = app_module.classify_publish_date(
            datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc), date(2024, 1, 1), False,
        )
        self.assertEqual((status, eligible), ("eligible", True))

    def test_missing_date_is_not_eligible_by_default(self):
        status, reason, eligible = app_module.classify_publish_date(
            None, date(2024, 1, 1), False,
        )
        self.assertEqual((status, eligible), ("no_date", False))
        self.assertEqual(reason, "date_not_found")

    def test_missing_date_can_be_opted_in(self):
        status, reason, eligible = app_module.classify_publish_date(
            None, date(2024, 1, 1), True,
        )
        self.assertEqual((status, eligible), ("no_date", True))
        self.assertEqual(reason, "missing_date_included")


class CheckPublishDatesTests(unittest.TestCase):
    def setUp(self):
        self.path = Path("tests/.test_publish_date_filter.db")
        self.path.unlink(missing_ok=True)
        app_module.DATABASE = Database(self.path)

    def tearDown(self):
        self.path.unlink(missing_ok=True)
        for wal in Path("tests").glob(".test_publish_date_filter.db-*"):
            wal.unlink(missing_ok=True)

    def test_no_cutoff_still_fetches_and_stores_publish_date(self):
        # Regressão: sem min_publish_date, o publish_date precisa
        # continuar sendo buscado e salvo (usado pelo filtro de
        # ano da tela e pela exportação) — só a elegibilidade é
        # que não depende da data.
        app_module.DATABASE.import_rows(
            [{"record_id": "r1", "lesson_name": "A", "jwplayer_id": "AAA11111", "keywords": ""}],
            "planilha.xlsx", replace=False,
        )
        with patch.object(
            app_module.JWPlayerClient, "playback",
            return_value=make_asset("AAA11111", datetime(2023, 5, 1, tzinfo=timezone.utc)),
        ) as mock_playback:
            summary = app_module.check_publish_dates(["AAA11111"], "XdfUPSCL", "", False)
            mock_playback.assert_called_once()

        self.assertEqual(summary, {"total": 1, "eligible": 1, "filtered": 0, "no_date": 0, "errors": 0, "will_be_analyzed": 1})

        rows = {r["jwplayer_id"]: r for r in app_module.DATABASE.list_portfolio()}
        self.assertEqual(rows["AAA11111"]["publish_date"], "2023-05-01T00:00:00+00:00")

    def test_no_cutoff_stays_eligible_even_if_fetch_fails(self):
        app_module.DATABASE.import_rows(
            [{"record_id": "r1", "lesson_name": "A", "jwplayer_id": "ERR22222", "keywords": ""}],
            "planilha.xlsx", replace=False,
        )
        with patch.object(
            app_module.JWPlayerClient, "playback",
            side_effect=JWPlayerError("Mídia não encontrada nessa propriedade JW Player."),
        ):
            summary = app_module.check_publish_dates(["ERR22222"], "XdfUPSCL", "", False)

        self.assertEqual(summary["errors"], 1)
        self.assertEqual(summary["eligible"], 1)
        self.assertEqual(summary["will_be_analyzed"], 1)

    def test_falls_back_to_dashboard_when_playback_has_no_pubdate(self):
        app_module.DATABASE.import_rows(
            [{"record_id": "r1", "lesson_name": "A", "jwplayer_id": "NOPUB111", "keywords": ""}],
            "planilha.xlsx", replace=False,
        )
        with patch.object(
            app_module.JWPlayerClient, "playback",
            return_value=make_asset("NOPUB111", None),
        ), patch.object(
            app_module, "fetch_publish_date_from_dashboard",
            return_value=datetime(2022, 7, 4, tzinfo=timezone.utc),
        ) as mock_fallback:
            app_module.check_publish_dates(["NOPUB111"], "XdfUPSCL", "", False)
            mock_fallback.assert_called_once_with("NOPUB111")

        rows = {r["jwplayer_id"]: r for r in app_module.DATABASE.list_portfolio()}
        self.assertEqual(rows["NOPUB111"]["publish_date"], "2022-07-04T00:00:00+00:00")

    def test_no_dashboard_fallback_when_playback_already_has_pubdate(self):
        app_module.DATABASE.import_rows(
            [{"record_id": "r1", "lesson_name": "A", "jwplayer_id": "HASPUB11", "keywords": ""}],
            "planilha.xlsx", replace=False,
        )
        with patch.object(
            app_module.JWPlayerClient, "playback",
            return_value=make_asset("HASPUB11", datetime(2024, 2, 2, tzinfo=timezone.utc)),
        ), patch.object(
            app_module, "fetch_publish_date_from_dashboard",
        ) as mock_fallback:
            app_module.check_publish_dates(["HASPUB11"], "XdfUPSCL", "", False)
            mock_fallback.assert_not_called()

    def test_error_on_one_video_does_not_stop_the_others(self):
        app_module.DATABASE.import_rows(
            [
                {"record_id": "r1", "lesson_name": "Bad", "jwplayer_id": "ERR11111", "keywords": ""},
                {"record_id": "r2", "lesson_name": "Good", "jwplayer_id": "OK111111", "keywords": ""},
            ],
            "planilha.xlsx", replace=False,
        )

        def fake_playback(self, media_id):
            if media_id == "ERR11111":
                raise JWPlayerError("Mídia não encontrada nessa propriedade JW Player.")
            return make_asset(media_id, datetime(2025, 1, 1, tzinfo=timezone.utc))

        with patch.object(app_module.JWPlayerClient, "playback", fake_playback):
            summary = app_module.check_publish_dates(
                ["ERR11111", "OK111111"], "XdfUPSCL", "2024-01-01", False,
            )

        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["errors"], 1)
        self.assertEqual(summary["eligible"], 1)
        self.assertEqual(app_module.DATABASE.eligible_media_for_current_run(), ["OK111111"])

    def test_queue_only_gets_eligible_media(self):
        app_module.DATABASE.import_rows(
            [
                {"record_id": "r1", "lesson_name": "Old", "jwplayer_id": "OLD11111", "keywords": ""},
                {"record_id": "r2", "lesson_name": "New", "jwplayer_id": "NEW11111", "keywords": ""},
            ],
            "planilha.xlsx", replace=False,
        )

        def fake_playback(self, media_id):
            pub = datetime(2021, 1, 1, tzinfo=timezone.utc) if media_id == "OLD11111" else datetime(2025, 1, 1, tzinfo=timezone.utc)
            return make_asset(media_id, pub)

        with patch.object(app_module.JWPlayerClient, "playback", fake_playback):
            app_module.check_publish_dates(["OLD11111", "NEW11111"], "XdfUPSCL", "2024-01-01", False)

        self.assertEqual(app_module.DATABASE.eligible_media_for_current_run(), ["NEW11111"])

        # Exportação: publish_date/filtro aparecem no resultado usado pelo CSV.
        rows = {r["jwplayer_id"]: r for r in app_module.DATABASE.list_portfolio()}
        self.assertEqual(rows["OLD11111"]["filter_status"], "filtered")
        self.assertEqual(rows["OLD11111"]["eligible_for_analysis"], 0)
        self.assertEqual(rows["NEW11111"]["filter_status"], "eligible")
        self.assertEqual(rows["NEW11111"]["eligible_for_analysis"], 1)


class IndividualAnalysisRespectsFilterTests(unittest.TestCase):
    def setUp(self):
        self.path = Path("tests/.test_publish_date_filter_api.db")
        self.path.unlink(missing_ok=True)
        app_module.DATABASE = Database(self.path)
        self.client = TestClient(app_module.app)
        app_module.JW_SESSION.status = lambda: {"state": "connected", "property_id": "XdfUPSCL"}

    def tearDown(self):
        self.path.unlink(missing_ok=True)
        for wal in Path("tests").glob(".test_publish_date_filter_api.db-*"):
            wal.unlink(missing_ok=True)

    def test_individual_analysis_is_blocked_when_not_eligible(self):
        with patch.object(
            app_module.JWPlayerClient, "playback",
            return_value=make_asset("OLD22222", datetime(2020, 1, 1, tzinfo=timezone.utc)),
        ):
            response = self.client.post(
                "/api/analyze-jwplayer",
                json={
                    "jwplayer_id": "OLD22222",
                    "library": "VIDEOSSANAR",
                    "property_id": "XdfUPSCL",
                    "provider": "Gemini",
                    "model": "gemini-flash-latest",
                    "min_publish_date": "2024-01-01",
                    "include_missing_date": False,
                },
            )

        self.assertEqual(response.status_code, 422)
        self.assertIn("não é elegível", response.json()["detail"])

        with app_module.DATABASE.connect() as connection:
            row = connection.execute(
                "SELECT status FROM analyses WHERE jwplayer_id=?", ("OLD22222",),
            ).fetchone()
        self.assertEqual(row["status"], "Pendente")

    def test_individual_analysis_without_filter_is_unaffected(self):
        with patch.object(app_module, "enqueue_jobs", return_value=[]) as mock_enqueue:
            response = self.client.post(
                "/api/analyze-jwplayer",
                json={
                    "jwplayer_id": "ANY11111",
                    "library": "VIDEOSSANAR",
                    "property_id": "XdfUPSCL",
                    "provider": "Gemini",
                    "model": "gemini-flash-latest",
                },
            )
        self.assertEqual(response.status_code, 200)
        mock_enqueue.assert_called_once()


if __name__ == "__main__":
    unittest.main()
