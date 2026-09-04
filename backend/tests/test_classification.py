import json
import unittest
from unittest.mock import patch

from src.portfolio.ai import (
    AIError,
    AIResponseError,
    DEFAULT_TOPIC_CLASSIFICATION,
    classification_prompt,
    classify_topics,
    parse_classification_result,
)


CARDIOLOGY_SUMMARY = (
    "A aula aborda a farmacologia cardiovascular focada no tratamento da "
    "insuficiência cardíaca congestiva (ICC). São discutidas as respostas "
    "fisiológicas compensatórias e o mecanismo de ação dos fármacos "
    "inotrópicos positivos, com destaque para a digoxina. Além disso, o "
    "conteúdo apresenta os medicamentos sem efeito inotrópico positivo, "
    "incluindo diuréticos, inibidores da ECA, bloqueadores de receptores "
    "de angiotensina e espironolactona."
)

NEUROLOGY_SUMMARY = (
    "A aula apresenta o diagnóstico do acidente vascular cerebral (AVC) "
    "isquêmico, detalhando os principais exames de imagem utilizados e "
    "os critérios clínicos para confirmar o diagnóstico rapidamente."
)

SURGERY_SUMMARY = (
    "A aula demonstra passo a passo a técnica cirúrgica de sutura em "
    "ferimentos, apresentando os instrumentos utilizados e os cuidados "
    "durante o procedimento."
)

GENERIC_SUMMARY = "Conteúdo não identificado nos frames analisados."

MULTI_SUBJECT_SUMMARY = (
    "A aula cita brevemente hipertensão e diabetes, mas o foco central e "
    "predominante é a explicação detalhada da fisiopatologia da asma "
    "brônquica em pacientes pediátricos."
)


class ClassificationPromptTests(unittest.TestCase):
    def test_prompt_includes_summary_and_hierarchy_rules(self):
        prompt = classification_prompt(CARDIOLOGY_SUMMARY)
        self.assertIn("digoxina", prompt)
        self.assertIn("Macrotema", prompt)
        self.assertIn("Microtema", prompt)
        self.assertIn("Nanotema", prompt)
        self.assertIn("Não identificado", prompt)


class ParseClassificationResultTests(unittest.TestCase):
    def test_valid_json(self):
        result = parse_classification_result(
            json.dumps(
                {
                    "macrotema": "Cardiologia",
                    "microtema": "Insuficiência cardíaca",
                    "nanotema": "Medicamentos",
                }
            )
        )
        self.assertEqual(
            result,
            {
                "macrotema": "Cardiologia",
                "microtema": "Insuficiência cardíaca",
                "nanotema": "Medicamentos",
            },
        )

    def test_strips_markdown_fences(self):
        result = parse_classification_result(
            '```json\n{"macrotema": "Neurologia", "microtema": "AVC", '
            '"nanotema": "Diagnóstico"}\n```'
        )
        self.assertEqual(result["macrotema"], "Neurologia")
        self.assertEqual(result["nanotema"], "Diagnóstico")

    def test_missing_fields_default_to_nao_identificado(self):
        result = parse_classification_result('{"macrotema": "Cardiologia"}')
        self.assertEqual(result["macrotema"], "Cardiologia")
        self.assertEqual(result["microtema"], "Não identificado")
        self.assertEqual(result["nanotema"], "Não identificado")

    def test_empty_field_defaults_to_nao_identificado(self):
        result = parse_classification_result(
            '{"macrotema": "Cardiologia", "microtema": "  ", "nanotema": null}'
        )
        self.assertEqual(result["microtema"], "Não identificado")
        self.assertEqual(result["nanotema"], "Não identificado")

    def test_invalid_json_raises_ai_response_error(self):
        with self.assertRaises(AIResponseError):
            parse_classification_result("isto não é json")

    def test_empty_text_raises_ai_response_error(self):
        with self.assertRaises(AIResponseError):
            parse_classification_result("")

    def test_non_object_json_raises_ai_response_error(self):
        with self.assertRaises(AIResponseError):
            parse_classification_result("[1, 2, 3]")


