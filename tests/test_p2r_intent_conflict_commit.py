"""P2R: only physically observed INTENT, challenge, COMMIT, DENY, P2NX."""
from __future__ import annotations

from dataclasses import replace
import unittest

from democracy_mrta.claim_resolution import (
    coordinate_p2r_announced_intents,
    decode_p2r_owner_response,
    encode_p2r_owner_response,
)
from democracy_mrta.coordination import P2KLocalVoteResult
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler,EmpiricalLatencyProfile,
    WifiCausalTimingSampler,WifiTimingConfig,
)
from experiments.run_p2r_intent_conflict_commit import (
    FIELDS,PHASES,parse_args,validate_p2r_axes,
    summarize_p2r_rows,
)


def profile():
    return EmpiricalLatencyProfile(
        source_repository="test",source_commit="test",
        source_blob_sha="0"*40,location="2",location_label="p2r",
        config="ax_160mhz_6ghz",config_label="synthetic",
        steady_start_s=0.0,steady_end_s=4.0,
        samples_ms=(3.0,4.0,5.0,6.0),
    )


def fixture(claims):
    base=((100,60,40),(100,60,40),(100,60,40))
    views=(
        ((30,150,20),base[1],base[2]),
        (base[0],(60,80,60),base[2]),
        (base[0],base[1],(30,40,130)),
    )
    initial=((0,0),(1,1),(2,2))
    return P2KLocalVoteResult(
        local_assignments=(initial,initial,initial),
        robot_claims=claims,
        local_vote_views=views,
        cost_visible_rows=(frozenset(range(3)),)*3,
        events=(),deliveries=(),decision_time_ms=10.0,
        cost_completion_ms=5.0,
    )


class LosePackets:
    def __init__(self, blocked_substring):
        self.blocked_substring=blocked_substring

    def is_delivered(self,key,p_loss):
        return self.blocked_substring not in key


