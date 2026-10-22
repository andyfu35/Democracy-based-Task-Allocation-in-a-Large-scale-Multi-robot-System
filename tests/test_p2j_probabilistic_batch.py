"""P2J: stochastic 100-ticket locally visible ballots and dynamic margin selection."""
from __future__ import annotations

from types import SimpleNamespace
import unittest

from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.optimizer import sample_probabilistic_pair_votes
from democracy_mrta.coordination import (
    decode_probabilistic_vote_packet, encode_probabilistic_vote_packet,
    decode_probabilistic_score_packet, encode_probabilistic_score_packet,
    resolve_dynamic_probability_margin_winners,
    validate_probabilistic_batch_scope,
    simulate_democracy_hungarian_retirement,
)
from democracy_mrta.network import (
    BernoulliLossSampler, EmpiricalLatencyProfile, WifiCausalTimingSampler,
    WifiTimingConfig,
)
from experiments.run_p2j_probabilistic_batch import (
    validate_p2j_config, summarize_p2j_cases,
)


def synthetic_profile():
    return EmpiricalLatencyProfile(
        source_repository="test",source_commit="test",source_blob_sha="0"*40,
        location="2",location_label="p2j",config="ax_160mhz_6ghz",
        config_label="synthetic",steady_start_s=0.0,steady_end_s=4.0,
        samples_ms=(3.0,4.0,5.0,6.0),
    )


