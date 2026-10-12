"""E9F-1: sender-paid Cost-row repetition in original Democracy owner."""
from __future__ import annotations

import unittest

from democracy_mrta.coordination import (
    capture_retirement_cost_snapshot, simulate_democracy_hungarian_retirement,
    validate_cost_repetitions, cost_row_payload_bytes,
)
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import BernoulliLossSampler, SenderPayloadBudget


class ConstantLatency:
    def sample_ms(self, key: str) -> float:
        return 1.0


class CopyOneOnlyLoss:
    def __init__(self):
        self.keys = []

    def is_delivered(self, key, probability):
        self.keys.append(key)
        return "|copy=1" in key


class E9FCostRedundancyTests(unittest.TestCase):
    def fixture(self, cost_repetitions=1, p_loss=0, budget=None, **extras):
        kwargs = dict(
            cost_matrix=((1.0,10.0),(10.0,1.0),(5.0,5.0)),
            sampler=ConstantLatency(),
            loss_sampler=BernoulliLossSampler(seed=7),
            p_loss=p_loss, p_vote_loss=p_loss,
            phase_timeout_ms=10.0, max_rounds=10,
            voting_strategy="greedy_task",
            vote_decision_rule="quarter_plurality",
            vote_repetitions=1, send_budget=budget,
            cost_repetitions=cost_repetitions,
        )
        kwargs.update(extras)
        return kwargs

    def test_default_original_one_copy_is_bitwise_equivalent_to_explicit_one(self):
        args=self.fixture(p_loss=0.32)
        baseline=dict(args)
        baseline.pop("cost_repetitions")
        self.assertEqual(simulate_democracy_hungarian_retirement(**baseline),
                         simulate_democracy_hungarian_retirement(**args))

    def test_physical_paid_cost_copies_and_per_copy_delivery_keys(self):
        snapshot=capture_retirement_cost_snapshot(
            cost_matrix=((1.0,10.0),(10.0,1.0),(4.0,4.0)),
            sampler=ConstantLatency(),loss_sampler=BernoulliLossSampler(seed=1),
            p_loss=0.0,phase_timeout_ms=10.0,cost_repetitions=3)
        events=snapshot.events
        self.assertEqual(len(events),9)
        self.assertEqual([e.transmission_index for e in events],[0,1,2]*3)
        self.assertTrue(all(e.payload_bytes==cost_row_payload_bytes(2) for e in events))
        self.assertEqual({e.round_id for e in events},{0})
        self.assertEqual(len(snapshot.deliveries),9*2)
        self.assertEqual(snapshot.ready_times_ms,(30.0,30.0,30.0))
        self.assertTrue(all(view==frozenset({0,1,2})
                            for view in snapshot.visible_by_voter))

    def test_physical_cost_retransmissions_restore_only_received_rows(self):
        recorder=CopyOneOnlyLoss()
        args=dict(cost_matrix=((1.0,3.0),(3.0,1.0)),
                  sampler=ConstantLatency(),loss_sampler=recorder,
                  p_loss=.5,phase_timeout_ms=10.0)
        original=capture_retirement_cost_snapshot(**args,cost_repetitions=1)
        repeated=capture_retirement_cost_snapshot(**args,cost_repetitions=2)
        self.assertEqual(original.visible_by_voter,(frozenset({0}),frozenset({1})))
        self.assertEqual(repeated.visible_by_voter,
                         (frozenset({0,1}),frozenset({0,1})))
        self.assertEqual(len(original.events),2)
        self.assertEqual(len(repeated.events),4)
        self.assertTrue(any("|copy=1" in key for key in recorder.keys))
        self.assertTrue(any(key.endswith("|round=0") for key in recorder.keys))
        self.assertEqual(len(set(recorder.keys)),4)

    def test_full_drop_has_no_invented_peer_costs(self):
        snapshot=capture_retirement_cost_snapshot(
            cost_matrix=((1.0,3.0),(3.0,1.0)),
            sampler=ConstantLatency(),loss_sampler=BernoulliLossSampler(seed=3),
            p_loss=1.0,phase_timeout_ms=10.0,cost_repetitions=5)
        self.assertEqual(snapshot.visible_by_voter,
                         (frozenset({0}),frozenset({1})))
        self.assertEqual(len(snapshot.events),10)
        self.assertEqual(len(snapshot.deliveries),10)
        self.assertFalse(any(x.delivered for x in snapshot.deliveries))

    def test_greedy_rounds_retain_only_one_initial_paid_cost_stage(self):
        args=self.fixture(cost_repetitions=3,p_loss=0)
        outcome=simulate_democracy_hungarian_retirement(**args)
        costs=[event for trace in outcome.rounds for event in trace.coordination.events
               if event.phase=="cost"]
        self.assertEqual(len(costs),9)
        self.assertEqual(sum(event.payload_bytes for event in costs),9*32)
        self.assertTrue(all(event.round_id==0 for event in costs))
        self.assertTrue(outcome.full_assignment_success)
        self.assertEqual(outcome.committed_tasks,2)

    def test_invalid_repetitions_first_named_data_diagnostic(self):
        for value in (0,6,-1,True,1.5,"2"):
            with self.subTest(value=value),self.assertRaises(ProtocolError) as ctx:
                validate_cost_repetitions(value)
            diag=ctx.exception.diagnostic
            self.assertEqual(
                (diag.owner,diag.function,diag.category,diag.code),
                ("coordination","validate_cost_repetitions","data",
                 "INVALID_COST_REPETITIONS")
            )

    def test_repetition_rejected_without_original_greedy_cost_owner(self):
        with self.assertRaises(ProtocolError) as ctx:
            simulate_democracy_hungarian_retirement(**self.fixture(
                cost_repetitions=2,voting_strategy="hungarian",
                vote_decision_rule="strict_majority",
            ))
        diag=ctx.exception.diagnostic
        self.assertEqual((diag.function,diag.category,diag.code),
                         ("validate_repeated_cost_scope","contract",
                          "REPEATED_COST_REQUIRES_GREEDY_COST_SOURCE"))

    def test_budgeted_cost_copy_denial_never_emits_unpaid_packet(self):
        # One row is 32 B. 64 B permits two copies of robot 0, then rejects
        # robot 0's third. There must not be fabricated assignment or Commit.
        budget=SenderPayloadBudget(64)
        outcome=simulate_democracy_hungarian_retirement(
            **self.fixture(cost_repetitions=3,p_loss=0,budget=budget))
        self.assertEqual(budget.sent_bytes,64)
        self.assertEqual(budget.sent_messages,2)
        self.assertTrue(outcome.budget_exhausted)
        self.assertEqual(outcome.committed_tasks,0)
        self.assertEqual(outcome.payload_bytes,64)
        self.assertEqual(outcome.budget_stop_phase,"cost")
        self.assertEqual(len([e for t in outcome.rounds for e in t.coordination.events
                              if e.phase=="cost"]),2)


if __name__=="__main__":
    unittest.main()
