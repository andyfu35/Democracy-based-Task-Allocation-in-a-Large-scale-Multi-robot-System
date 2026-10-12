"""E9G-1/2 network owner and Voting-only causal sensitivity smoke tests."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import (
    EmpiricalLatencyProfile, WifiCausalTimingSampler, WifiTimingConfig,
    validate_wifi_phy_config,
)
from experiments.run_e9g_wifi_scaling import (
    calculate_e9g_phase_timeout_ms, parse_e9g_rates, parse_e9g_sizes,
    run_e9g_one_voting_case, run_e9g_wifi_scaling,
)


def profile_fixture() -> EmpiricalLatencyProfile:
    return EmpiricalLatencyProfile(
        source_repository="test/synthetic", source_commit="synthetic",
        source_blob_sha="synthetic", location="test",
        location_label="synthetic", config="test",
        config_label="synthetic", steady_start_s=0.0,
        steady_end_s=1.0, samples_ms=(5.0, 7.0, 9.0),
    )


class E9GCausalWifiTimingTests(unittest.TestCase):

    def test_phy_data_first_failure(self):
        for rate in (-1.0, 0.0, float("nan"), float("inf")):
            with self.subTest(rate=rate), self.assertRaises(ProtocolError) as err:
                validate_wifi_phy_config(WifiTimingConfig(phy_rate_mbps=rate))
            self.assertEqual(err.exception.diagnostic.owner, "network")
            self.assertEqual(err.exception.diagnostic.category, "data")
            self.assertEqual(err.exception.diagnostic.code, "E9G_INVALID_WIFI_PHY")

    def test_same_time_send_pays_two_radio_hops_and_shared_queue(self):
        sampler = WifiCausalTimingSampler(
            profile_fixture(), 0, WifiTimingConfig(phy_rate_mbps=144.0),
        )
        first = sampler.sample_packet_ms(
            key="a", phase="cost", sender_id=0, receiver_id=-1,
            send_time_ms=0.0, payload_bytes=416,
        )
        second = sampler.sample_packet_ms(
            key="b", phase="cost", sender_id=1, receiver_id=-1,
            send_time_ms=0.0, payload_bytes=416,
        )
        summary = sampler.summarize_network()
        self.assertGreater(first, 0)
        self.assertGreater(second, first)
        self.assertEqual(summary["packet_count"], 2)
        self.assertEqual(summary["application_sender_bytes"], 832)
        self.assertEqual(summary["radio_hop_count"], 4)
        self.assertGreater(sampler.packet_trace[1]["queue_ms"], 0)
        self.assertEqual(summary["radio_payload_equivalent_bytes"], 4*(416+64))

    def test_original_task_is_one_ap_hop_and_ack_free(self):
        sampler = WifiCausalTimingSampler(
            profile_fixture(), 10, WifiTimingConfig(phy_rate_mbps=600.0),
        )
        sampler.sample_packet_ms(
            key="task", phase="task_announcement", sender_id=5,
            receiver_id=-1, send_time_ms=0.0, payload_bytes=1200,
        )
        self.assertEqual(sampler.packet_trace[0]["wireless_hops"], 1)
        self.assertEqual(sampler.packet_trace[0]["mac_ack_ms"], 0.0)

    def test_network_cannot_submit_past_release_after_future(self):
        sampler = WifiCausalTimingSampler(
            profile_fixture(), 0, WifiTimingConfig(phy_rate_mbps=144.0),
        )
        sampler.sample_packet_ms(
            key="later", phase="vote", sender_id=0, receiver_id=1,
            send_time_ms=50.0, payload_bytes=32,
        )
        with self.assertRaises(ProtocolError) as err:
            sampler.sample_packet_ms(
                key="earlier", phase="vote", sender_id=2, receiver_id=1,
                send_time_ms=10.0, payload_bytes=32,
            )
        self.assertEqual(err.exception.diagnostic.code,
                         "E9G_NONCAUSAL_PACKET_RELEASE")

    def test_actual_original_voting_owner_passes_both_models_same_payload(self):
        fixture = profile_fixture()
        cases = [
            run_e9g_one_voting_case(
                profile=fixture, n=5, seed=1, max_rounds=15,
                phy_rate_mbps=rate, timeout_ms=100.0,
            ) for rate in (None, 144.0)
        ]
        self.assertEqual([x["full_commit"] for x in cases], [1, 1])
        self.assertEqual([x["tasks_committed"] for x in cases], [5, 5])
        self.assertEqual(cases[0]["total_sender_bytes"],
                         cases[1]["total_sender_bytes"])
        self.assertEqual(cases[0]["total_send_count"],
                         cases[1]["total_send_count"])
        self.assertGreater(cases[1]["total_queue_ms"], 0)
        self.assertGreater(cases[1]["total_airtime_ms"], 0)

    def test_derived_timeout_is_fixed_for_all_sizes_in_one_grid(self):
        profile = profile_fixture()
        full = calculate_e9g_phase_timeout_ms(
            profile=profile, sizes=(5, 20, 100), rates=(144.0, 600.0),
        )
        tiny = calculate_e9g_phase_timeout_ms(
            profile=profile, sizes=(5,), rates=(144.0, 600.0),
        )
        self.assertGreater(full, tiny)
        self.assertGreater(full, max(profile.samples_ms))

    def test_immutable_paired_grid_checksums_and_no_fake_ns3(self):
        fixture = profile_fixture()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "e9g"
            with (
                patch("experiments.run_e9g_wifi_scaling.ensure_rady_dataset",
                      return_value=Path(folder)/"fake-rady.json"),
                patch("experiments.run_e9g_wifi_scaling.load_rady_latency_profile",
                      return_value=fixture),
                patch("experiments.run_e9g_wifi_scaling.subprocess.check_output",
                      return_value="a"*40),
            ):
                rows = run_e9g_wifi_scaling(
                    sizes=(3, 5), rates=(144.0,), seeds=2,
                    first_seed=0, max_rounds=15,
                    dataset=Path(folder)/"fake-rady.json",
                    output_root=root, allow_download=False,
                )
            self.assertEqual(len(rows), 2*2*2)
            self.assertEqual(set(x["model"] for x in rows), {
                "rady_bootstrap_no_shared_channel",
                "e9g_shared_medium_backoff_proxy",
            })
            manifest = json.loads((root/"manifest.json").read_text())
            self.assertEqual(manifest["source_git_sha"], "a"*40)
            self.assertIn("ns3", manifest["model_not_supported"])
            for name, digest in manifest["checksums_sha256"].items():
                self.assertEqual(
                    hashlib.sha256((root/name).read_bytes()).hexdigest(),
                    digest,
                )
            with (root/"per_seed_wifi_timing.csv").open() as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), len(rows))
            self.assertFalse((root/"per_seed_wifi_timing.partial.csv").exists())
            with self.assertRaises(ProtocolError) as err:
                run_e9g_wifi_scaling(
                    sizes=(3, 5), rates=(144.0,), seeds=2,
                    first_seed=0, max_rounds=15,
                    dataset=Path(folder)/"fake-rady.json",
                    output_root=root, allow_download=False,
                )
            self.assertEqual(err.exception.diagnostic.code, "E9G_OUTPUT_EXISTS")

    def test_reject_duplicate_size_and_invalid_rate_grid(self):
        for raw in ("5,5,10", "100,5", "1,5", ""):
            with self.subTest(raw=raw), self.assertRaises(ProtocolError):
                parse_e9g_sizes(raw)
        for raw in ("0,600", "600,144", "144,144", "nan"):
            with self.subTest(raw=raw), self.assertRaises(ProtocolError):
                parse_e9g_rates(raw)


if __name__ == "__main__":
    unittest.main()