class P2JProbabilityTests(unittest.TestCase):
    def setUp(self):
        self.costs=(
            (1.0,10.0,12.0),
            (10.0,1.0,10.0),
            (12.0,10.0,1.0),
        )

    def test_sample_has_exactly_100_tickets_and_reproducible_hash(self):
        ballot=sample_probabilistic_pair_votes(
            cost_matrix=self.costs,visible_robot_ids=frozenset((0,1,2)),
            voter_id=0,seed=12,votes_per_voter=100,temperature=5.0,
        )
        same=sample_probabilistic_pair_votes(
            cost_matrix=self.costs,visible_robot_ids=frozenset((0,1,2)),
            voter_id=0,seed=12,votes_per_voter=100,temperature=5.0,
        )
        self.assertEqual(ballot,same)
        self.assertEqual(sum(count for _task,_robot,count in ballot),100)
        self.assertEqual(len({(task,robot) for task,robot,_count in ballot}),len(ballot))
        self.assertTrue(all(0<=task<3 and 0<=robot<3 for task,robot,_count in ballot))

    def test_only_physically_visible_costs_can_receive_votes(self):
        ballot=sample_probabilistic_pair_votes(
            cost_matrix=self.costs,visible_robot_ids=frozenset((0,2)),
            voter_id=0,seed=5,votes_per_voter=100,temperature=9.0,
        )
        self.assertEqual(sum(c for _t,_r,c in ballot),100)
        self.assertTrue(all(robot in (0,2) for _task,robot,_count in ballot))
        with self.assertRaises(ProtocolError) as exc:
            sample_probabilistic_pair_votes(
                cost_matrix=self.costs,visible_robot_ids=frozenset((1,2)),
                voter_id=0,seed=5,votes_per_voter=100,temperature=9.0,
            )
        self.assertEqual(exc.exception.diagnostic.code,"P2J_INVALID_LOCAL_COST_VIEW")

    def test_probability_is_not_deterministic_cheapest_only(self):
        ballot=sample_probabilistic_pair_votes(
            cost_matrix=self.costs,visible_robot_ids=frozenset((0,1,2)),
            voter_id=0,seed=4,votes_per_voter=100,temperature=50.0,
        )
        # Positive chance for a nonminimum candidate, sampled with fixed seed.
        self.assertTrue(any(
            self.costs[robot][task]>min(row[task] for row in self.costs)
            for task,robot,_count in ballot
        ))

    def test_compact_vote_wire_exact_one_batch(self):
        raw=sample_probabilistic_pair_votes(
            cost_matrix=self.costs,visible_robot_ids=frozenset((0,1,2)),
            voter_id=0,seed=9,votes_per_voter=100,temperature=5.0,
        )
        wire=encode_probabilistic_vote_packet(
            round_id=0,sender_id=0,records=raw,votes_per_voter=100,
        )
        self.assertLessEqual(len(wire),416)
        self.assertEqual(
            decode_probabilistic_vote_packet(
                wire,round_id=0,sender_id=0,
                physical_robots=(0,1,2),physical_tasks=(0,1,2),
                votes_per_voter=100,
            ),raw,
        )
        with self.assertRaises(ProtocolError) as exc:
            decode_probabilistic_vote_packet(
                wire,round_id=0,sender_id=1,
                physical_robots=(0,1,2),physical_tasks=(0,1,2),
                votes_per_voter=100,
            )
        self.assertEqual(exc.exception.diagnostic.code,"P2J_INVALID_RECEIVED_VOTE")

    def test_score_transmits_count_and_own_cost(self):
        packet=encode_probabilistic_score_packet(
            round_id=0,sender_id=2,records=((0,60,10.0),(1,40,2.0)),
        )
        self.assertEqual(
            decode_probabilistic_score_packet(
                packet,round_id=0,sender_id=2,physical_tasks=(0,1)
            ),((0,60,10.0),(1,40,2.0)),
        )
        self.assertLessEqual(len(packet),1200)

    def test_later_task_wins_before_earlier_small_margin(self):
        scores={
            (0,0):(60,10.0),(0,1):(40,8.0),
            (1,0):(90,5.0),(1,1):(10,12.0),
        }
        winners,ties=resolve_dynamic_probability_margin_winners(
            scores=scores,physical_tasks=(0,1),physical_robots=(0,1),
            margin_rule="absolute",
        )
        self.assertEqual(winners,((1,0),(0,1)))
        self.assertEqual(ties,0)

    def test_announced_cost_breaks_same_vote_ties(self):
        winners,_=resolve_dynamic_probability_margin_winners(
            scores={(0,0):(10,20.0),(0,1):(10,3.0)},
            physical_tasks=(0,),physical_robots=(0,1),
        )
        self.assertEqual(winners,((1,0),))

    def test_renormalize_after_robot_retirement(self):
        # Task 1 has overwhelming margin and takes robot 0 first, so task 0
        # must RECOMPUTE its own leading candidate using robots 1 and 2.
        scores={
            (0,0):(15,1.0),(0,1):(14,5.0),(0,2):(10,6.0),
            (1,0):(70,1.0),(1,1):(2,3.0),
            (2,2):(30,2.0),
        }
        winners,_=resolve_dynamic_probability_margin_winners(
            scores=scores,physical_tasks=(0,1,2),physical_robots=(0,1,2),
        )
        self.assertEqual(winners,((1,0),(0,1),(2,2)))

    def test_global_matching_repairs_stranded_tasks_using_one_vote_edges(self):
        # The previous irreversible greedy method takes T1/R0 (large
        # margin), then T0/R1, stranding T2 with idle R2. Global
        # optimization chooses T1/R1 (one vote), T0/R2 (one vote),
        # T2/R0 to satisfy every task, without new Vote/Cost traffic.
        scores={
            (0,0):(15,10.0),(0,1):(14,15.0),(0,2):(1,20.0),
            (1,0):(70,5.0),(1,1):(1,11.0),
            (2,0):(5,12.0),
        }
        winners,_=resolve_dynamic_probability_margin_winners(
            scores=scores,physical_tasks=(0,1,2),
            physical_robots=(0,1,2),margin_rule="absolute",
        )
        self.assertEqual(len(winners),3)
        self.assertEqual({t for _r,t in winners},{0,1,2})
        self.assertTrue(all((t,r) in scores for r,t in winners))

    def test_global_matching_enforces_cardinality_before_vote_advantage(self):
        # T0/R0 has overwhelming support; T1 has only R0, so T0/R1
        # (one vote) must be chosen, allowing BOTH tasks to complete.
        scores={
            (0,0):(99,1.0),(0,1):(1,30.0),
            (1,0):(49,3.0),
        }
        winners,_=resolve_dynamic_probability_margin_winners(
            scores=scores,physical_tasks=(0,1),physical_robots=(0,1),
        )
        self.assertEqual(winners,((1,0),(0,1)))

    def test_no_unannounced_edge_is_fabricated_when_score_graph_deficient(self):
        scores={
            (0,0):(50,5.0),(1,0):(40,6.0),(2,0):(30,7.0),
        }
        winners,_=resolve_dynamic_probability_margin_winners(
            scores=scores,physical_tasks=(0,1,2),physical_robots=(0,1,2),
        )
        self.assertEqual(len(winners),1)
        self.assertTrue(all((t,r) in scores for r,t in winners))

    def test_global_matching_keeps_margin_preferences_without_task_id_order(self):
        scores={
            (0,0):(60,10.0),(0,1):(40,8.0),
            (1,0):(90,5.0),(1,1):(10,12.0),
        }
        winners,_=resolve_dynamic_probability_margin_winners(
            scores=scores,physical_tasks=(0,1),physical_robots=(0,1),
            margin_rule="absolute",
        )
        self.assertEqual(winners,((1,0),(0,1)))
        normalized,_=resolve_dynamic_probability_margin_winners(
            scores=scores,physical_tasks=(0,1),physical_robots=(0,1),
            margin_rule="normalized",
        )
        self.assertEqual(normalized,winners)

    def test_reliable_score_reaches_matching_before_original_commit(self):
        sampler=WifiCausalTimingSampler(
            synthetic_profile(),22,WifiTimingConfig(phy_rate_mbps=144.0),
        )
        result=simulate_democracy_hungarian_retirement(
            cost_matrix=self.costs,sampler=sampler,loss_sampler=BernoulliLossSampler(22),
            p_loss=0.0,p_vote_loss=0.0,
            phase_timeout_ms=1000.0,max_rounds=1,
            voting_strategy="probabilistic_batch",
            vote_decision_rule="received_plurality",
            vote_repetitions=1,cost_repetitions=1,
            per_active_round_deadline_ms=(1000.0,1000.0,1000.0),
            enforce_vote_deadline=True,probabilistic_seed=22,
            votes_per_voter=100,temperature=5.0,margin_rule="absolute",
        )
        self.assertEqual(len(result.rounds),1)
        evs=result.rounds[0].coordination.events
        score=[e for e in evs if e.phase=="vote_score_announcement"]
        commits=[e for e in evs if e.phase=="commit"]
        self.assertTrue(score)
        self.assertTrue(commits)
        self.assertEqual(len(commits),len(result.assigned_pairs))
        self.assertTrue(all(
            e.send_time_ms >= max(item.arrival_time_ms for item in score)-1e-9
            for e in commits
        ))
        self.assertFalse(any(
            d.phase=="vote_score_announcement"
            for d in result.rounds[0].coordination.deliveries
        ))
        self.assertEqual(
            sum(e.payload_bytes for e in evs),
            sampler.summarize_network()["application_sender_bytes"],
        )

    def test_one_cost_one_vote_no_retries_at_90_percent_loss(self):
        sampler=WifiCausalTimingSampler(
            synthetic_profile(),17,WifiTimingConfig(phy_rate_mbps=144.0),
        )
        result=simulate_democracy_hungarian_retirement(
            cost_matrix=self.costs,sampler=sampler,loss_sampler=BernoulliLossSampler(17),
            p_loss=0.90,p_vote_loss=0.90,
            phase_timeout_ms=1000.0,max_rounds=1,
            voting_strategy="probabilistic_batch",
            vote_decision_rule="received_plurality",
            vote_repetitions=1,cost_repetitions=1,
            per_active_round_deadline_ms=(1000.0,1000.0,1000.0),
            enforce_vote_deadline=True,probabilistic_seed=17,
            votes_per_voter=100,temperature=5.0,margin_rule="absolute",
        )
        self.assertEqual(len(result.rounds),1)
        self.assertIsInstance(
            result.rounds[0].coordination.plurality_winner_vote_count,int,
        )
        events=result.rounds[0].coordination.events
        self.assertEqual(sum(event.phase=="cost" for event in events),3)
        self.assertEqual(sum(event.phase=="vote" for event in events),3)
        self.assertTrue(all(e.payload_bytes<=416 for e in events if e.phase=="vote"))
        self.assertEqual(len({e.sender_id for e in events if e.phase=="vote"}),3)
        self.assertLessEqual(len(result.assigned_pairs),3)
        self.assertEqual(len({r for r,t in result.assigned_pairs}),len(result.assigned_pairs))
        self.assertEqual(len({t for r,t in result.assigned_pairs}),len(result.assigned_pairs))
        network=sampler.summarize_network()
        self.assertEqual(
            sum(e.payload_bytes for e in events),network["application_sender_bytes"],
        )

    def test_scope_rejects_fresh_redecision_or_cost_retry(self):
        args=dict(voting_strategy="probabilistic_batch",max_rounds=2,
                  cost_repetitions=1,vote_repetitions=1,batch_vote_scope="all",
                  probabilistic_seed=4,votes_per_voter=100,temperature=5.0,
                  margin_rule="absolute",enforce_vote_deadline=True,
                  num_robots=3,num_tasks=3,
                  send_budget=None,preknown_cost_snapshot=None)
        with self.assertRaises(ProtocolError) as exc:
            validate_probabilistic_batch_scope(**args)
        self.assertEqual(exc.exception.diagnostic.code,"P2J_ONE_SHOT_SCOPE_VIOLATION")

    def test_formal_freeze(self):
        args=SimpleNamespace(
            losses="0.00,0.30",seeds=2,first_seed=0,votes_per_voter=100,
            temperature=5.0,margin_rule="absolute",formal=False,
        )
        self.assertEqual(validate_p2j_config(args),(0,30))
        args.formal=True
        with self.assertRaises(ProtocolError) as exc:
            validate_p2j_config(args)
        self.assertEqual(exc.exception.diagnostic.code,"P2J_FORMAL_AXIS_CHANGED")


if __name__=="__main__":
    unittest.main()
