"""P2F native sequential Global Greedy voting regression."""
from __future__ import annotations

import unittest

from democracy_mrta.coordination import (
    simulate_democracy_hungarian_retirement,
    validate_batch_vote_scope, collect_greedy_batch_votes,
)
from democracy_mrta.optimizer import solve_visible_batched_greedy_assignment
from democracy_mrta.diagnostics import ProtocolError

MATRIX = (
    (8., 5., 1.),
    (1., 8., 5.),
    (5., 1., 8.),
)

class FixedSampler:
    def sample_ms(self, key):
        return 1.0

class BernoulliExtreme:
    def is_delivered(self, key, probability):
        return probability < 1.0

def run(scope, loss=0.0):
    return simulate_democracy_hungarian_retirement(
        cost_matrix=MATRIX, sampler=FixedSampler(),
        loss_sampler=BernoulliExtreme(),
        p_loss=loss, p_vote_loss=loss, phase_timeout_ms=20.0,
        max_rounds=20, voting_strategy="greedy_batch",
        vote_decision_rule="received_plurality",
        cost_repetitions=1, vote_repetitions=1,
        enforce_vote_deadline=True, batch_vote_scope=scope,
    )

class P2FSequentialVotingTests(unittest.TestCase):
    def test_reject_scope_without_greedy_batch(self):
        with self.assertRaises(ProtocolError) as caught:
            validate_batch_vote_scope(voting_strategy="greedy_task",
                                      batch_vote_scope="one_task")
        self.assertEqual(caught.exception.diagnostic.code,
                         "P2F_INVALID_BATCH_VOTE_SCOPE")

    def test_no_loss_complete_for_both_repeatable_modes(self):
        reference=solve_visible_batched_greedy_assignment(MATRIX, {0,1,2})
        batch=run("all")
        serial=run("one_task")
        self.assertTrue(batch.full_assignment_success)
        self.assertTrue(serial.full_assignment_success)
        self.assertEqual(len(batch.rounds),1)
        self.assertEqual(len(serial.rounds),3)
        self.assertEqual(batch.assigned_pairs,reference.assigned_pairs)
        self.assertEqual(len(serial.assigned_pairs),3)
        self.assertEqual(serial.committed_tasks,3)
        self.assertEqual(
            sum(e.phase=="cost" for r in serial.rounds for e in r.coordination.events),3)
        for r in serial.rounds:
            vote_frames=[e for e in r.coordination.events if e.phase=="vote"]
            self.assertTrue(vote_frames)
            self.assertTrue(all(e.payload_bytes==24 for e in vote_frames))
            self.assertEqual(len(r.newly_committed_pairs),1)
        self.assertGreater(serial.logical_message_count,batch.logical_message_count)
        self.assertGreater(serial.global_agreement_ms,batch.global_agreement_ms)

    def test_full_loss_keeps_one_initial_cost_snapshot_and_no_duplicate(self):
        for scope in ("all","one_task"):
            result=run(scope,1.0)
            self.assertEqual(
                sum(e.phase=="cost" for r in result.rounds for e in r.coordination.events),3)
            self.assertEqual(len(result.assigned_pairs)+len(result.remaining_task_ids),3)
            self.assertEqual(len(set(r for r,t in result.assigned_pairs)),
                             len(result.assigned_pairs))
            self.assertLessEqual(len(result.rounds),20)

    def test_default_scope_matches_original_batch(self):
        normal=run("all")
        original=simulate_democracy_hungarian_retirement(
            cost_matrix=MATRIX,sampler=FixedSampler(),
            loss_sampler=BernoulliExtreme(),p_loss=0.,p_vote_loss=0.,
            phase_timeout_ms=20.,max_rounds=20,voting_strategy="greedy_batch",
            vote_decision_rule="received_plurality",cost_repetitions=1,
            vote_repetitions=1,enforce_vote_deadline=True,
        )
        self.assertEqual(normal.assigned_pairs,original.assigned_pairs)
        self.assertEqual(normal.payload_bytes,original.payload_bytes)
        self.assertEqual(normal.global_agreement_ms,original.global_agreement_ms)

if __name__=="__main__":
    unittest.main()
