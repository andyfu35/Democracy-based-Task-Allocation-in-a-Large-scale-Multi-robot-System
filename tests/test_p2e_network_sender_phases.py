"""P2E: the real network sender ledger counts attempted, not delivered, packets."""
import unittest

from democracy_mrta.coordination import _broadcast_event, _lossy_broadcast_deliveries
from democracy_mrta.network import (
    EmpiricalLatencyProfile, WifiCausalTimingSampler, WifiTimingConfig,
    BernoulliLossSampler,
)


def fixture():
    return EmpiricalLatencyProfile(
        source_repository="test/synthetic", source_commit="synthetic",
        source_blob_sha="synthetic", location="test", location_label="synthetic",
        config="test", config_label="synthetic", steady_start_s=0.0,
        steady_end_s=1.0, samples_ms=(5.0, 7.0, 9.0),
    )


class P2EPhaseSenderTests(unittest.TestCase):
    def test_all_dropped_cost_is_still_paid_per_phase_once(self):
        sampler = WifiCausalTimingSampler(
            fixture(), 4, WifiTimingConfig(phy_rate_mbps=144.0),
        )
        event = _broadcast_event(
            phase="cost", sender_id=0, payload_bytes=816,
            send_time_ms=0.0, sampler=sampler,
        )
        observed = _lossy_broadcast_deliveries(
            event=event, num_robots=5,
            loss_sampler=BernoulliLossSampler(seed=4), p_loss=1.0,
            round_id=0,
        )
        self.assertEqual(len(observed), 4)
        self.assertTrue(all(not o.delivered for o in observed))
        by_phase = sampler.summarize_network()["sender_by_phase"]
        self.assertEqual(by_phase["cost"], {"sender_sends": 1, "sender_bytes": 816})
        self.assertEqual(sampler.summarize_network()["application_sender_bytes"], 816)
        self.assertEqual(sampler.summarize_network()["packet_count"], 1)

    def test_multi_phase_senders_reconcile_to_network_total(self):
        sampler = WifiCausalTimingSampler(
            fixture(), 4, WifiTimingConfig(phy_rate_mbps=144.0),
        )
        sampler.sample_packet_ms(
            key="task", phase="task_announcement", sender_id=5,
            receiver_id=-1, send_time_ms=0, payload_bytes=1200,
        )
        sampler.sample_packet_ms(
            key="cost", phase="cost", sender_id=0,
            receiver_id=-1, send_time_ms=0, payload_bytes=816,
        )
        sampler.sample_packet_ms(
            key="vote", phase="vote", sender_id=1,
            receiver_id=-1, send_time_ms=0, payload_bytes=32,
        )
        summary = sampler.summarize_network()
        self.assertEqual(summary["application_sender_bytes"], 2048)
        self.assertEqual(summary["packet_count"], 3)
        self.assertEqual(summary["sender_by_phase"], {
            "task_announcement": {"sender_sends": 1, "sender_bytes": 1200},
            "cost": {"sender_sends": 1, "sender_bytes": 816},
            "vote": {"sender_sends": 1, "sender_bytes": 32},
        })


if __name__ == "__main__":
    unittest.main()
