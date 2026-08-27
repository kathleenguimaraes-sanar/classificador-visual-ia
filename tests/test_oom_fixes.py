import unittest
from unittest.mock import patch

import app as app_module


class PruneJobsLockedTests(unittest.TestCase):
    """
    Regressão: JOBS era um dict global que só era zerado por
    inteiro quando uma planilha nova substituía um lote ativo.
    Análises individuais e /api/start-eligible não passavam por
    essa limpeza, então JOBS crescia sem limite pela vida inteira
    do processo (uma das causas do OOM no Render).
    """

    def setUp(self):
        self._original_jobs = dict(app_module.JOBS)
        app_module.JOBS.clear()

    def tearDown(self):
        app_module.JOBS.clear()
        app_module.JOBS.update(self._original_jobs)

    def test_prune_keeps_at_most_max_jobs_history(self):
        with app_module.JOBS_LOCK:
            for i in range(app_module.MAX_JOBS_HISTORY + 50):
                app_module.JOBS[f"job-{i}"] = {"id": f"job-{i}"}
            app_module._prune_jobs_locked()

        self.assertEqual(len(app_module.JOBS), app_module.MAX_JOBS_HISTORY)

    def test_prune_discards_oldest_and_keeps_newest(self):
        with app_module.JOBS_LOCK:
            for i in range(app_module.MAX_JOBS_HISTORY + 10):
                app_module.JOBS[f"job-{i}"] = {"id": f"job-{i}"}
            app_module._prune_jobs_locked()

        self.assertNotIn("job-0", app_module.JOBS)
        self.assertNotIn("job-9", app_module.JOBS)
        last_id = f"job-{app_module.MAX_JOBS_HISTORY + 9}"
        self.assertIn(last_id, app_module.JOBS)

    def test_prune_is_a_no_op_below_the_limit(self):
        with app_module.JOBS_LOCK:
            for i in range(5):
                app_module.JOBS[f"job-{i}"] = {"id": f"job-{i}"}
            app_module._prune_jobs_locked()

        self.assertEqual(len(app_module.JOBS), 5)


class EnqueueJobsPrunesJobsTests(unittest.TestCase):
    """
    Confirma que a poda é de fato acionada no ponto real onde
    JOBS cresce: a cada job criado por enqueue_jobs().
    """

    def setUp(self):
        self._original_jobs = dict(app_module.JOBS)
        app_module.JOBS.clear()

    def tearDown(self):
        app_module.JOBS.clear()
        app_module.JOBS.update(self._original_jobs)

    def test_enqueue_jobs_never_exceeds_max_history(self):
        with app_module.JOBS_LOCK:
            for i in range(app_module.MAX_JOBS_HISTORY - 1):
                app_module.JOBS[f"old-job-{i}"] = {"id": f"old-job-{i}"}

        request = app_module.ProcessRequest(
            media_ids=["AAA11111", "BBB11111", "CCC11111"],
            provider="Gemini",
            model="gemini-3.6-flash",
            frame_count=4,
        )

        with patch.object(
            app_module.JW_SESSION, "status",
            return_value={"state": "connected", "property_id": "XdfUPSCL"},
        ), patch.object(
            app_module, "get_provider_api_key", return_value="fake-key",
        ), patch.object(
            app_module.PROCESSOR, "submit",
        ) as mock_submit:
            app_module.enqueue_jobs(request)

        # 3 jobs novos entrariam, o que ultrapassaria MAX_JOBS_HISTORY
        # em 2 se não houvesse poda.
        self.assertLessEqual(len(app_module.JOBS), app_module.MAX_JOBS_HISTORY)
        self.assertEqual(mock_submit.call_count, 3)


if __name__ == "__main__":
    unittest.main()
