"""Owner-level P2 batch regression: Cost once, all-task Greedy vote phase, causal paid packets."""
from __future__ import annotations

import unittest

from democracy_mrta.coordination import (
    decode_greedy_batch_packet, encode_greedy_batch_packet,
    simulate_democracy_hungarian_retirement, validate_vote_decision_rule,
)
from democracy_mrta.optimizer import (
    solve_sequential_greedy_reference, solve_visible_batched_greedy_assignment,
)
from democracy_mrta.protocol import validate_one_to_one_commits
from democracy_mrta.diagnostics import ProtocolError


MATRIX = (
    (1., 9., 9., 9.),
    (2., 1., 9., 9.),
    (3., 2., 1., 9.),
    (4., 3., 2., 1.),
)


class OneMsSampler:
    def sample_ms(self, key):
        return 1.0


class DeterministicLoss:
    def is_delivered(self, key, probability):
        return probability < 1.0


def run_voting(mode, packet_loss=0.0):
    return simulate_democracy_hungarian_retirement(
        cost_matrix=MATRIX, sampler=OneMsSampler(), loss_sampler=DeterministicLoss(),
        p_loss=packet_loss, p_vote_loss=packet_loss,
        phase_timeout_ms=20.0, max_rounds=8,
        voting_strategy=mode, vote_decision_rule="received_plurality",
        cost_repetitions=1, vote_repetitions=1, enforce_vote_deadline=True,
    )


class P2BatchedGreedyTests(unittest.TestCase):
    def test_full_cost_one_batch_matches_unmodified_sequential_greedy(self):
        visible = frozenset(range(4))
        proposal = solve_visible_batched_greedy_assignment(MATRIX, visible)
        self.assertEqual(proposal.assigned_pairs,
                         solve_sequential_greedy_reference(MATRIX).assigned_pairs)
        partial = solve_visible_batched_greedy_assignment(MATRIX, {0, 2})
        self.assertEqual(len(partial.assigned_pairs), 2)
        self.assertEqual(len({robot for robot, _ in partial.assigned_pairs}), 2)
        self.assertTrue(all(task in (0, 1) for _, task in partial.assigned_pairs))

    def test_batch_rejects_implicit_strict_majority_rule(self):
        with self.assertRaises(ProtocolError) as ctx:
            validate_vote_decision_rule(
                rule="strict_majority", voting_strategy="greedy_batch", num_tasks=4,
            )
        self.assertEqual(ctx.exception.diagnostic.code,
                         "BATCH_GREEDY_REQUIRES_RECEIVED_PLURALITY")

    def test_wire_records_are_framed_and_decoded(self):
        records = ((0, 2), (1, 3), (3, 1))
        packet = encode_greedy_batch_packet(
            kind=b"BVOT", round_id=0, sender_id=4, records=records)
        self.assertEqual(len(packet), 16 + 8 * len(records))
        self.assertEqual(decode_greedy_batch_packet(
            packet, kind=b"BVOT", round_id=0, sender_id=4), records)
        with self.assertRaises(ProtocolError):
            decode_greedy_batch_packet(packet, kind=b"BSCR", round_id=0, sender_id=4)
        with self.assertRaises(ProtocolError):
            encode_greedy_batch_packet(
                kind=b"BVOT", round_id=0, sender_id=4,
                records=tuple((i, i) for i in range(149)))

    def test_zero_loss_one_epoch_cost_once_batched_vote_and_paid_commit(self):
        result = run_voting("greedy_batch")
        self.assertTrue(result.full_assignment_success)
        self.assertEqual(len(result.rounds), 1)
        self.assertEqual(result.assigned_pairs,
                         solve_sequential_greedy_reference(MATRIX).assigned_pairs)
        events = result.rounds[0].coordination.events
        self.assertEqual(sum(e.phase == "cost" for e in events), 4)
        self.assertEqual(sum(e.phase == "vote" for e in events), 4)
        self.assertEqual(sum(e.phase == "vote_score_announcement" for e in events), 4)
        self.assertEqual(sum(e.phase == "commit" for e in events), 4)
        self.assertEqual(result.payload_bytes, sum(e.payload_bytes for e in events))
        self.assertLess(result.global_agreement_ms,
                        run_voting("greedy_task").global_agreement_ms)

    def test_loss_does_not_rebroadcast_cost_or_duplicate_executors(self):
        result = run_voting("greedy_batch", packet_loss=1.0)
        self.assertGreaterEqual(len(result.rounds), 2)
        all_events = [ev for round_ in result.rounds for ev in round_.coordination.events]
        self.assertEqual(sum(e.phase == "cost" for e in all_events), 4)
        self.assertEqual(sum(e.phase == "commit" for e in all_events),
                         len(result.assigned_pairs))
        validate_one_to_one_commits(result.assigned_pairs)
        self.assertEqual(len(result.assigned_pairs) + len(result.remaining_task_ids), 4)


if __name__ == "__main__":
    unittest.main()
