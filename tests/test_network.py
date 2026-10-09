from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from democracy_mrta.network import (
    BernoulliLossSampler,
    EmpiricalLatencySampler,
    build_verified_https_context,
    load_rady_latency_profile,
)


class NetworkTests(unittest.TestCase):
    def test_verified_https_context_keeps_certificate_verification_enabled(self) -> None:
        context = build_verified_https_context()
        self.assertTrue(context.check_hostname)
        self.assertNotEqual(context.verify_mode, 0)

    def test_profile_filters_to_steady_window(self) -> None:
        fake = {
            "2": {
                "ax_160mhz_6ghz": {
                    "control_timestamp_s": [119.0, 120.0, 150.0, 181.0, 182.0],
                    "control_delay_ms": [1.0, 10.0, 20.0, 30.0, 99.0],
                }
            }
        }
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "fake.json"
            path.write_text(json.dumps(fake), encoding="utf-8")
            profile = load_rady_latency_profile(path)

        self.assertEqual(profile.samples_ms, (10.0, 20.0, 30.0))

    def test_keyed_sampler_is_deterministic(self) -> None:
        fake = {
            "2": {
                "ax_160mhz_6ghz": {
                    "control_timestamp_s": [120.0, 121.0, 122.0],
                    "control_delay_ms": [10.0, 20.0, 30.0],
                }
            }
        }
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "fake.json"
            path.write_text(json.dumps(fake), encoding="utf-8")
            profile = load_rady_latency_profile(path)

        first = EmpiricalLatencySampler(profile, seed=7)
        second = EmpiricalLatencySampler(profile, seed=7)
        self.assertEqual(first.sample_ms("cost|1|2|-"), second.sample_ms("cost|1|2|-"))

    def test_bernoulli_loss_sampler_zero_loss_always_delivers(self) -> None:
        sampler = BernoulliLossSampler(seed=123)
        for index in range(100):
            self.assertTrue(sampler.is_delivered(f"packet-{index}", 0.0))

    def test_bernoulli_loss_sampler_full_loss_never_delivers(self) -> None:
        sampler = BernoulliLossSampler(seed=123)
        for index in range(100):
            self.assertFalse(sampler.is_delivered(f"packet-{index}", 1.0))

    def test_bernoulli_loss_sampler_is_deterministic(self) -> None:
        first = BernoulliLossSampler(seed=7)
        second = BernoulliLossSampler(seed=7)
        outcomes_first = [
            first.is_delivered(f"packet-{index}", 0.3)
            for index in range(100)
        ]
        outcomes_second = [
            second.is_delivered(f"packet-{index}", 0.3)
            for index in range(100)
        ]
        self.assertEqual(outcomes_first, outcomes_second)


if __name__ == "__main__":
    unittest.main()
