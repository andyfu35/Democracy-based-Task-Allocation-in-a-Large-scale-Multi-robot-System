"""P2H: real Vote/Score/Commit per task and the true sequential Centralized owner."""
from __future__ import annotations

from argparse import Namespace
import unittest
import xml.etree.ElementTree as ET

from democracy_mrta.centralized_method import (
    simulate_one_shot_centralized, validate_centralized_assignment_scope,
)
from democracy_mrta.coordination import simulate_democracy_hungarian_retirement
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import EmpiricalLatencyProfile
from democracy_mrta.optimizer import (
    solve_visible_task_ordered_greedy_assignment,
)
from experiments.p2g_plot import FAMILIES, render_p2g_figure
from experiments.run_p2h_sequential_figure1 import (
    LOSSES,MODES,case_keys,validate_p2h_config,
    validate_p2h_zero_loss,summarize_p2h_native,
)


COSTS=((2.,1.,9.),(4.,5.,2.),(8.,3.,4.))
TASKS=((0.,0.),(1.,0.),(0.,1.))


def profile():
    return EmpiricalLatencyProfile(
        "test","test","test","2","test","ax_160mhz_6ghz",
        "test",120.0,181.0,(10.,15.,25.),
    )


class FixedSampler:
    def sample_ms(self,key):
        return 1.0


class FixedLoss:
    def is_delivered(self,key,probability):
        return probability < 1.0


def sample_row(mode,loss,success=True):
    return {
        "loss_percent":loss,"seed":0,"mode":mode,
        "native_success":int(success),"final_feasible":int(success),
        "committed_task_count":100 if success else 50,
        "task_coverage":1.0 if success else 0.5,
        "cost_increase_percent":0.0 if success else "",
        "native_stop_ms":3000.,"native_sender_bytes":105000,
        "rounds_executed":100,
    }


class InteractiveVoteTests(unittest.TestCase):
    def test_each_task_has_exactly_one_vote_epoch_and_retires_after_commit(self):
        result=simulate_democracy_hungarian_retirement(
            cost_matrix=COSTS,sampler=FixedSampler(),
            loss_sampler=FixedLoss(),p_loss=0.,p_vote_loss=0.,
            phase_timeout_ms=20.0,max_rounds=3,
            voting_strategy="greedy_task",
            vote_decision_rule="received_plurality",
            vote_repetitions=1,cost_repetitions=1,
            enforce_vote_deadline=True,batch_vote_scope="all",
        )
        expected=solve_visible_task_ordered_greedy_assignment(
            COSTS,frozenset(range(3))).assigned_pairs
        self.assertEqual(result.assigned_pairs,expected)
        self.assertEqual(tuple(r.voted_task_id for r in result.rounds),(0,1,2))
        self.assertEqual(len(result.rounds),3)
        for k,r in enumerate(result.rounds):
            self.assertEqual(len(r.newly_committed_pairs),1)
            self.assertEqual(r.newly_committed_pairs[0][1],k)
            self.assertEqual(r.active_robot_ids,tuple(
                candidate for candidate in range(3)
                if candidate not in {pair[0] for pair in expected[:k]}
            ))
            self.assertFalse(any(e.phase=="cost" for e in result.rounds[k+1].coordination.events)
                             if k<2 else False)
        self.assertEqual(
            sum(e.phase=="cost" for r in result.rounds for e in r.coordination.events),
            3,
        )

    def test_stale_task_is_not_retried_at_high_loss(self):
        result=simulate_democracy_hungarian_retirement(
            cost_matrix=COSTS,sampler=FixedSampler(),
            loss_sampler=FixedLoss(),p_loss=1.0,p_vote_loss=1.0,
            phase_timeout_ms=20.,max_rounds=3,
            voting_strategy="greedy_task",vote_decision_rule="received_plurality",
            vote_repetitions=1,cost_repetitions=1,enforce_vote_deadline=True,
        )
        self.assertEqual(tuple(r.voted_task_id for r in result.rounds),(0,1,2))
        self.assertEqual(len(result.rounds),3)
        self.assertLessEqual(len(result.assigned_pairs),3)


