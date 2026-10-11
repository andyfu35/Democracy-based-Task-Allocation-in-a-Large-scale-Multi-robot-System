from __future__ import annotations

import unittest

from democracy_mrta.cbaa import (
    CBAALocalState,
    audit_cbaa_local_agreement,
    cbaa_auction_phase,
    cbaa_bid_outbids,
    cbaa_consensus_phase,
    simulate_cbaa,
)
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import BernoulliLossSampler


class ConstantLatency:
    def sample_ms(self, key: str) -> float:
        return 10.0


class DelayedLatency:
    def sample_ms(self, key: str) -> float:
        return 15.0


class CBAASingleAssignmentTests(unittest.TestCase):
    def simulate(
        self, costs, *, p=0.0, iterations=3, capture_audit=False, latency=None,
    ):
        return simulate_cbaa(
            cost_matrix=costs,
            sampler=latency or ConstantLatency(),
            loss_sampler=BernoulliLossSampler(seed=7),
            loss_probability=p,
            phase_timeout_ms=10.0,
            max_iterations=iterations,
            capture_audit=capture_audit,
        )

    def test_zero_loss_single_assignment_without_any_vote_or_central_commit(self):
        result = self.simulate(((1.0, 10.0), (10.0, 1.0)), iterations=3,
                               capture_audit=True)
        self.assertEqual(result.method, "cbaa_sync_single_assignment")
        self.assertEqual(result.observer_agreed_pairs, ((0, 0), (1, 1)))
        self.assertEqual(result.local_claims, ((0, 0), (1, 1)))
        self.assertTrue(result.full_observer_agreement)
        self.assertEqual(result.task_agreement_rate, 1.0)
        self.assertEqual(result.conflicting_task_ids, ())
        self.assertEqual(result.unconfirmed_task_ids, ())
        self.assertEqual(result.logical_message_count, 6)
        self.assertEqual(result.payload_bytes, 6 * (16 + 2 * (8 + 4)))
        self.assertEqual(result.delivery_attempts, 6)
        self.assertEqual(result.delivery_drops, 0)
        self.assertEqual(result.elapsed_ms, 30.0)
        self.assertEqual({e.phase for e in result.audit_events}, {"cbaa_consensus"})
        self.assertEqual({e.receiver_id for e in result.audit_events}, {-1})
        self.assertTrue(all(d.delivered for d in result.audit_deliveries))
        self.assertFalse(any(e.phase in ("vote", "commit", "fallback_self_claim")
                             for e in result.audit_events))

    def test_losing_initial_collision_releases_then_rebids_on_another_task(self):
        costs = ((1.0, 20.0), (1.1, 100.0))
        one_round = self.simulate(costs, iterations=1)
        self.assertEqual(one_round.observer_agreed_pairs, ((0, 0),))
        self.assertEqual(one_round.unconfirmed_task_ids, (1,))
        self.assertEqual(one_round.local_claims, ((0, 0),))
        two_rounds = self.simulate(costs, iterations=2)
        self.assertTrue(two_rounds.full_observer_agreement)
        self.assertEqual(two_rounds.observer_agreed_pairs, ((0, 0), (1, 1)))

    def test_ties_use_lowest_robot_id_then_task_id(self):
        costs = ((1.0, 3.0), (1.0, 3.0))
        first = self.simulate(costs, iterations=1)
        self.assertEqual(first.local_claims, ((0, 0),))
        self.assertEqual(first.unconfirmed_task_ids, (1,))
        second = self.simulate(costs, iterations=2)
        self.assertEqual(second.observer_agreed_pairs, ((0, 0), (1, 1)))
        self.assertTrue(second.full_observer_agreement)
        self.assertTrue(cbaa_bid_outbids(0.5, 0, 0.5, 1))
        self.assertFalse(cbaa_bid_outbids(0.5, 1, 0.5, 0))

    def test_one_robot_may_claim_at_most_one_task_even_if_more_are_visible(self):
        costs = ((1.0,), (2.0,), (3.0,))
        result = self.simulate(costs, iterations=4)
        self.assertEqual(result.observer_agreed_pairs, ((0, 0),))
        self.assertEqual(result.local_claims, ((0, 0),))
        self.assertTrue(result.full_observer_agreement)
        self.assertEqual(result.logical_message_count, 12)
        self.assertEqual(result.delivery_attempts, 24)

    def test_total_packet_loss_preserves_conflicts_and_disagreed_views(self):
        costs = ((1.0, 10.0), (1.1, 100.0))
        result = self.simulate(costs, p=1.0, iterations=4, capture_audit=True)
        self.assertFalse(result.full_observer_agreement)
        self.assertEqual(result.local_claims, ((0, 0), (1, 0)))
        self.assertEqual(result.observer_agreed_pairs, ())
        self.assertEqual(result.conflicting_task_ids, (0,))
        self.assertEqual(result.unconfirmed_task_ids, (0, 1))
        self.assertEqual(result.delivery_attempts, 8)
        self.assertEqual(result.delivery_drops, 8)
        self.assertEqual(len(result.audit_events), 8)
        self.assertEqual(len(result.audit_deliveries), 8)
        self.assertFalse(any(d.delivered for d in result.audit_deliveries))

    def test_independent_loss_is_seed_deterministic(self):
        costs = ((1.0, 5.0), (2.0, 1.0), (3.0, 2.0))
        first = self.simulate(costs, p=0.35, iterations=5)
        second = self.simulate(costs, p=0.35, iterations=5)
        self.assertEqual(first, second)
        self.assertEqual(first.logical_message_count, 3 * 5)
        self.assertEqual(first.delivery_attempts, 3 * 2 * 5)
        self.assertTrue(0 <= first.delivery_drops <= first.delivery_attempts)

    def test_observer_does_not_fabricate_agreement_from_local_claims(self):
        states = (
            CBAALocalState(0, 0, (0.5, 0.0), (0, None)),
            CBAALocalState(1, 0, (0.4, 0.0), (1, None)),
        )
        claims, agreed, conflicts, unconfirmed = audit_cbaa_local_agreement(states)
        self.assertEqual(claims, ((0, 0), (1, 0)))
        self.assertEqual(agreed, ())
        self.assertEqual(conflicts, (0,))
        self.assertEqual(unconfirmed, (0, 1))

    def test_auction_and_consensus_have_separate_owner_functions(self):
        current = CBAALocalState(1, None, (0.5, 0.0), (0, None))
        bidding = cbaa_auction_phase(state=current, cost_row=(5.0, 3.0))
        self.assertEqual(bidding.assigned_task, 1)
        self.assertEqual(bidding.winning_robots, (0, 1))
        remote = CBAALocalState(0, 1, (0.5, 0.5), (0, 0))
        updated = cbaa_consensus_phase(state=bidding, received=(remote,))
        self.assertIsNone(updated.assigned_task)
        self.assertEqual(updated.winning_robots, (0, 0))

    def test_late_packets_are_not_silently_accepted_into_local_beliefs(self):
        costs = ((1.0, 10.0), (1.1, 100.0))
        result = self.simulate(costs, p=0.0, iterations=2,
                               latency=DelayedLatency(), capture_audit=True)
        self.assertEqual(result.delivery_drops, 0)
        self.assertEqual(result.late_deliveries, result.delivery_attempts)
        self.assertEqual(result.observer_agreed_pairs, ())
        self.assertEqual(result.conflicting_task_ids, (0,))

    def test_nonnegative_score_cost_contract(self):
        with self.assertRaises(ProtocolError) as context:
            self.simulate(((1.0,), (-2.0,)))
        self.assertEqual(context.exception.diagnostic.owner, "democracy_mrta.cbaa")
        self.assertEqual(context.exception.diagnostic.function,
                         "validate_cbaa_configuration")
        self.assertEqual(context.exception.diagnostic.category, "data")
        self.assertEqual(context.exception.diagnostic.code, "CBAA_NEGATIVE_COST")

    def test_invalid_synchronous_time_budget_is_rejected(self):
        with self.assertRaises(ProtocolError) as context:
            self.simulate(((1.0,),), iterations=0)
        self.assertEqual(context.exception.diagnostic.code,
                         "CBAA_INVALID_ITERATION_BUDGET")
        with self.assertRaises(ProtocolError) as context:
            simulate_cbaa(
                cost_matrix=((1.0,),),
                sampler=ConstantLatency(),
                loss_sampler=BernoulliLossSampler(seed=0),
                loss_probability=0.0,
                phase_timeout_ms=0.0,
                max_iterations=1,
            )
        self.assertEqual(context.exception.diagnostic.category, "time")
        self.assertEqual(context.exception.diagnostic.code, "CBAA_INVALID_PHASE_TIMEOUT")

    def test_no_audit_materialized_unless_explicitly_requested(self):
        result = self.simulate(((1.0,), (2.0,)), iterations=3)
        self.assertEqual(result.audit_events, ())
        self.assertEqual(result.audit_deliveries, ())
        self.assertEqual(result.logical_message_count, 6)


if __name__ == "__main__":
    unittest.main()