class ClassifyTopicsTests(unittest.TestCase):
    def _mock_response(self, macrotema, microtema, nanotema):
        return json.dumps(
            {
                "macrotema": macrotema,
                "microtema": microtema,
                "nanotema": nanotema,
            }
        )

    def test_empty_summary_returns_default_without_calling_provider(self):
        with patch("src.portfolio.ai._request_provider_text") as mocked:
            result = classify_topics("Gemini", "key", "model", "   ")

        mocked.assert_not_called()
        self.assertEqual(result, DEFAULT_TOPIC_CLASSIFICATION)

    # TESTE 1 — Cardiologia: foco é o tratamento medicamentoso, não a
    # digoxina isolada.
    def test_cardiology_pharmacology_summary(self):
        fake_text = self._mock_response(
            "Cardiologia", "Insuficiência cardíaca", "Medicamentos"
        )
        with patch(
            "src.portfolio.ai._request_provider_text",
            return_value=fake_text,
        ) as mocked:
            result = classify_topics(
                "Gemini", "key", "gemini-flash-latest", CARDIOLOGY_SUMMARY
            )

        mocked.assert_called_once()
        self.assertEqual(result["macrotema"], "Cardiologia")
        self.assertEqual(result["microtema"], "Insuficiência cardíaca")
        self.assertEqual(result["nanotema"], "Medicamentos")

    # TESTE 2 — Neurologia / AVC.
    def test_neurology_stroke_summary(self):
        fake_text = self._mock_response("Neurologia", "AVC", "Diagnóstico")
        with patch(
            "src.portfolio.ai._request_provider_text",
            return_value=fake_text,
        ):
            result = classify_topics(
                "Gemini", "key", "gemini-flash-latest", NEUROLOGY_SUMMARY
            )

        self.assertEqual(result["macrotema"], "Neurologia")
        self.assertEqual(result["microtema"], "AVC")
        self.assertIn(result["nanotema"], {"Diagnóstico", "Exame"})

    # TESTE 3 — Procedimento / técnica cirúrgica.
    def test_surgical_technique_summary(self):
        fake_text = self._mock_response(
            "Cirurgia", "Sutura de ferimentos", "Técnica"
        )
        with patch(
            "src.portfolio.ai._request_provider_text",
            return_value=fake_text,
        ):
            result = classify_topics(
                "Gemini", "key", "gemini-flash-latest", SURGERY_SUMMARY
            )

        self.assertEqual(result["macrotema"], "Cirurgia")
        self.assertTrue(result["microtema"])
        self.assertIn(result["nanotema"], {"Técnica", "Procedimento"})

    # TESTE 4 — Resumo insuficiente: não deve inventar classificação.
    def test_generic_summary_returns_not_identified(self):
        fake_text = self._mock_response(
            "Não identificado", "Não identificado", "Não identificado"
        )
        with patch(
            "src.portfolio.ai._request_provider_text",
            return_value=fake_text,
        ):
            result = classify_topics(
                "Gemini", "key", "gemini-flash-latest", GENERIC_SUMMARY
            )

        self.assertEqual(result, DEFAULT_TOPIC_CLASSIFICATION)

    # TESTE 5 — Múltiplos assuntos: usa o foco predominante.
    def test_multiple_subjects_uses_predominant_focus(self):
        fake_text = self._mock_response(
            "Pneumologia", "Asma brônquica", "Fisiopatologia"
        )
        with patch(
            "src.portfolio.ai._request_provider_text",
            return_value=fake_text,
        ):
            result = classify_topics(
                "Gemini", "key", "gemini-flash-latest", MULTI_SUBJECT_SUMMARY
            )

        self.assertEqual(result["macrotema"], "Pneumologia")
        self.assertEqual(result["microtema"], "Asma brônquica")

    # TESTE 6 — JSON inválido: o sistema não deve quebrar.
    def test_invalid_json_response_does_not_raise(self):
        with patch(
            "src.portfolio.ai._request_provider_text",
            return_value="isto não é um JSON",
        ):
            result = classify_topics(
                "Gemini", "key", "gemini-flash-latest", CARDIOLOGY_SUMMARY
            )

        self.assertEqual(result, DEFAULT_TOPIC_CLASSIFICATION)

    def test_provider_error_does_not_raise(self):
        with patch(
            "src.portfolio.ai._request_provider_text",
            side_effect=AIError("Gemini: 503 - indisponível"),
        ):
            result = classify_topics(
                "Gemini", "key", "gemini-flash-latest", CARDIOLOGY_SUMMARY
            )

        self.assertEqual(result, DEFAULT_TOPIC_CLASSIFICATION)

    def test_unexpected_exception_does_not_raise(self):
        with patch(
            "src.portfolio.ai._request_provider_text",
            side_effect=RuntimeError("falha inesperada"),
        ):
            result = classify_topics(
                "Gemini", "key", "gemini-flash-latest", CARDIOLOGY_SUMMARY
            )

        self.assertEqual(result, DEFAULT_TOPIC_CLASSIFICATION)


if __name__ == "__main__":
    unittest.main()
