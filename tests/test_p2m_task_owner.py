"""P2M: only deterministic task-owner method (no legacy comparison runs)."""
from __future__ import annotations

from types import SimpleNamespace
import unittest

from democracy_mrta.claim_resolution import (
    coordinate_p2m_task_owners,decode_p2m_owner_decision,
    encode_p2m_owner_decision,p2m_task_owner_id,
)
from democracy_mrta.coordination import P2KLocalVoteResult
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler,EmpiricalLatencySampler,EmpiricalLatencyProfile,
)
from experiments.run_p2m_task_owner import (
    analyze_p2m_owner_result,validate_p2m_axes,
)


def profile():
    return EmpiricalLatencyProfile(
        source_repository="test",source_commit="test",source_blob_sha="0"*40,
        location="2",location_label="p2m",config="ax_160mhz_6ghz",
        config_label="synthetic",steady_start_s=0.0,steady_end_s=4.0,
        samples_ms=(3.0,4.0,5.0,6.0),
    )


def fixture():
    # Each receiver sees 600 valid logical tickets in its own 3x3 view.
    # R0 & R1 initially claim T0; own receipt ratio selects R1.
    views=(
        ((120,30,50),(50,90,40),(30,80,110)),
        ((10,70,50),(160,20,20),(30,110,130)),
        ((40,100,20),(50,30,60),(110,70,120)),
    )
    return P2KLocalVoteResult(
        local_assignments=(
            ((0,0),(1,1),(2,2)),
            ((1,0),(0,1),(2,2)),
            ((0,0),(1,1),(2,2)),
        ),
        robot_claims=((0,0),(1,0),(2,2)),
        local_vote_views=views,
        cost_visible_rows=tuple(frozenset((0,1,2)) for _ in range(3)),
        events=(),deliveries=(),decision_time_ms=10.0,
        cost_completion_ms=5.0,
    )


