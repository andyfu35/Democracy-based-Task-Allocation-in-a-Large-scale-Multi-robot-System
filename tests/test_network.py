from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from democracy_mrta.network import (
    EmpiricalLatencySampler,
    load_rady_latency_profile,
)


class NetworkTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
