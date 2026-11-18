import concurrent.futures
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / "oracle/profile/gateway.py"
spec = importlib.util.spec_from_file_location("oracle_gateway", path)
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


class Reply(io.BytesIO):
    status = 200

    def __init__(self, verdict):
        super().__init__(json.dumps({"choices": [{"message": {"content": verdict}}]}).encode())


class Routing(unittest.TestCase):
    def test_no_external_by_default_or_for_private_tasks(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(gateway, "upstream") as upstream:
            self.assertEqual(gateway.choose({}, True)[0], gateway.LOCAL)
            with patch.dict(os.environ, {"PUBLIC_OPENAI_KEY": "fake", "PUBLIC_OPENAI_MODEL": "mock",
                                         "PUBLIC_CALLS_PER_DAY": "5"}):
                self.assertEqual(gateway.choose({}, False)[0], gateway.LOCAL)
            upstream.assert_not_called()

    def test_only_valid_escalation_consumes_a_slot(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
                "PUBLIC_OPENAI_KEY": "fake", "PUBLIC_OPENAI_MODEL": "mock", "PUBLIC_CALLS_PER_DAY": "1",
                "USAGE_DB": str(Path(tmp) / "usage")}, clear=True):
            for verdict, target in (("invalid", gateway.LOCAL), ("SIMPLE", gateway.LOCAL),
                                    ("HARD", "https://api.openai.com"), ("HARD", gateway.LOCAL)):
                with patch.object(gateway, "upstream", return_value=Reply(verdict)):
                    self.assertEqual(gateway.choose({"input": "request"}, True)[0], target)

    def test_atomic_daily_reservation(self):
        with tempfile.TemporaryDirectory() as tmp, concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(lambda _: gateway.reserve(str(Path(tmp)/"db"), 2), range(10)))
            self.assertEqual(sum(results), 2)