class SequentialCentralizedTests(unittest.TestCase):
    def test_one_cost_then_one_assignment_commit_per_task(self):
        args=dict(cost_matrix=COSTS,task_positions=TASKS,profile=profile(),
                  seed=12,p_loss=0.)
        original=simulate_one_shot_centralized(**args)
        explicit_batch=simulate_one_shot_centralized(
            **args,assignment_scope="batch")
        self.assertEqual(original,explicit_batch)
        serial=simulate_one_shot_centralized(
            **args,planning_rule="task_ordered",
            assignment_scope="task_sequence",max_cost_rounds=1,
        )
        expected=solve_visible_task_ordered_greedy_assignment(
            COSTS,frozenset(range(3))).assigned_pairs
        self.assertEqual(serial.assignment,expected)
        self.assertEqual(serial.cost_sender_sends,2)
        self.assertEqual(serial.cost_rounds_executed,1)
        self.assertEqual(serial.decision_sender_sends,3)
        self.assertEqual(serial.commit_sender_sends,3)
        self.assertTrue(serial.native_success)
        self.assertGreater(serial.sender_bytes,original.sender_bytes)
        trace=serial.event_ledger["sequential_decision_commit_trace"]
        self.assertEqual(len(trace),3)
        for k,task in enumerate(trace):
            self.assertEqual(task["task_id"],k)
            self.assertGreaterEqual(
                task["commit_send_ms"],task["assignment_arrival_ms"])
            if k:
                self.assertGreaterEqual(
                    task["assignment_send_ms"],trace[k-1]["commit_arrival_ms"],
                )
        phases=serial.event_ledger["network"]["sender_by_phase"]
        self.assertEqual(phases["centralized_assignment"]["sender_sends"],3)
        self.assertEqual(phases["commit"]["sender_sends"],3)

    def test_all_remote_cost_lost_cannot_assign_unseen_robot(self):
        result=simulate_one_shot_centralized(
            cost_matrix=COSTS,task_positions=TASKS,
            profile=profile(),seed=12,p_loss=1.0,
            planning_rule="task_ordered",assignment_scope="task_sequence",
        )
        self.assertEqual(result.received_robot_ids,(0,))
        self.assertEqual(result.assignment,((0,0),))
        self.assertFalse(result.native_success)
        self.assertEqual(result.cost_sender_sends,2)
        self.assertEqual(result.decision_sender_sends,1)
        self.assertEqual(result.commit_sender_sends,1)

    def test_sequential_cannot_silently_enable_global_or_cost_retry(self):
        for planning,max_rounds in (("global",1),("task_ordered",2)):
            with self.subTest(planning=planning,max_rounds=max_rounds):
                with self.assertRaises(ProtocolError) as caught:
                    validate_centralized_assignment_scope(
                        assignment_scope="task_sequence",
                        planning_rule=planning,max_cost_rounds=max_rounds,
                    )
                self.assertEqual(caught.exception.diagnostic.code,
                                 "P2H_SEQUENTIAL_CENTRAL_REQUIRES_ONESHOT_GREEDY")


class P2HStudyTests(unittest.TestCase):
    def test_formal_fixed_one_hundred_pair_grid(self):
        options=Namespace(
            losses=",".join(f"{p/100:.2f}" for p in LOSSES),
            seeds=100,first_seed=0,formal=True,
        )
        self.assertEqual(validate_p2h_config(options),LOSSES)
        self.assertEqual(len(case_keys(LOSSES,0,100)),2000)
        options.seeds=2
        with self.assertRaises(ProtocolError):
            validate_p2h_config(options)

    def test_zero_loss_requires_full_greedy_no_cost_increase(self):
        rows=[sample_row(mode,0) for mode in MODES]
        validate_p2h_zero_loss(rows)
        rows[0]["cost_increase_percent"]=1.0
        with self.assertRaises(ProtocolError) as caught:
            validate_p2h_zero_loss(rows)
        self.assertEqual(caught.exception.diagnostic.code,"P2H_ZERO_LOSS_NOT_GREEDY")

    def test_failed_costs_never_imputed(self):
        rows=[sample_row(mode,90,success=False) for mode in MODES]
        summary=summarize_p2h_native(rows,(90,))
        self.assertEqual(len(summary),2)
        for row in summary:
            self.assertEqual(row["native_complete"],0)
            self.assertEqual(row["quality_sample_count"],0)
            self.assertEqual(row["cost_increase_percent"],"")

    def test_both_figure_families_have_no_bottom_explanatory_text(self):
        rows=[{
            "loss_percent":p,"method":mode,"trials":2,
            "native_complete":2,"completion_rate_percent":100.,
            "quality_sample_count":2,"cost_increase_percent":0.,
            "mean_stop_s":5.,"mean_sender_kb":210.,
        } for p in (0,90) for mode in FAMILIES["interactive"]]
        svg=render_p2g_figure(rows,(0,90),"interactive")
        self.assertIn('viewBox="0 0 1800 1120"',svg)
        self.assertIn("Figure 1 · Sequential Task Allocation",svg)
        self.assertNotIn("Cost line points exist only",svg)
        self.assertNotIn("Bytes include attempted sender",svg)
        self.assertTrue(ET.fromstring(svg).tag.endswith("svg"))
        self.assertEqual(FAMILIES["interactive"],MODES)


if __name__=="__main__":
    unittest.main()
