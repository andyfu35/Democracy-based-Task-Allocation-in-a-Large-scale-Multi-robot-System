"""P2G central Cost retry owner and first-family one-pass regression."""
from __future__ import annotations

import unittest

from democracy_mrta.centralized_method import (
    simulate_one_shot_centralized, validate_centralized_retry_limit,
    validate_centralized_planning_rule,
)
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import EmpiricalLatencyProfile
from democracy_mrta.optimizer import (
    solve_visible_batched_greedy_assignment,
    solve_visible_task_ordered_greedy_assignment,
)
from democracy_mrta.coordination import simulate_democracy_hungarian_retirement


def profile():
    return EmpiricalLatencyProfile(
        "test", "test", "test", "2", "test", "ax_160mhz_6ghz",
        "test", 120.0, 181.0, (10.0,15.0,25.0),
    )


COSTS = ((2.,1.,4.),(4.,2.,3.),(9.,3.,1.))
TASKS = ((0.,0.),(1.,0.),(0.,1.))


class FixedSampler:
    def sample_ms(self, key):
        return 1.0


class ExtremeLoss:
    def is_delivered(self, key, probability):
        return probability < 1.0


class CentralizedRetryTests(unittest.TestCase):
    def test_opt_in_zero_loss_is_exact_one_shot(self):
        args=dict(cost_matrix=COSTS,task_positions=TASKS,
                  profile=profile(),seed=12,p_loss=0.0)
        original=simulate_one_shot_centralized(**args)
        explicit=simulate_one_shot_centralized(**args,max_cost_rounds=1)
        retry=simulate_one_shot_centralized(**args,max_cost_rounds=300)
        self.assertEqual(original,explicit)
        self.assertEqual(retry.assignment,original.assignment)
        self.assertEqual(retry.sender_bytes,original.sender_bytes)
        self.assertEqual(retry.native_stop_ms,original.native_stop_ms)
        self.assertEqual(retry.cost_rounds_executed,1)
        self.assertEqual(retry.assignment,
            solve_visible_batched_greedy_assignment(
                COSTS,frozenset(range(3))).assigned_pairs)

    def test_full_drop_resends_and_charges_each_physical_send(self):
        one=simulate_one_shot_centralized(
            cost_matrix=COSTS,task_positions=TASKS,
            profile=profile(),seed=12,p_loss=1.0)
        repeated=simulate_one_shot_centralized(
            cost_matrix=COSTS,task_positions=TASKS,
            profile=profile(),seed=12,p_loss=1.0,max_cost_rounds=4)
        self.assertEqual(repeated.cost_rounds_executed,4)
        self.assertEqual(repeated.cost_sender_sends,2*4)
        self.assertEqual(repeated.cost_sender_bytes,8*(16+8*3))
        self.assertEqual(repeated.cost_receiver_drops,8)
        self.assertEqual(repeated.received_robot_ids,(0,))
        self.assertFalse(repeated.native_success)
        self.assertEqual(repeated.assignment,one.assignment)
        self.assertGreater(repeated.sender_bytes,one.sender_bytes)
        self.assertGreater(repeated.native_stop_ms,one.native_stop_ms)

    def test_validate_retry_limit_at_true_owner(self):
        for limit in (0,301,True,2.5):
            with self.subTest(limit=limit):
                with self.assertRaises(ProtocolError) as caught:
                    validate_centralized_retry_limit(max_cost_rounds=limit)
                self.assertEqual(caught.exception.diagnostic.owner,
                                 "democracy_mrta.centralized_method")
                self.assertEqual(caught.exception.diagnostic.category,"data")
                self.assertEqual(caught.exception.diagnostic.code,
                                 "P2G_INVALID_CENTRAL_COST_ROUNDS")

    def test_one_pass_serial_never_voted_same_task_twice(self):
        costs=COSTS
        for loss in (0.0,1.0):
            result=simulate_democracy_hungarian_retirement(
                cost_matrix=costs,sampler=FixedSampler(),
                loss_sampler=ExtremeLoss(),p_loss=loss,p_vote_loss=loss,
                phase_timeout_ms=20.,max_rounds=len(costs[0]),
                voting_strategy="greedy_batch",
                vote_decision_rule="received_plurality",
                cost_repetitions=1,vote_repetitions=1,
                enforce_vote_deadline=True,batch_vote_scope="one_task",
            )
            task_ids=[r.voted_task_id for r in result.rounds]
            self.assertEqual(len(set(task_ids)),len(task_ids))
            self.assertLessEqual(len(task_ids),len(costs[0]))
            self.assertEqual(sum(e.phase=="cost" for r in result.rounds
                                 for e in r.coordination.events),3)
            self.assertEqual(result.committed_tasks+len(result.remaining_task_ids),3)

    def test_task_ordered_one_shot_central_plan_uses_same_rule_and_single_cost(self):
        matrix=((2.,1.),(3.,100.))
        positions=((0.,0.),(1.,0.))
        result=simulate_one_shot_centralized(
            cost_matrix=matrix,task_positions=positions,
            profile=profile(),seed=12,p_loss=0.0,
            max_cost_rounds=1,planning_rule="task_ordered",
        )
        expected=solve_visible_task_ordered_greedy_assignment(matrix,{0,1})
        global_plan=solve_visible_batched_greedy_assignment(matrix,{0,1})
        self.assertNotEqual(expected.assigned_pairs,global_plan.assigned_pairs)
        self.assertEqual(result.assignment,expected.assigned_pairs)
        self.assertEqual(result.cost_sender_sends,1)
        self.assertEqual(result.cost_rounds_executed,1)
        self.assertTrue(result.native_success)

    def test_task_ordered_central_loss_does_not_restore_missing_cost(self):
        matrix=((2.,1.),(3.,100.))
        result=simulate_one_shot_centralized(
            cost_matrix=matrix,task_positions=((0.,0.),(1.,0.)),
            profile=profile(),seed=12,p_loss=1.0,
            max_cost_rounds=1,planning_rule="task_ordered",
        )
        self.assertEqual(result.received_robot_ids,(0,))
        self.assertEqual(result.assignment,((0,0),))
        self.assertFalse(result.native_success)
        self.assertEqual(result.cost_sender_sends,1)

    def test_task_ordered_voting_is_one_full_batch_not_serial_epochs(self):
        matrix=((2.,1.),(3.,100.))
        def run(strategy,loss):
            return simulate_democracy_hungarian_retirement(
                cost_matrix=matrix,sampler=FixedSampler(),
                loss_sampler=ExtremeLoss(),p_loss=loss,p_vote_loss=loss,
                phase_timeout_ms=20.,max_rounds=1,
                voting_strategy=strategy,vote_decision_rule="received_plurality",
                cost_repetitions=1,vote_repetitions=1,
                enforce_vote_deadline=True,batch_vote_scope="all",
            )
        task_ordered=run("greedy_batch_task_order",0.)
        global_greedy=run("greedy_batch",0.)
        expected=solve_visible_task_ordered_greedy_assignment(matrix,{0,1})
        self.assertEqual(task_ordered.assigned_pairs,expected.assigned_pairs)
        self.assertNotEqual(task_ordered.assigned_pairs,global_greedy.assigned_pairs)
        self.assertEqual(len(task_ordered.rounds),1)
        self.assertEqual(len(task_ordered.rounds[0].coordination.events),9)
        vote=[e for e in task_ordered.rounds[0].coordination.events
              if e.phase=="vote"]
        self.assertEqual(len(vote),2)
        self.assertEqual([e.payload_bytes for e in vote],[32,32])
        lost=run("greedy_batch_task_order",1.)
        self.assertLess(len(lost.assigned_pairs),2)
        self.assertEqual(len(lost.rounds),1)

    def test_invalid_task_order_central_planner_is_explicitly_rejected(self):
        with self.assertRaises(ProtocolError) as caught:
            validate_centralized_planning_rule(planning_rule="global_maybe")
        self.assertEqual(caught.exception.diagnostic.code,
                         "P2G_INVALID_CENTRAL_GREEDY_RULE")
        self.assertEqual(caught.exception.diagnostic.category,"planning")


if __name__=="__main__":
    unittest.main()
