from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aws/laya-decisions"))
import service

QUESTION = {"risk": {"type": "noul", "instructions": "Were any tests skipped?"}}


class DecisionServiceTest(unittest.TestCase):
    def test_returns_typed_answers_from_laya(self):
        request = {"state": "No tests skipped.", "questions": QUESTION}
        with patch.object(service, "reserve", return_value=True), patch.object(service, "model") as model:
            model.return_value.predict.return_value = {"answers": {"risk": {"noul": 0.1}}}
            result = service.handle(request, None)
        self.assertEqual(result["answers"], {"risk": {"noul": 0.1}})
        self.assertEqual(result["model"], service.MODEL)
        model.return_value.predict.assert_called_once_with(request["state"], QUESTION)

    def test_invalid_request_and_exhausted_allowance_never_call_model(self):
        with patch.object(service, "model") as model, patch.object(service, "reserve", return_value=False) as reserve:
            invalid = service.handle({"state": "x" * 8001, "questions": QUESTION}, None)
            self.assertEqual(invalid["code"], "invalid_request")
            reserve.assert_not_called()
            limited = service.handle({"state": "Test.", "questions": QUESTION}, None)
            self.assertEqual(limited["code"], "quota")
            reserve.assert_called_once()
            model.assert_not_called()
