"""P2O only: causal parallel owner transport and honest lossy ACK chronology."""
from __future__ import annotations

from dataclasses import replace
import unittest

from democracy_mrta.claim_resolution import (
    coordinate_p2m_task_owners,
    validate_p2o_timing_scope,
)
from democracy_mrta.coordination import P2KLocalVoteResult
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler, EmpiricalLatencyProfile, WifiCausalTimingSampler,
    WifiTimingConfig,
)
from experiments.run_p2o_causal_owner_timing import (
    FIELDS, PHASES, parse_args, validate_p2o_axes, summarize_p2o_rows,
)


def profile():
    return EmpiricalLatencyProfile(
        source_repository="test", source_commit="test",
        source_blob_sha="0"*40, location="2", location_label="p2o",
        config="ax_160mhz_6ghz", config_label="synthetic",
        steady_start_s=0.0, steady_end_s=4.0,
        samples_ms=(3.0,4.0,5.0,6.0),
    )


def fixture():
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
        events=(), deliveries=(), decision_time_ms=10.0,
        cost_completion_ms=5.0,
    )


class DropPhase:
    def __init__(self, substring):
        self.substring=substring

    def is_delivered(self,key,p_loss):
        return self.substring not in key


class P2OCausalOwnerTimingTests(unittest.TestCase):
    def setUp(self):
        self.costs=((1.0,3.0,9.0),(2.0,8.0,9.0),(8.0,9.0,1.0))

    def run_owner(self, *, source=None, loss_sampler=None, repeats=3,
                  attempts=4, timeout=100.0):
        return coordinate_p2m_task_owners(
            run=source or fixture(),
            cost_matrix=self.costs,
            votes_per_voter=600,
            sampler=WifiCausalTimingSampler(
                profile(),17,WifiTimingConfig(phy_rate_mbps=144.0),
            ),
            loss_sampler=loss_sampler or BernoulliLossSampler(17),
            p_loss=0.0,max_attempts=attempts,max_rounds=10,
            execution_announce_repetitions=repeats,
            timing_mode="causal",retry_timeout_ms=timeout,
        )

    def test_one_radio_many_candidates_start_request_concurrently(self):
        source=replace(
            fixture(),robot_claims=((0,1),(1,2),(2,0)),
        )
        result=self.run_owner(source=source)
        initial=[e for e in result.events
                 if e.phase=="owner_request" and e.round_id==1
                 and e.transmission_index==0]
        self.assertEqual(len(initial),3)
        self.assertEqual(len({e.send_time_ms for e in initial}),1)
        self.assertEqual(set(result.executed_pairs),
                         {(0,1),(1,2),(2,0)})
        self.assertEqual(result.rounds_executed,1)
        self.assertEqual(result.timing_mode,"causal")
        self.assertEqual(len(result.announced_executions),3)
        self.assertTrue(all(
            e.send_time_ms<=later.send_time_ms
            for e,later in zip(result.events,result.events[1:])
        ))
        self.assertEqual(
            sum(e.phase=="execution_announce" for e in result.events),9)
        self.assertEqual(
            len({task for _,task in result.executed_pairs}),3)
        self.assertLess(result.last_first_grant_arrival_ms,
                        result.finish_ms)

    def test_first_physical_grant_immediately_triggers_announcements(self):
        # R1's owner GRANT is delivered on the first attempt, but ALL
        # return ACKs are lost. The owner still sends later duplicate
        # GRANTs while the executor already sent its three P2NX copies.
        result=self.run_owner(
            loss_sampler=DropPhase("|owner_decision_ack|"),
            attempts=4,timeout=100,
        )
        self.assertEqual(set(result.executed_pairs),
                         {(0,1),(1,0),(2,2)})
        self.assertEqual(set(result.announced_executions),
                         set(result.executed_pairs))
        self.assertEqual(len([e for e in result.events
                              if e.phase=="execution_announce"]),9)
        first_grant=min(e.arrival_time_ms for e in result.events
                        if e.phase=="owner_decision" and e.receiver_id==1)
        first_announce=min(e.send_time_ms for e in result.events
                           if e.phase=="execution_announce"
                           and e.sender_id==1)
        self.assertAlmostEqual(first_announce,first_grant)
        later_duplicates=[e for e in result.events
                          if e.phase=="owner_decision"
                          and e.receiver_id==1 and e.transmission_index>0]
        self.assertTrue(later_duplicates)
        self.assertTrue(all(e.send_time_ms>first_announce
                            for e in later_duplicates))
        self.assertLess(result.last_first_grant_arrival_ms,
                        result.finish_ms)

    def test_no_grant_no_executing_even_if_owner_reserved(self):
        result=self.run_owner(
            loss_sampler=DropPhase("|owner_decision|"),
            attempts=2,timeout=100,
        )
        self.assertIn((1,0),result.reserved_pairs)
        self.assertNotIn((1,0),result.executed_pairs)
        self.assertNotIn((1,0),result.announced_executions)
        self.assertEqual(set(result.announced_executions),
                         set(result.executed_pairs))
        self.assertEqual(
            len({task for _,task in result.executed_pairs}),
            len(result.executed_pairs),
        )
        self.assertEqual(
            result.first_diagnostic.code,
            "P2O_OWNER_DECISION_NOT_DELIVERED",
        )

    def test_no_announcement_receipt_no_hidden_occupancy(self):
        result=self.run_owner(
            loss_sampler=DropPhase("broadcast|execution_announce|"),
        )
        self.assertEqual(result.avoided_announced_requests,0)
        for robot,known in enumerate(result.recipient_seen_executing_tasks):
            self.assertEqual(set(known),{
                task for sender,task in result.announced_executions
                if sender==robot
            })

    def test_owner_only_receives_physical_claim_with_ack_lost(self):
        result=self.run_owner(
            loss_sampler=DropPhase("|owner_request_ack|"),
            attempts=2,timeout=100,
        )
        self.assertEqual(set(result.executed_pairs),
                         {(0,1),(1,0),(2,2)})
        self.assertGreaterEqual(result.request_receipt_ack_timeouts,1)
        self.assertIsNone(result.first_diagnostic)

    def test_real_shared_radio_ledger_charges_every_send(self):
        source=replace(
            fixture(),robot_claims=((0,1),(1,2),(2,0)),
        )
        sampler=WifiCausalTimingSampler(
            profile(),19,WifiTimingConfig(phy_rate_mbps=144.0),
        )
        result=coordinate_p2m_task_owners(
            run=source,cost_matrix=self.costs,votes_per_voter=600,
            sampler=sampler,loss_sampler=DropPhase("|owner_request_ack|"),
            p_loss=0.30,max_attempts=2,max_rounds=10,
            execution_announce_repetitions=3,
            timing_mode="causal",retry_timeout_ms=100.0,
        )
        ledger=sampler.summarize_network()
        self.assertEqual(ledger["packet_count"],len(result.events))
        self.assertEqual(ledger["application_sender_bytes"],
                         result.sender_bytes)
        self.assertEqual(len({task for _,task in result.executed_pairs}),
                         len(result.executed_pairs))
        self.assertTrue(all(
            e.send_time_ms<=n.send_time_ms
            for e,n in zip(result.events,result.events[1:])
        ))
        self.assertEqual(
            sum(e.phase=="execution_announce" for e in result.events),
            len(result.executed_pairs)*3,
        )
        self.assertGreaterEqual(result.request_receipt_ack_timeouts,1)

    def test_retry_timeout_has_named_diagnostic(self):
        for value in (float("nan"),float("inf"),-1.0,0.0):
            with self.subTest(value=value):
                with self.assertRaises(ProtocolError) as exc:
                    validate_p2o_timing_scope(
                        retry_timeout_ms=value,plans=(),
                        phase="request",robots=3,max_attempts=24,
                        start_ms=10.0,
                    )
                self.assertEqual(
                    exc.exception.diagnostic.code,
                    "P2O_INVALID_TEMPORAL_SCOPE",
                )

    def test_only_p2o_axes_and_report_schema(self):
        args=parse_args(["--output-root","results/_p2o_test"])
        self.assertEqual(validate_p2o_axes(args),(0,30,50,90))
        self.assertEqual(args.retry_timeout_ms,100.0)
        self.assertEqual(args.announcement_repetitions,3)
        self.assertIn("request_window_total_ms",FIELDS)
        self.assertIn("last_first_grant_arrival_ms",FIELDS)
        self.assertEqual(PHASES[-1],"execution_announce")
        args.retry_timeout_ms=-5.0
        with self.assertRaises(ProtocolError):
            validate_p2o_axes(args)

    def test_new_method_summary_includes_actual_phase_times(self):
        record={
            "loss_percent":30,"full_valid_allocation":1,
            "unique_task_completion_percent":100.,
            "unassigned_task_count":0,"duplicate_task_count":0,
            "preclaim_unique_percent":80.,"preclaim_duplicate_tasks":1,
            "rounds_executed":2,"reassignment_requests":1,
            "announcement_avoided_requests":1,
            "announced_execution_count":3,
            "announcement_known_task_receipts":9,
            "execution_announce_sends":9,
            "execution_announce_bytes":180,
            "execution_announce_receiver_drops":0,
            "sender_bytes":1000,"native_stop_ms":100.0,
            "blocked_robot_count":0,"actual_cost_if_valid":5.0,
            "request_window_total_ms":20.,
            "decision_window_total_ms":30.,
            "timeout_wait_total_ms":0.,
            "last_first_grant_arrival_ms":60.,
            "owner_protocol_finish_ms":100.,
        }
        for phase in PHASES:
            if phase.startswith("owner_"):
                record[phase+"_bytes"]=20
        summary=summarize_p2o_rows([record])
        self.assertEqual(summary[0]["full_valid_percent"],100.)
        self.assertEqual(summary[0]["mean_request_window_ms"],20.)
        self.assertEqual(summary[0]["mean_last_first_grant_ms"],60.)


if __name__=="__main__":
    unittest.main()
