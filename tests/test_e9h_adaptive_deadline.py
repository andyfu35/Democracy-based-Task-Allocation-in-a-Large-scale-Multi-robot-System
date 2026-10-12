"""E9H original-Greedy deadline/positive-receipt plurality and QA tests."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
from dataclasses import replace
import unittest
from unittest.mock import patch

from democracy_mrta.coordination import (
    build_quarter_plurality_claims, capture_retirement_cost_snapshot,
    validate_e9h_deadline_schedule,
    simulate_democracy_hungarian_retirement,
    transmit_repeated_remote_vote,
)
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler, EmpiricalLatencyProfile,
    estimate_e9h_adaptive_deadline, WifiCausalTimingSampler, WifiTimingConfig,
)
from democracy_mrta.protocol import (
    CandidateVoteAnnouncement, plurality_announcement_threshold,
    resolve_unique_plurality_claims,
)
from democracy_mrta.scenario import generate_e0_scenario
from experiments.run_e9h_adaptive_deadline import (
    parse_e9h_floats, build_e9h_deadline_schedule,
    run_e9h_original_voting_case, iter_e9h_arms,
    pair_e9h_against_fixed, run_e9h_experiment,
    verify_historical_e9g_zip,
)

def fake_profile() -> EmpiricalLatencyProfile:
    return EmpiricalLatencyProfile(
        source_repository="test/synthetic",source_commit="synthetic",
        source_blob_sha="synthetic", location="test",
        location_label="synthetic",config="test",
        config_label="synthetic",steady_start_s=0.0,
        steady_end_s=1.0,samples_ms=(5.0,7.0,9.0),
    )

class AlwaysLateSampler:
    def sample_ms(self,key:str)->float:
        return 80.0

class E9HTrueOwnerContractTests(unittest.TestCase):
    def test_quarter_default_still_requires_greater_than_25pct(self):
        eligible=frozenset(range(8))
        ledger={0:{0,1},1:{2},2:{3}}
        self.assertEqual(plurality_announcement_threshold(8,"quarter_plurality"),3)
        self.assertEqual(plurality_announcement_threshold(8,"received_plurality"),1)
        self.assertEqual(build_quarter_plurality_claims(
            ledgers_by_candidate=ledger,eligible_robots=eligible,
        ),())
        received=build_quarter_plurality_claims(
            ledgers_by_candidate=ledger,eligible_robots=eligible,
            decision_rule="received_plurality",
        )
        self.assertEqual([(x.candidate_id,x.received_votes) for x in received],
                         [(0,2),(1,1),(2,1)])
        win=resolve_unique_plurality_claims(
            announcements=received,eligible_robots=eligible,task_id=0,round_id=0,
            decision_rule="received_plurality",
        )
        self.assertEqual((win.winner_id,win.counted_votes,win.announcement_threshold),
                         (0,2,1))
        self.assertIsNone(resolve_unique_plurality_claims(
            announcements=(),eligible_robots=eligible,task_id=0,round_id=0,
            decision_rule="received_plurality",
        ))

    def test_positive_received_claim_never_accepts_zero_or_duplicate(self):
        for claims in (
            (CandidateVoteAnnouncement(0,0),),
            (CandidateVoteAnnouncement(0,1),CandidateVoteAnnouncement(0,1)),
        ):
            with self.subTest(claims=claims),self.assertRaises(ProtocolError):
                resolve_unique_plurality_claims(
                    announcements=claims,eligible_robots=frozenset({0,1}),
                    task_id=0,round_id=0,decision_rule="received_plurality",
                )

    def test_exact_one_vote_ties_break_lowest_original_id(self):
        claims=(CandidateVoteAnnouncement(3,1),CandidateVoteAnnouncement(1,1))
        winner=resolve_unique_plurality_claims(
            announcements=claims,eligible_robots=frozenset({1,2,3}),
            task_id=0,round_id=9,decision_rule="received_plurality",
        )
        self.assertEqual(winner.winner_id,1)
        self.assertTrue(winner.tied_highest)

    def test_global_absolute_deadline_rejects_real_delivered_rady_ballot(self):
        transmitted,delivered,usable=transmit_repeated_remote_vote(
            voter_id=0,candidate_id=1,task_id=0,round_id=0,
            send_time_ms=0.0,phase_timeout_ms=100.0,
            vote_repetitions=1,sampler=AlwaysLateSampler(),
            loss_sampler=BernoulliLossSampler(seed=0),p_vote_loss=0.0,
            global_vote_deadline_ms=50.0,
        )
        self.assertEqual(len(transmitted),1)
        self.assertTrue(delivered[0].delivered)
        self.assertEqual(delivered[0].arrival_time_ms,80.0)
        self.assertIsNone(usable) # physically arrived but no valid count
        _events,_obs,old_use=transmit_repeated_remote_vote(
            voter_id=0,candidate_id=1,task_id=0,round_id=0,
            send_time_ms=0.0,phase_timeout_ms=100.0,
            vote_repetitions=1,sampler=AlwaysLateSampler(),
            loss_sampler=BernoulliLossSampler(seed=0),p_vote_loss=0.0,
        )
        self.assertIsNotNone(old_use) # legacy behavior unaffected

    def test_formula_numeric_and_active_monotonic(self):
        prof=fake_profile()
        c5,v5=build_e9h_deadline_schedule(
            profile=prof,robots=5,design_rate_mbps=144.0,margin_factor=1,
        )
        c20,v20=build_e9h_deadline_schedule(
            profile=prof,robots=20,design_rate_mbps=144.0,margin_factor=1,
        )
        self.assertGreater(c20.deadline_ms,c5.deadline_ms)
        self.assertGreater(c20.deadline_ms,v20[-1].deadline_ms)
        self.assertLess(v20[0].deadline_ms,v20[-1].deadline_ms)
        self.assertEqual(c5.rady_mean_ms,7.0)
        self.assertEqual(c5.rady_p95_ms,7.0)
        self.assertEqual(c20.application_packet_bytes,16+8*20)
        self.assertEqual(v5[0].application_packet_bytes,32)
        max_m=estimate_e9h_adaptive_deadline(
            profile=prof,active_robots=5,total_tasks=5,
            reference_phy_mbps=144.0,margin_factor=2,phase="vote",
        )
        self.assertEqual(max_m.statistical_margin_ms,0.0)
        validate_e9h_deadline_schedule(
            schedule_ms=tuple(x.deadline_ms for x in v5),
            initial_robots=5,initial_phase_timeout_ms=c5.deadline_ms,
            enforce_vote_deadline=True,
        )

    def test_rady_only_cost_receipts_late_are_paid_but_ineligible(self):
        matrix=((0.5,),(0.7,))
        observed=capture_retirement_cost_snapshot(
            cost_matrix=matrix,sampler=AlwaysLateSampler(),
            loss_sampler=BernoulliLossSampler(seed=3),p_loss=0.0,
            phase_timeout_ms=50.0,enforce_cost_deadline=True,
        )
        self.assertEqual(observed.visible_by_voter,
                         (frozenset({0}),frozenset({1})))
        self.assertEqual(len(observed.events),2)
        self.assertTrue(all(o.delivered for o in observed.deliveries))
        # Legacy old opt-out must still see both rows in Rady-only mode.
        old=capture_retirement_cost_snapshot(
            cost_matrix=matrix,sampler=AlwaysLateSampler(),
            loss_sampler=BernoulliLossSampler(seed=3),p_loss=0.0,
            phase_timeout_ms=50.0,
        )
        self.assertEqual(old.visible_by_voter,
                         (frozenset({0,1}),frozenset({0,1})))

    def test_rady_margin_grid_has_strictly_monotone_predetermined_time(self):
        prof=replace(fake_profile(),samples_ms=tuple(float(i) for i in range(1,11)))
        deadlines=[
            estimate_e9h_adaptive_deadline(
                profile=prof,active_robots=10,total_tasks=10,
                reference_phy_mbps=144.0,margin_factor=k,phase="vote",
            ) for k in (0,1,2)
        ]
        self.assertLess(deadlines[0].deadline_ms,deadlines[1].deadline_ms)
        self.assertLess(deadlines[1].deadline_ms,deadlines[2].deadline_ms)
        self.assertAlmostEqual(deadlines[1].deadline_ms-deadlines[0].deadline_ms,
                               deadlines[1].rady_p95_ms-deadlines[1].rady_mean_ms)

    def test_malformed_deadlines_diagnostic(self):
        for schedule in ((10.0,5.0),(0.0,1.0),(1.0,float("nan"))):
            with self.subTest(schedule=schedule),self.assertRaises(ProtocolError) as err:
                validate_e9h_deadline_schedule(
                    schedule_ms=schedule,initial_robots=2,
                    initial_phase_timeout_ms=10.0,
                    enforce_vote_deadline=True,
                )
            self.assertEqual(err.exception.diagnostic.code,"E9H_INVALID_DEADLINE_SCHEDULE")

    def test_end_to_end_original_voting_avoids_fake_score_and_commit(self):
        profile=fake_profile()
        scenario=generate_e0_scenario(1,5,5)
        schedules={
            1.0:build_e9h_deadline_schedule(
                profile=profile,robots=5,design_rate_mbps=144.0,margin_factor=1.0,
            )
        }
        oracle=1.0
        cases=[
            run_e9h_original_voting_case(
                scenario=scenario,profile=profile,n=5,seed=1,p_loss=0.0,
                rate=144.0,max_rounds=15,
                fixed_timeout_ms=100.0,arm=arm,
                schedules=schedules,oracle_total_cost=oracle,
            ) for arm in iter_e9h_arms((1.0,))
        ]
        self.assertEqual(len(cases),4)
        self.assertEqual([r["decision_rule"] for r in cases],
                         ["quarter_plurality","received_plurality",
                          "quarter_plurality","received_plurality"])
        self.assertTrue(all(r["commit_send_count"]==r["tasks_committed"]
                            for r in cases))
        self.assertTrue(all(r["total_sender_application_bytes"]>0
                            and r["total_airtime_ms"]>0 for r in cases))
        pair_e9h_against_fixed(cases)
        self.assertTrue(all(r["paired_time_delta_ms"]!="" for r in cases))

    def test_immutable_smoke_grid_with_source_hashes(self):
        profile=fake_profile()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"e9h"
            with (
                patch("experiments.run_e9h_adaptive_deadline.ensure_rady_dataset",
                      return_value=Path(tmp)/"synthetic.json"),
                patch("experiments.run_e9h_adaptive_deadline.load_rady_latency_profile",
                      return_value=profile),
                patch("experiments.run_e9h_adaptive_deadline.subprocess.check_output",
                      return_value="c"*40),
            ):
                rows=run_e9h_experiment(
                    sizes=(3,5),rates=(144.0,),losses=(0.0,),
                    margins=(1.0,),seeds=2,first_seed=0,
                    max_rounds=15,dataset=Path(tmp)/"synthetic.json",
                    output_root=root,design_rate_mbps=144.0,
                    allow_download=False,
                )
            self.assertEqual(len(rows),2*2*1*2*4)
            m=json.loads((root/"manifest.json").read_text())
            self.assertEqual(m["source_git_sha"],"c"*40)
            self.assertTrue(m["no_actual_ns3_edca_ofdma_wifi_client_calibration"])
            for f,digest in m["original_csv_sha256"].items():
                self.assertEqual(hashlib.sha256((root/f).read_bytes()).hexdigest(),digest)
            self.assertFalse((root/"per_seed_e9h.partial.csv").exists())
            with (root/"per_seed_e9h.csv").open() as fh:
                self.assertEqual(len(list(csv.DictReader(fh))),32)
            with self.assertRaises(ProtocolError) as err:
                run_e9h_experiment(
                    sizes=(3,5),rates=(144.0,),losses=(0.0,),
                    margins=(1.0,),seeds=2,first_seed=0,
                    max_rounds=15,dataset=Path(tmp)/"synthetic.json",
                    output_root=root,design_rate_mbps=144.0,
                    allow_download=False,
                )
            self.assertEqual(err.exception.diagnostic.code,"E9H_OUTPUT_EXISTS")

    def test_invalid_history_is_first_source_contract_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/"invalid.zip"
            file.write_bytes(b"not a zip")
            with self.assertRaises(ProtocolError) as err:
                verify_historical_e9g_zip(file)
            self.assertEqual(err.exception.diagnostic.code,"E9H_UNVERIFIED_HISTORICAL_SOURCE")

    def test_parse_valid_margin_and_loss_grid(self):
        self.assertEqual(parse_e9h_floats("0,0.3",is_loss=True),(0.0,0.3))
        self.assertEqual(parse_e9h_floats("0,1,2",is_loss=False),(0.0,1.0,2.0))
        for raw in ("", "nan", "1,1", "-0.1", "1,0"):
            with self.subTest(raw=raw),self.assertRaises(ProtocolError):
                parse_e9h_floats(raw,is_loss=False)


if __name__=="__main__":
    unittest.main()
