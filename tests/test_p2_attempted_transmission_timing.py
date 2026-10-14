"""P2 transport regression: receiver loss never refunds emitted radio airtime.

The model injects receiver Bernoulli loss AFTER a sender's original application
SEND has already been scheduled on the causal shared medium. This tests
attempted transmission charging, not PHY retries or physical Wi-Fi loss.
"""
from __future__ import annotations

import unittest

from democracy_mrta.coordination import (
    _broadcast_event,
    _lossy_broadcast_deliveries,
    _lossy_unicast_delivery,
    _unicast_event,
)
from democracy_mrta.multitask_wire import E9MChannel
from democracy_mrta.network import (
    BernoulliLossSampler,
    EmpiricalLatencyProfile,
    WifiCausalTimingSampler,
    WifiTimingConfig,
)


def _synthetic_timing() -> WifiCausalTimingSampler:
    profile = EmpiricalLatencyProfile(
        source_repository="test", source_commit="test",
        source_blob_sha="test", location="test", location_label="test",
        config="test", config_label="test", steady_start_s=0.0,
        steady_end_s=1.0, samples_ms=(7.0,),
    )
    return WifiCausalTimingSampler(
        profile=profile, seed=123, config=WifiTimingConfig(phy_rate_mbps=144.0),
    )


class AttemptedTransmissionTimingTests(unittest.TestCase):
    def test_broadcast_all_receivers_dropped_still_consumes_airtime(self):
        observed = {}
        for p_loss in (0.0, 1.0):
            with self.subTest(p_loss=p_loss):
                timing = _synthetic_timing()
                send = _broadcast_event(
                    phase="cbaa_consensus", sender_id=0, round_id=1,
                    send_time_ms=0.0, payload_bytes=816, sampler=timing,
                )
                deliveries = _lossy_broadcast_deliveries(
                    event=send, num_robots=5,
                    loss_sampler=BernoulliLossSampler(seed=19),
                    p_loss=p_loss, round_id=1,
                )
                summary = timing.summarize_network()
                self.assertEqual(len(deliveries), 4)
                self.assertEqual(sum(x.delivered for x in deliveries),
                                 4 if p_loss == 0.0 else 0)
                self.assertEqual(summary["packet_count"], 1)
                self.assertEqual(summary["application_sender_bytes"], 816)
                self.assertGreater(summary["total_airtime_ms"], 0.0)
                self.assertGreater(summary["medium_busy_until_ms"], 0.0)
                self.assertGreater(send.arrival_time_ms, 0.0)
                observed[p_loss] = (
                    summary["total_airtime_ms"],
                    summary["medium_busy_until_ms"],
                    send.arrival_time_ms,
                )
        # Same physical SEND workload and same radio seeds, despite 0 vs 100%
        # successful reception. Drop decisions do not erase prior radio time.
        self.assertEqual(observed[0.0], observed[1.0])

    def test_unicast_dropped_receiver_still_consumes_airtime(self):
        observed = {}
        for p_loss in (0.0, 1.0):
            with self.subTest(p_loss=p_loss):
                timing = _synthetic_timing()
                send = _unicast_event(
                    phase="price_bid", sender_id=0, receiver_id=1,
                    round_id=1, send_time_ms=0.0, payload_bytes=28,
                    sampler=timing,
                )
                receipt = _lossy_unicast_delivery(
                    event=send, loss_sampler=BernoulliLossSampler(seed=19),
                    p_loss=p_loss, round_id=1,
                )
                summary = timing.summarize_network()
                self.assertEqual(receipt.delivered, p_loss == 0.0)
                self.assertEqual(summary["application_sender_bytes"], 28)
                self.assertGreater(summary["total_airtime_ms"], 0.0)
                observed[p_loss] = (
                    summary["medium_busy_until_ms"],
                    send.arrival_time_ms,
                )
        self.assertEqual(observed[0.0], observed[1.0])

    def test_cbba_native_channel_pays_dropped_broadcast_phase(self):
        observed = {}
        for p_loss in (0.0, 1.0):
            with self.subTest(p_loss=p_loss):
                timing = _synthetic_timing()
                channel = E9MChannel(
                    robots=5, timing=timing, loss_seed=19, method="cbba",
                )
                channel.begin_phase()
                received = channel.send(
                    phase="cbba_consensus", sender=0, frame=b"x" * 200,
                    round_id=1, frame_id=0, p_loss=p_loss,
                )
                channel.end_phase()
                ledger = channel.ledger()["cbba_consensus"]
                self.assertEqual(len(received), 4 if p_loss == 0.0 else 0)
                self.assertEqual(ledger["sender_sends"], 1)
                self.assertEqual(ledger["sender_bytes"], 200)
                self.assertEqual(ledger["receiver_attempts"], 4)
                self.assertEqual(ledger["receiver_dropped"],
                                 0 if p_loss == 0.0 else 4)
                self.assertGreater(timing.summarize_network()["total_airtime_ms"], 0.0)
                self.assertGreater(channel.clock_ms, 0.0)
                channel.audit_physical_bytes()
                observed[p_loss] = channel.clock_ms
        self.assertEqual(observed[0.0], observed[1.0])


if __name__ == "__main__":
    unittest.main()
