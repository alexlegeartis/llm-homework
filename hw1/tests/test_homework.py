import copy
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from homework_01_rag.evaluate import evaluate
from homework_01_rag.predict import Client, input_bound, make_messages, predict, validate_answer


class HomeworkTests(unittest.TestCase):
    def setUp(self):
        self.question = {"id": "unseen", "question": "Выберите верное утверждение.", "options": [{"id": letter, "text": letter} for letter in ["Z", "Y", "X", "W"]]}
        self.answer = {"id": "unseen", "answer_ids": ["Z", "Y"], "abstain": False, "rationale": "Краткое обоснование.", "citations": ["source"]}

    def test_actual_option_ids_and_exact_sets(self):
        self.assertEqual(validate_answer(self.answer, self.question, ["source"]), [])
        invalid = copy.deepcopy(self.answer)
        invalid["answer_ids"] = ["A"]
        self.assertTrue(validate_answer(invalid, self.question, ["source"]))
        target = {"id": "unseen", "category": "conditions", "answer_ids": ["Y"], "abstain": False, "citation_sets": [["source"]]}
        trace = {"id": "unseen", "llm_calls": 1, "input_tokens": 50, "output_tokens": 20, "elapsed_ms": 1, "usage_verified": True, "calls": [{"input_tokens": 50, "output_tokens": 20, "max_tokens": 100}]}
        metrics = evaluate([self.question], [target], [self.answer], [trace], ["source"])
        self.assertEqual(metrics["answer_accuracy"], 0)

    def test_abstention_and_citation_contract(self):
        answer = copy.deepcopy(self.answer)
        answer["abstain"] = True
        self.assertTrue(validate_answer(answer, self.question, ["source"]))
        answer["answer_ids"], answer["citations"] = [], []
        self.assertEqual(validate_answer(answer, self.question, ["source"]), [])
        answer["abstain"] = "true"
        self.assertTrue(validate_answer(answer, self.question, ["source"]))

    def test_one_limit_violation_invalidates_all_efficiency(self):
        target = {"id": "unseen", "category": "conditions", "answer_ids": ["Z", "Y"], "abstain": False, "citation_sets": [["source"]]}
        trace = {"id": "unseen", "llm_calls": 1, "input_tokens": 8000, "output_tokens": 20, "elapsed_ms": 1, "usage_verified": True, "calls": [{"input_tokens": 8000, "output_tokens": 20, "max_tokens": 512}]}
        metrics = evaluate([self.question], [target], [self.answer], [trace], ["source"], reference_cost=100)
        self.assertFalse(metrics["efficiency_valid"])
        self.assertEqual(metrics["E"], 0)
        self.assertEqual(metrics["questions"][0]["score"], 0)

    def test_context_packing_respects_the_preflight_budget(self):
        candidates = [{"block_id": "large", "page": 1, "section": "test", "text": "я" * 10000}, {"block_id": "small", "page": 2, "section": "test", "text": "Теорема."}]
        messages, sources = make_messages(self.question, candidates, 7400)
        self.assertLessEqual(input_bound(messages), 7400)
        self.assertEqual(sources, ["small"])

    def test_format_error_with_verified_usage_preserves_efficiency(self):
        target = {"id": "unseen", "category": "insufficient", "answer_ids": [], "abstain": True, "citation_sets": []}
        answer = {"id": "unseen", "answer_ids": [], "abstain": True, "rationale": "Processing failed.", "citations": []}
        trace = {"id": "unseen", "llm_calls": 1, "input_tokens": 50, "output_tokens": 20, "elapsed_ms": 1, "usage_verified": True, "calls": [{"input_tokens": 50, "output_tokens": 20, "max_tokens": 512}], "error": "Invalid model answer"}
        metrics = evaluate([self.question], [target], [answer], [trace], ["source"], reference_cost=500)
        self.assertEqual(metrics["answer_accuracy"], 0)
        self.assertTrue(metrics["efficiency_valid"])
        self.assertEqual(metrics["E"], 1)

    def test_endpoint_usage_and_headers_are_preserved(self):
        runtime = {"model": "Qwen/Qwen3.5-4B", "generation": {"max_tokens": 512}, "timeout_seconds": 2}
        response = {"id": "response-1", "model": "Qwen/Qwen3.5-4B", "usage": {"prompt_tokens": 50, "completion_tokens": 20}, "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({k: v for k, v in self.answer.items() if k != "id"})}}]}
        trace = {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0, "calls": []}
        with patch.dict("os.environ", {"LLM_BASE_URL": "http://127.0.0.1:1234/v1", "SUBMISSION_ID": "unit-test"}):
            with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as request:
                result = Client(runtime).answer(self.question, [{"role": "user", "content": "test"}], ["source"], trace)
        self.assertEqual(result, self.answer)
        self.assertEqual(trace["input_tokens"], 50)
        self.assertEqual(trace["output_tokens"], 20)
        headers = {key.lower(): value for key, value in request.call_args.args[0].header_items()}
        self.assertEqual(headers["x-question-id"], "unseen")
        self.assertEqual(headers["x-submission-id"], "unit-test")

    def test_model_rationale_is_preserved(self):
        runtime = {"model": "Qwen/Qwen3.5-4B", "generation": {"max_tokens": 512}, "timeout_seconds": 2}
        answer = {**self.answer, "rationale": "Верны A и C по формуле. Варианты B и D означают постоянство."}
        with patch.dict("os.environ", {"LLM_BASE_URL": "http://127.0.0.1:1234/v1", "SUBMISSION_ID": "unit-test"}):
            with patch.object(Client, "complete", return_value=copy.deepcopy(answer)):
                result = Client(runtime).answer(self.question, [], ["source"], {})
        self.assertEqual(result["rationale"], answer["rationale"])

    def test_latex_json_control_escapes_are_recovered(self):
        runtime = {"model": "Qwen/Qwen3.5-4B", "generation": {"max_tokens": 512}, "timeout_seconds": 2}
        trace = {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0, "calls": []}
        answer = {**self.answer, "rationale": "\frac{1}{2}, \bar z"}
        with patch.dict("os.environ", {"LLM_BASE_URL": "http://127.0.0.1:1234/v1", "SUBMISSION_ID": "unit-test"}):
            with patch.object(Client, "complete", return_value=answer):
                result = Client(runtime).answer(self.question, [], ["source"], trace)
        self.assertEqual(result["rationale"], r"\frac{1}{2}, \bar z")
        self.assertEqual(validate_answer(result, self.question, ["source"]), [])

    def test_prediction_maps_labels_to_original_option_ids(self):
        runtime = {"model": "Qwen/Qwen3.5-4B", "generation": {"max_tokens": 512}, "timeout_seconds": 2}
        config = {"runtime_settings": runtime, "mode": "baseline", "retrieval": {"neighbors": False, "query_expansion": False}}
        source = {"block_id": "source", "page": 1, "section": "test", "text": "Reference text."}
        index = SimpleNamespace(retrieve=lambda *args: [source])
        model_answer = {**{k: v for k, v in self.answer.items() if k != "id"}, "answer_ids": ["A", "A", "B"], "citations": ["source", "source"]}
        response = {"id": "response-2", "model": runtime["model"], "usage": {"prompt_tokens": 50, "completion_tokens": 20}, "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(model_answer)}}]}
        with TemporaryDirectory() as temporary:
            output, trace = Path(temporary) / "answers.jsonl", Path(temporary) / "trace.jsonl"
            with patch.dict("os.environ", {"LLM_BASE_URL": "http://127.0.0.1:1234/v1", "SUBMISSION_ID": "unit-test"}):
                with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as request:
                    predict(index, [self.question], output, trace, config)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), self.answer)
            payload = json.loads(request.call_args.args[0].data)
            self.assertIn("A. Z\nB. Y\nC. X\nD. W", payload["messages"][1]["content"])

    def test_final_refusal_keeps_reason_and_usage_and_clears_lists(self):
        runtime = {"model": "Qwen/Qwen3.5-4B", "generation": {"max_tokens": 512}, "timeout_seconds": 2}
        config = {"runtime_settings": runtime, "mode": "final", "retrieval": {"neighbors": False, "query_expansion": False}}
        source = {"block_id": "source", "page": 1, "section": "test", "text": "Reference text."}
        index = SimpleNamespace(retrieve=lambda *args: [source])
        model_answer = {"answer_ids": ["A"], "abstain": True, "rationale": "Не указана ориентация контура.", "citations": ["source"]}
        response = {"usage": {"prompt_tokens": 50, "completion_tokens": 20}, "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(model_answer)}}]}
        with TemporaryDirectory() as temporary:
            output, trace = Path(temporary) / "answers.jsonl", Path(temporary) / "trace.jsonl"
            with patch.dict("os.environ", {"LLM_BASE_URL": "http://127.0.0.1:1234/v1", "SUBMISSION_ID": "unit-test"}):
                with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
                    predict(index, [self.question], output, trace, config)
            answer = json.loads(output.read_text(encoding="utf-8"))
            usage = json.loads(trace.read_text(encoding="utf-8"))
        self.assertEqual(answer["rationale"], model_answer["rationale"])
        self.assertEqual((answer["answer_ids"], answer["citations"]), ([], []))
        self.assertTrue(answer["abstain"])
        self.assertNotIn("error", usage)
        self.assertEqual((usage["llm_calls"], usage["input_tokens"], usage["output_tokens"]), (1, 50, 20))

    def test_retrieval_keeps_evidence_for_distinct_search_queries(self):
        from homework_01_rag.retrieval import Index
        index = Index.__new__(Index)
        index.blocks = [{"block_id": identifier} for identifier in ["alpha-source", "beta-source", "generic-overlap"]]
        index.search = lambda query, *args: {"alpha": [0, 2], "beta": [1, 2]}.get(query, [2, 0, 1])
        settings = {"candidate_k": 3, "top_k": 2, "query_expansion": True, "neighbors": False}
        blocks = index.retrieve(self.question, settings, "final", ["alpha", "beta"])
        self.assertEqual([block["block_id"] for block in blocks][:2], ["alpha-source", "beta-source"])

    def test_neighbors_add_continuation_without_unrelated_previous_theorem(self):
        from homework_01_rag.retrieval import Index
        index = Index.__new__(Index)
        index.blocks = [
            {"block_id": "unrelated", "page": 1, "section": "s", "text": "Теорема о другом."},
            {"block_id": "seed", "page": 1, "section": "s", "text": "Замечание о первообразной."},
            {"block_id": "continuation", "page": 1, "section": "s", "text": "Продолжение примера."},
            {"block_id": "next", "page": 2, "section": "s", "text": "Теорема следующая."},
        ]
        index.search = lambda *args: [1]
        settings = {"candidate_k": 1, "top_k": 1, "neighbors": True}
        blocks = index.retrieve(self.question, settings, "final")
        self.assertEqual([b["block_id"] for b in blocks], ["seed", "continuation"])

    def test_math_query_preserves_adjacent_latex_commands(self):
        from homework_01_rag.retrieval import math_query, tokens, expand_queries
        normalized = math_query(r"\partial f/\partial\bar z=0")
        self.assertIn("bar(z)", normalized)
        self.assertIn("partial", tokens(normalized))
        self.assertNotIn("partialbar", tokens(normalized))
        self.assertIn("∂f ∂bar(z)", expand_queries({"question": normalized, "options": []}))
        self.assertEqual(math_query(r"\tfrac12(f_x+i f_y)=0"), "(1)/(2)(f_x+i f_y)=0")
        self.assertIn("e", tokens(r"e^z"))
        self.assertIn("интегральная формула Коши для производных", expand_queries({"question": "Вычислите ∮ f(z) dz", "options": []}))

    def test_pdf_preserves_conjugation_fractions_and_factorials(self):
        root = Path(__file__).resolve().parents[1]
        pdf = root / "homework_01_rag" / "data" / "textbook.pdf"
        if not pdf.is_file():
            pdf = root.parent / "textbook.pdf"
        if not pdf.is_file():
            self.skipTest("Run with the downloaded source PDF available")
        import pymupdf
        from homework_01_rag.pdf_text import page_paragraphs
        document = pymupdf.open(pdf)
        page12 = " ".join(page_paragraphs(document[11]))
        page18 = " ".join(page_paragraphs(document[17]))
        page34 = " ".join(page_paragraphs(document[33]))
        page79 = " ".join(page_paragraphs(document[78]))
        self.assertIn("(∂f)/(∂bar(z)) = 0", page12)
        self.assertIn("(∂f)/(∂z) = (1)/(2)", page12)
        self.assertIn("(n!)/(2πi)", page34)
        self.assertIn("((ζ−z)^{n+1})", page34)
        self.assertIn("функция bar(f(z)) является дифференцируемой", page79)
        self.assertIn("bar(z^{′}(t_{0}))", page79)
        self.assertIn("root(n,|a_{n}|)", page18)
        self.assertIn("limsup", page18)
        self.assertIn("≠ 0", page79)


if __name__ == "__main__":
    unittest.main()
