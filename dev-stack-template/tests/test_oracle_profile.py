import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "oracle/profile"))
import free_tier
import gateway


class FreeProfile(unittest.TestCase):
    def test_home_region_and_unupgraded_account(self):
        regions = [{"is-home-region": True, "region-name": "ap-sydney-1"}]
        free = {"lifecycle-state": "ACTIVE", "payment-model": "FREE_TRIAL"}
        free_tier.check([free], regions, "ap-sydney-1")
        for subscriptions, region in (([], "ap-sydney-1"), ([free], "elsewhere"),
                                      ([free, dict(free, **{"payment-model": "PAYG"})], "ap-sydney-1")):
            with self.assertRaises(ValueError):
                free_tier.check(subscriptions, regions, region)

    def test_inference_transport_is_loopback(self):
        with patch.object(gateway.http.client, "HTTPConnection") as connection:
            gateway.upstream("/v1/responses", {"input": "test"})
        connection.assert_called_once_with("127.0.0.1", 8181, timeout=240)