class P2RIntentConflictTests(unittest.TestCase):
    def setUp(self):
        self.costs=((2.,1.,9.),(1.,2.,8.),(9.,8.,1.))
        self.run_routed=fixture(((0,1),(1,2),(2,0)))
        self.run_conflict=fixture(((0,1),(1,0),(2,1)))

    def execute(self, run, *, loss_sampler=None, attempts=3, rounds=7):
        sampler=WifiCausalTimingSampler(
            profile(),17,WifiTimingConfig(phy_rate_mbps=144.0),
        )
        outcome=coordinate_p2r_announced_intents(
            run=run,cost_matrix=self.costs,
            votes_per_voter=600,sampler=sampler,
            loss_sampler=loss_sampler or BernoulliLossSampler(17),
            p_loss=0.,max_rounds=rounds,
            intent_repetitions=attempts,
            decision_repetitions=attempts,
            announcement_repetitions=3,
        )
        return outcome,sampler

    def test_no_conflict_only_three_intent_and_commit_copies(self):
        result, sampler=self.execute(self.run_routed)
        self.assertEqual(
            set(result.executed_pairs),
            {(0,1),(1,2),(2,0)},
        )
        self.assertEqual(result.rounds_executed,1)
        self.assertEqual(result.owner_observed_conflicts,0)
        self.assertEqual(result.peer_observed_challenges,0)
        counts={phase:sum(e.phase==phase for e in result.events)
                for phase in PHASES}
        self.assertEqual(counts["p2r_intent"],9)
        self.assertEqual(counts["p2r_commit"],9)
        self.assertEqual(counts["p2r_deny"],0)
        self.assertEqual(counts["p2r_challenge"],0)
        self.assertEqual(counts["execution_announce"],9)
        physical=sampler.summarize_network()
        self.assertEqual(
            physical["application_sender_bytes"],result.sender_bytes,
        )
        self.assertEqual(physical["packet_count"],len(result.events))
        self.assertLess(result.finish_ms,2000)

    def test_only_conflicting_intents_trigger_challenges_and_denies(self):
        result,_=self.execute(self.run_conflict)
        self.assertEqual(len(result.executed_pairs),3)
        self.assertEqual(len({t for _,t in result.executed_pairs}),3)
        self.assertEqual(len({r for r,_ in result.executed_pairs}),3)
        self.assertGreaterEqual(result.rounds_executed,2)
        self.assertGreaterEqual(result.owner_observed_conflicts,1)
        self.assertGreater(result.peer_observed_challenges,0)
        self.assertGreater(result.denial_receipts,0)
        self.assertGreater(
            sum(e.phase=="p2r_deny" for e in result.events),0,
        )
        self.assertEqual(set(result.executed_pairs),
                         {(0,1),(1,0),(2,2)})

    def test_silence_is_not_permission_and_no_owner_received_intent(self):
        result,_=self.execute(
            self.run_routed,
            loss_sampler=LosePackets("broadcast|p2r_intent|"),
            rounds=3,
        )
        self.assertEqual(result.executed_pairs,())
        self.assertEqual(result.reserved_pairs,())
        self.assertIsNotNone(result.first_diagnostic)
        self.assertEqual(
            result.first_diagnostic.code,"P2R_INCOMPLETE_AFTER_ROUNDS",
        )
        self.assertFalse(any(
            e.phase=="execution_announce" for e in result.events
        ))

    def test_lost_commit_keeps_reservation_but_never_executes(self):
        # R1's T2 owner is R2. Its P2RC is lost on EVERY attempt.
        result,_=self.execute(
            self.run_routed,
            loss_sampler=LosePackets("unicast|p2r_commit|2|1|"),
            rounds=3,
        )
        self.assertIn((1,2),result.reserved_pairs)
        self.assertNotIn((1,2),result.executed_pairs)
        self.assertEqual(result.first_diagnostic.code,
                         "P2R_COMMIT_NOT_DELIVERED")
        self.assertEqual(
            sum(e.phase=="execution_announce" for e in result.events),
            3*len(result.executed_pairs),
        )
        self.assertEqual(len({t for _,t in result.executed_pairs}),
                         len(result.executed_pairs))

    def test_actual_peer_conflict_challenge_defers_unknown_contender(self):
        # R0 and R2 both intend task T1, whose owner is R1.
        # R2's first round INTENT drops ONLY at R1; R0 hears it and
        # emits an actual P2RH to R1, asking to collect again.
        run=fixture(((0,1),(1,0),(2,1)))
        loss_sampler=LosePackets(
            "broadcast|p2r_intent|2|1|1|round=1",
        )
        result,_=self.execute(run,loss_sampler=loss_sampler,rounds=7)
        self.assertGreaterEqual(result.challenge_deferrals,1)
        self.assertTrue(any(
            d.get("status")=="DEFER_CHALLENGE"
            for d in result.decisions
        ))
        self.assertTrue(any(e.phase=="p2r_challenge"
                            for e in result.events))
        self.assertEqual(len(result.executed_pairs),3)
        self.assertEqual(len({t for _,t in result.executed_pairs}),3)

    def test_no_phantom_notice_and_every_real_commit_is_irreversible(self):
        result,_=self.execute(
            self.run_routed,
            loss_sampler=LosePackets(
                "broadcast|execution_announce|",
            ),
        )
        for robot,known in enumerate(
                result.recipient_seen_executing_tasks):
            expected={task for r,task in result.executed_pairs if r==robot}
            self.assertEqual(set(known),expected)
        self.assertEqual(len(result.reserved_pairs),
                         len(result.executed_pairs))

    def test_wrong_owner_and_wrong_tag_cannot_authorize(self):
        wire=encode_p2r_owner_response(
            round_id=0,owner_id=1,robot_id=0,
            task_id=1,commit=True,
        )
        self.assertEqual(len(wire),20)
        with self.assertRaises(ProtocolError) as exc:
            decode_p2r_owner_response(
                wire,sender_id=2,robot_id=0,task_id=1,
                claim_round=0,robots=3,
            )
        self.assertEqual(exc.exception.diagnostic.code,
                         "P2R_NOT_FIXED_OWNER")
        with self.assertRaises(ProtocolError) as exc:
            decode_p2r_owner_response(
                b"P2MD"+wire[4:],sender_id=1,robot_id=0,
                task_id=1,claim_round=0,robots=3,
            )
        self.assertEqual(exc.exception.diagnostic.code,
                         "P2R_INVALID_RESPONSE_TAG")

    def test_new_only_axis_and_failed_cost_is_blank(self):
        args=parse_args(["--output-root","results/_p2r_test"])
        self.assertEqual(validate_p2r_axes(args),(0,30,50,90))
        self.assertEqual(args.intent_repetitions,3)
        self.assertIn("p2r_challenge_bytes",FIELDS)
        args.intent_repetitions=0
        with self.assertRaises(ProtocolError) as exc:
            validate_p2r_axes(args)
        self.assertEqual(exc.exception.diagnostic.code,
                         "P2R_INVALID_STUDY_AXIS")
        row={
            "loss_percent":30,"full_valid_allocation":0,
            "unique_completion_percent":90.0,"unassigned_task_count":10,
            "duplicate_task_count":0,"reserved_count":100,
            "initial_duplicate_tasks":8,"rounds_executed":5,
            "owner_observed_conflicts":8,"p2r_challenge_sends":3,
            "challenge_deferrals":1,"denial_receipts":8,
            "retargeted_intents":6,"p2r_intent_bytes":10000,
            "p2r_commit_bytes":2000,"p2r_deny_bytes":100,
            "sender_bytes":198000,"native_stop_ms":5000,
        }
        summary=summarize_p2r_rows([row])
        self.assertEqual(summary[0]["valid_cost_samples"],0)
        self.assertEqual(summary[0]["mean_valid_actual_cost"],"")


if __name__=="__main__":
    unittest.main()