class P2MTaskOwnerTests(unittest.TestCase):
    def setUp(self):
        self.costs=((1.0,3.0,9.0),(2.0,8.0,9.0),(8.0,9.0,1.0))

    def run_owner(self,p_loss,max_attempts=24):
        return coordinate_p2m_task_owners(
            run=fixture(),cost_matrix=self.costs,
            votes_per_voter=600,
            sampler=EmpiricalLatencySampler(profile(),7),
            loss_sampler=BernoulliLossSampler(7),p_loss=p_loss,
            max_attempts=max_attempts,max_rounds=10,
        )

    def test_deterministic_public_owner_map(self):
        self.assertEqual(p2m_task_owner_id(task_id=29,robots=100),29)
        self.assertEqual(p2m_task_owner_id(task_id=104,robots=100),4)
        with self.assertRaises(ProtocolError):
            p2m_task_owner_id(task_id=-1,robots=100)

    def test_grant_only_valid_from_task_owner(self):
        packet=encode_p2m_owner_decision(
            round_id=1,owner_id=0,robot_id=2,task_id=0,granted=True,
        )
        self.assertEqual(len(packet),20)
        self.assertTrue(decode_p2m_owner_decision(
            packet,round_id=1,owner_id=0,
            robot_id=2,task_id=0,robots=3,
        ))
        with self.assertRaises(ProtocolError) as exc:
            decode_p2m_owner_decision(
                packet,round_id=1,owner_id=1,
                robot_id=2,task_id=0,robots=3,
            )
        self.assertEqual(
            exc.exception.diagnostic.code,"P2M_UNAUTHORISED_OWNER_DECISION",
        )

    def test_zero_loss_conflicts_resolve_without_global_score(self):
        result=self.run_owner(0.0)
        self.assertEqual(
            set(result.executed_pairs),{(0,1),(1,0),(2,2)},
        )
        self.assertEqual(len(result.reserved_pairs),3)
        self.assertEqual(result.conflicted_task_rounds,1)
        self.assertEqual(result.rounds_executed,3)
        self.assertEqual(result.blocked_robot_ids,())
        self.assertEqual(result.reassignment_requests,2)
        self.assertTrue(all(e.phase in (
            "owner_request","owner_request_ack",
            "owner_decision","owner_decision_ack",
        ) for e in result.events))
        self.assertEqual(
            sum(e.payload_bytes for e in result.events),result.sender_bytes,
        )
        self.assertFalse(any(e.receiver_id==-1 for e in result.events))
        self.assertEqual(len({r for r,t in result.executed_pairs}),3)
        self.assertEqual(len({t for r,t in result.executed_pairs}),3)
        self.assertTrue(any(d["task"]==0 and
                            d["reserved_winner"]==1 and
                            len(d["confirmed_claimants"])==2
                            for d in result.owner_decisions))

    def test_owner_must_not_use_hidden_ack_delivery_to_filter_received_bids(self):
        # Every REQUEST genuinely reaches its owner, but request-receipt
        # ACKs fail. The owner can still arbitrate from its own actually
        # received CLAIM, and its separately delivered GRANT/DENY tells
        # the robot whether to execute or try another task.
        class DropOwnerReceiptAck:
            def is_delivered(self,key,p_loss):
                return "|owner_request_ack|" not in key

        result=coordinate_p2m_task_owners(
            run=fixture(),cost_matrix=self.costs,
            votes_per_voter=600,
            sampler=EmpiricalLatencySampler(profile(),3),
            loss_sampler=DropOwnerReceiptAck(),p_loss=0.30,
            max_attempts=2,max_rounds=10,
        )
        self.assertEqual(
            set(result.executed_pairs),{(0,1),(1,0),(2,2)},
        )
        self.assertTrue(any(
            d["task"]==0 and d["reserved_winner"]==1
            for d in result.owner_decisions
        ))
        self.assertIsNone(result.first_diagnostic)
        self.assertGreaterEqual(result.request_receipt_ack_timeouts,1)
        self.assertTrue(any(
            e.phase=="owner_request_ack" for e in result.events
        ))
        self.assertFalse(any(
            obs.delivered for obs in result.deliveries
            if obs.phase=="owner_request_ack"
        ))

    def test_all_links_lost_fails_partially_but_never_double_executes(self):
        result=self.run_owner(1.0,max_attempts=2)
        self.assertEqual(len(result.executed_pairs),2)
        self.assertEqual(set(result.executed_pairs),{(0,0),(2,2)})
        self.assertEqual(result.blocked_robot_ids,(1,))
        self.assertEqual(result.first_diagnostic.code,"P2M_REQUEST_ACK_LIMIT")
        self.assertEqual(len({t for r,t in result.executed_pairs}),
                         len(result.executed_pairs))
        self.assertTrue(all(e.phase=="owner_request" for e in result.events))
        self.assertEqual(len(result.events),2)

    def test_owner_agreement_costs_only_new_executors(self):
        result=self.run_owner(0.0)
        scene=SimpleNamespace(
            num_robots=3,num_tasks=3,cost_matrix=self.costs,
        )
        metrics=analyze_p2m_owner_result(
            scene=scene,local_run=fixture(),owner_result=result,
        )
        self.assertEqual(metrics["preclaim_duplicate_tasks"],1)
        self.assertEqual(metrics["duplicate_task_count"],0)
        self.assertEqual(metrics["unassigned_task_count"],0)
        self.assertEqual(metrics["full_valid_allocation"],1)

    def test_one_new_method_axis_validation(self):
        args=SimpleNamespace(
            losses="0.00,0.30,0.50,0.90",votes=1000,
            robots=100,tasks=100,seeds=10,first_seed=0,
            temperature=5.0,max_attempts=24,max_rounds=101,
            audit_seeds=1,
        )
        self.assertEqual(validate_p2m_axes(args),(0,30,50,90))
        args.votes=500
        with self.assertRaises(ProtocolError):
            validate_p2m_axes(args)


if __name__=="__main__":
    unittest.main()
