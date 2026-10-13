"""E9M native vote transmission: local ballots are free; remote ballots are unicast."""
import unittest

from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.multitask_scenario import generate_multitask_scene
from democracy_mrta.multitask_wire import E9MChannel, encode_small_packet
from democracy_mrta.voting_multitask import transmit_votes
from democracy_mrta.network import EmpiricalLatencyProfile, WifiCausalTimingSampler, WifiTimingConfig


def make_channel(robots=3):
    profile = EmpiricalLatencyProfile(
        "test", "test", "test", "2", "test",
        "x", "test", 120, 181, (1.0,))
    sampler = WifiCausalTimingSampler(profile, 101, WifiTimingConfig(phy_rate_mbps=144.0))
    return E9MChannel(robots=robots, timing=sampler, loss_seed=8,
                      method="voting_multitask")


class TestE9MVoteDelivery(unittest.TestCase):
    def test_one_remote_unicast_and_two_local_votes(self):
        scene = generate_multitask_scene(0, 3, 3, 1)
        channel = make_channel()
        # Agent0 votes itself, agent1 votes itself, agent2 votes agent0.
        physically_received_costs = {0: {0: 5.0}, 1: {1: 5.0}, 2: {0: 6.0}}
        votes = transmit_votes(scene, channel, 0, physically_received_costs,
                               [0, 0, 0], 0.0)
        self.assertEqual(dict(votes), {0: 2, 1: 1})
        ledger = channel.ledger()["voting_vote"]
        self.assertEqual(ledger["sender_sends"], 1)
        self.assertEqual(ledger["sender_bytes"],
                         len(encode_small_packet("voting_vote", 0, 2, 0, 1)))
        self.assertEqual(ledger["receiver_attempts"], 1)
        self.assertEqual(ledger["receiver_delivered"], 1)
        self.assertEqual(ledger["receiver_dropped"], 0)
        self.assertEqual(channel.timing.packet_trace[0]["sender_id"], 2)
        self.assertEqual(channel.timing.packet_trace[0]["receiver_id"], 0)
        channel.audit_physical_bytes()

    def test_explicit_unicast_rejects_self_destination_without_send(self):
        channel = make_channel()
        channel.begin_phase()
        frame = encode_small_packet("voting_vote", 0, 0, 0, 1)
        with self.assertRaises(ProtocolError) as raised:
            channel.send(phase="voting_vote", sender=0, frame=frame,
                         round_id=0, frame_id=0, p_loss=0.0, receivers=(0,))
        self.assertEqual(raised.exception.diagnostic.code,
                         "E9M_INVALID_UNICAST_DESTINATION")
        self.assertFalse(channel.timing.packet_trace)

    def test_voting_vote_broadcast_rejected_before_physical_send(self):
        channel = make_channel()
        channel.begin_phase()
        frame = encode_small_packet("voting_vote", 0, 0, 1, 1)
        with self.assertRaises(ProtocolError) as raised:
            channel.send(phase="voting_vote", sender=0, frame=frame,
                         round_id=0, frame_id=0, p_loss=0.0)
        self.assertEqual(raised.exception.diagnostic.code,
                         "E9M_VOTE_REQUIRES_UNICAST")
        self.assertFalse(channel.timing.packet_trace)

    def test_original_broadcast_phases_remain_broadcast(self):
        channel = make_channel()
        channel.begin_phase()
        frame = encode_small_packet("voting_cost", 0, 0, 0, 1)
        delivered = channel.send(phase="voting_cost", sender=0, frame=frame,
                                 round_id=0, frame_id=0, p_loss=0.0)
        channel.end_phase()
        self.assertEqual(set(delivered), {1, 2})
        self.assertEqual(channel.ledger()["voting_cost"]["sender_sends"], 1)
        self.assertEqual(channel.ledger()["voting_cost"]["receiver_attempts"], 2)
        self.assertEqual(channel.timing.packet_trace[0]["receiver_id"], -1)
        channel.audit_physical_bytes()


if __name__ == "__main__":
    unittest.main()
