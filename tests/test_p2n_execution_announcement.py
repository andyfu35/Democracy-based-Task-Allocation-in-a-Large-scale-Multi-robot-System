"""P2N: only test EXECUTING announcements, local receipts and owner safety."""
from __future__ import annotations

from types import SimpleNamespace
import unittest

from democracy_mrta.claim_resolution import (
    coordinate_p2m_task_owners,
    decode_p2n_execution_announcement,
    encode_p2n_execution_announcement,
    validate_p2n_announcement_repetitions,
)
from democracy_mrta.coordination import P2KLocalVoteResult
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler, EmpiricalLatencySampler, EmpiricalLatencyProfile,
)
from experiments.run_p2n_execution_announcement import (
    FIELDS, PHASES, parse_args, summarize_p2n_rows, validate_p2n_axes,
)


def test_profile():
    return EmpiricalLatencyProfile(
        source_repository="test",source_commit="test",
        source_blob_sha="0"*40,location="2",location_label="p2n",
        config="ax_160mhz_6ghz",config_label="synthetic",
        steady_start_s=0.0,steady_end_s=4.0,
        samples_ms=(3.0,4.0,5.0,6.0),
    )


def source_fixture():
    # Same native P2M 3x3 scenario: R0/R1 contest T0; R2 claims T2.
    # After losing T0, R0 would prefer occupied T2 over unclaimed T1.
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


