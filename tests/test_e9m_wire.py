import unittest
from democracy_mrta.multitask_wire import (encode_cbba_snapshot,
    decode_cbba_snapshot, encode_small_packet, decode_small_packet, E9MChannel)
from democracy_mrta.network import (EmpiricalLatencyProfile, WifiCausalTimingSampler,
                                     WifiTimingConfig)


class TestE9MWire(unittest.TestCase):
    def test_full_fragmentation_stale_and_incomplete(self):
        tasks, robots = 100, 25
        frames = encode_cbba_snapshot(5, 3, list(range(robots)) * 4,
                                      [float(x) + 0.12345678912345678 for x in range(tasks)],
                                      [float(x) + 0.10345678912345678 for x in range(robots)])
        self.assertGreater(len(frames), 1)
        self.assertTrue(all(len(packet) <= 1200 for packet in frames))
        self.assertIsNone(decode_cbba_snapshot(frames[:-1], round_id=5,
                                                sender_id=3, tasks=tasks, robots=robots))
        self.assertIsNone(decode_cbba_snapshot(frames, round_id=6,
                                                sender_id=3, tasks=tasks, robots=robots))
        self.assertEqual(decode_cbba_snapshot(frames, round_id=5,
                                               sender_id=3, tasks=tasks, robots=robots)["z"],
                         list(range(robots)) * 4)
        corrupted = list(frames)
        corrupted[0] = corrupted[0][:-1] + bytes([corrupted[0][-1] ^ 1])
        self.assertIsNone(decode_cbba_snapshot(corrupted, round_id=5,
                                                sender_id=3, tasks=tasks, robots=robots))

    def test_independent_receiver_loss_and_exact_sender_bytes(self):
        profile = EmpiricalLatencyProfile("test", "test", "test", "2", "test",
                                          "x", "test", 120, 181, (1.0,))
        timing = WifiCausalTimingSampler(profile, 7, WifiTimingConfig(phy_rate_mbps=144))
        channel = E9MChannel(robots=12, timing=timing, loss_seed=5, method="cbba")
        packet = encode_small_packet("voting_cost", 2, 0, 3, 1)
        self.assertEqual(decode_small_packet("voting_cost", packet, 2, 0), (3, 1))
        channel.begin_phase()
        delivered = channel.send(phase="voting_cost", sender=0, frame=packet,
                                 round_id=2, frame_id=0, p_loss=0.30)
        channel.end_phase()
        self.assertNotIn(0, delivered)
        row = channel.ledger()["voting_cost"]
        self.assertEqual(row["sender_sends"], 1)
        self.assertEqual(row["sender_bytes"], len(packet))
        self.assertEqual(row["receiver_attempts"], 11)
        self.assertEqual(row["receiver_delivered"] + row["receiver_dropped"], 11)
        self.assertGreater(row["receiver_dropped"], 0)
        self.assertGreater(row["receiver_delivered"], 0)
        channel.audit_physical_bytes()


if __name__ == "__main__":
    unittest.main()