class P2NExecutionAnnouncementTests(unittest.TestCase):
    def setUp(self):
        self.costs=((1.0,3.0,9.0),(2.0,8.0,9.0),(8.0,9.0,1.0))

    def run_owner(self, loss_sampler=None, loss=0.0, repeats=3):
        return coordinate_p2m_task_owners(
            run=source_fixture(),cost_matrix=self.costs,
            votes_per_voter=600,
            sampler=EmpiricalLatencySampler(test_profile(),13),
            loss_sampler=loss_sampler or BernoulliLossSampler(13),
            p_loss=loss,max_attempts=3,max_rounds=10,
            execution_announce_repetitions=repeats,
        )

    def test_20_byte_wire_rejects_forged_owner_and_stale_epoch(self):
        wire=encode_p2n_execution_announcement(
            claim_round=2,robot_id=1,task_id=0,robots=3,
        )
        self.assertEqual(len(wire),20)
        self.assertEqual(decode_p2n_execution_announcement(
            wire,claim_round=2,sender_id=1,task_id=0,
            robots=3,tasks=3,
        ),(1,0))
        for altered in (
            (wire,1,1,0),
            (wire,2,2,0),
            (wire,2,1,1),
            (wire[:16]+(1).to_bytes(4,"little"),2,1,0),
        ):
            data,rnd,robot,task=altered
            with self.assertRaises(ProtocolError):
                decode_p2n_execution_announcement(
                    data,claim_round=rnd,sender_id=robot,
                    task_id=task,robots=3,tasks=3,
                )
        with self.assertRaises(ProtocolError):
            validate_p2n_announcement_repetitions(-1)
        with self.assertRaises(ProtocolError):
            validate_p2n_announcement_repetitions(6)
        self.assertEqual(validate_p2n_announcement_repetitions(0),0)
        self.assertEqual(validate_p2n_announcement_repetitions(3),3)

    def test_three_announcements_after_owner_grant_reduce_occupied_requests(self):
        # Ownership is unchanged, but R0 now knows R2 is executing T2,
        # so it chooses free T1 immediately instead of querying occupied T2.
        old=self.run_owner(repeats=0)
        new=self.run_owner(repeats=3)
        self.assertEqual(set(old.executed_pairs),set(new.executed_pairs))
        self.assertEqual(set(new.executed_pairs),{(0,1),(1,0),(2,2)})
        self.assertEqual(old.rounds_executed,3)
        self.assertEqual(new.rounds_executed,2)
        self.assertGreaterEqual(new.avoided_announced_requests,1)
        self.assertEqual(set(new.announced_executions),set(new.executed_pairs))
        sends=[event for event in new.events
               if event.phase=="execution_announce"]
        self.assertEqual(len(sends),3*len(new.executed_pairs))
        self.assertEqual(sum(e.payload_bytes for e in sends),9*20)
        self.assertEqual({e.payload_bytes for e in sends},{20})
        self.assertTrue(all(e.receiver_id==-1 for e in sends))
        self.assertEqual(
            set(new.recipient_seen_executing_tasks[0]),{0,1,2},
        )
        self.assertEqual(old.announced_executions,())
        self.assertEqual(old.recipient_seen_executing_tasks,())
        self.assertTrue(all(e.phase!="execution_announce" for e in old.events))
        self.assertEqual(len({t for r,t in new.executed_pairs}),3)

    def test_broadcast_loss_does_not_leak_owner_reservations_to_peers(self):
        class DropOnlyExecAnnouncements:
            def is_delivered(self,key,p_loss):
                return not key.startswith("broadcast|execution_announce|")

        new=self.run_owner(loss_sampler=DropOnlyExecAnnouncements(),loss=0.30)
        self.assertEqual(
            set(new.executed_pairs),{(0,1),(1,0),(2,2)},
        )
        self.assertEqual(new.rounds_executed,3)
        self.assertEqual(new.avoided_announced_requests,0)
        self.assertEqual(len(new.announced_executions),3)
        self.assertEqual(sum(
            e.phase=="execution_announce" for e in new.events),9)
        self.assertTrue(all(
            not obs.delivered for obs in new.deliveries
            if obs.phase=="execution_announce"
        ))
        for robot,tasks in enumerate(new.recipient_seen_executing_tasks):
            own={task for sender,task in new.announced_executions
                 if sender==robot}
            self.assertEqual(set(tasks),own)

    def test_every_recipient_cache_equals_only_its_actual_receipts(self):
        result=self.run_owner(loss=0.50)
        for robot in range(3):
            expected={
                task for sender,task in result.announced_executions
                if sender==robot
            }
            expected.update(
                obs.task_id for obs in result.deliveries
                if obs.phase=="execution_announce" and obs.delivered
                and obs.receiver_id==robot
            )
            self.assertEqual(
                set(result.recipient_seen_executing_tasks[robot]),expected)
        self.assertEqual(
            len({task for robot,task in result.executed_pairs}),
            len(result.executed_pairs),
        )

    def test_p2n_only_new_method_axes(self):
        args=parse_args(["--output-root","results/_p2n_test"])
        self.assertEqual(validate_p2n_axes(args),(0,30,50,90))
        self.assertEqual(args.announcement_repetitions,3)
        self.assertEqual(args.votes,1000)
        self.assertIn("execution_announce_sends",FIELDS)
        self.assertEqual(PHASES[-1],"execution_announce")
        args.announcement_repetitions=0
        with self.assertRaises(ProtocolError):
            validate_p2n_axes(args)

    def test_single_method_summary_has_no_old_arm_dimension(self):
        row={
            "loss_percent":30,"full_valid_allocation":1,
            "unique_task_completion_percent":100.0,
            "unassigned_task_count":0,"duplicate_task_count":0,
            "preclaim_unique_percent":80.0,"preclaim_duplicate_tasks":10,
            "rounds_executed":2,"reassignment_requests":1,
            "announcement_avoided_requests":1,
            "announced_execution_count":3,
            "announcement_known_task_receipts":9,
            "execution_announce_sends":9,
            "execution_announce_bytes":180,
            "execution_announce_receiver_drops":0,
            "sender_bytes":1000,
            "native_stop_ms":30.0,
            "blocked_robot_count":0,
            "actual_cost_if_valid":5.0,
        }
        for phase in PHASES:
            if phase.startswith("owner_"):
                row[phase+"_bytes"]=20
        summary=summarize_p2n_rows([row])
        self.assertEqual(len(summary),1)
        self.assertEqual(summary[0]["loss_percent"],30)
        self.assertEqual(summary[0]["mean_announcement_sender_bytes"],180)
        self.assertEqual(summary[0]["full_valid_percent"],100)
        self.assertEqual(summary[0]["mean_avoided_known_task_requests"],1)


if __name__=="__main__":
    unittest.main()
