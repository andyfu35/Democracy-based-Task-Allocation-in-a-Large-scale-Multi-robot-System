"""P2K no-PSCR/no-Commit local assignment and on-wire safety regression."""
from __future__ import annotations

from types import SimpleNamespace
import unittest

from democracy_mrta.coordination import (
    encode_p2k_vote_packet,decode_p2k_vote_packet,
    resolve_p2k_local_assignment,simulate_p2k_local_vote_epoch,
)
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import BernoulliLossSampler,EmpiricalLatencySampler
from democracy_mrta.optimizer import sample_p2k_task_balanced_votes
from experiments.run_p2k_consensus_free import (
    validate_p2k_config,analyze_p2k_local_claims,
)
from democracy_mrta.scenario import generate_e0_scenario
from tests.test_p2j_probabilistic_batch import synthetic_profile


class P2KConsensusFreeTests(unittest.TestCase):
    def setUp(self):
        self.costs=((1.0,8.0,9.0),(8.0,1.0,9.0),(9.0,8.0,1.0))

    def test_500_tickets_are_task_balanced_and_local(self):
        for policy in ("cost_softmax","optimized_kbest"):
            ballot=sample_p2k_task_balanced_votes(
                cost_matrix=self.costs,visible_robot_ids=frozenset((0,2)),
                voter_id=0,seed=2,votes_per_voter=600,
                policy=policy,k=5,epsilon=0.1,
            )
            self.assertEqual(len(ballot),600)
            self.assertTrue(all(r in (0,2) for r in ballot))
            self.assertEqual(ballot,sample_p2k_task_balanced_votes(
                cost_matrix=self.costs,visible_robot_ids=frozenset((0,2)),
                voter_id=0,seed=2,votes_per_voter=600,
                policy=policy,k=5,epsilon=0.1,
            ))
            for task in range(3):
                self.assertEqual(len(ballot[task*200:(task+1)*200]),200)

    def test_p2k_wire_roundtrip_and_mtu(self):
        ballot=(0,1,2,1,0)*100
        packet=encode_p2k_vote_packet(round_id=3,sender_id=2,candidates=ballot)
        self.assertEqual(len(packet),516)
        self.assertEqual(decode_p2k_vote_packet(
            packet,round_id=3,sender_id=2,votes_per_voter=500,robots=3,
        ),ballot)
        with self.assertRaises(ProtocolError):
            decode_p2k_vote_packet(
                packet,round_id=4,sender_id=2,votes_per_voter=500,robots=3,
            )
        with self.assertRaises(ProtocolError):
            encode_p2k_vote_packet(
                round_id=0,sender_id=0,candidates=tuple([0]*1185),
            )

    def test_optimization_restricts_capacity_and_cannot_use_zero_vote(self):
        counts=((300,280),(250,200))
        pairs=resolve_p2k_local_assignment(counts=counts)
        self.assertEqual(set(pairs),{(0,1),(1,0)})
        self.assertEqual(resolve_p2k_local_assignment(
            counts=((0,0),(0,10)),
        ),((1,1),))

    def test_receiver_loss_can_create_different_private_views(self):
        profile=synthetic_profile()
        result=simulate_p2k_local_vote_epoch(
            cost_matrix=self.costs,
            sampler=EmpiricalLatencySampler(profile,5),
            loss_sampler=BernoulliLossSampler(5),
            p_loss=0.90,phase_timeout_ms=1000.0,seed=5,
            votes_per_voter=600,policy="optimized_kbest",
        )
        self.assertEqual(len(result.local_assignments),3)
        self.assertEqual(len(result.local_vote_views),3)
        self.assertEqual({e.phase for e in result.events},{"cost","vote"})
        self.assertEqual(len([e for e in result.events if e.phase=="vote"]),3)
        self.assertEqual(len({r for r,t in result.robot_claims}),
                         len(result.robot_claims))
        self.assertGreaterEqual(sum(
            not o.delivered for o in result.deliveries if o.phase=="vote"
        ),1)

    def test_zero_loss_all_receivers_compute_identical_match(self):
        result=simulate_p2k_local_vote_epoch(
            cost_matrix=self.costs,
            sampler=EmpiricalLatencySampler(synthetic_profile(),7),
            loss_sampler=BernoulliLossSampler(7),
            p_loss=0.0,phase_timeout_ms=1000.0,seed=7,
            votes_per_voter=600,policy="optimized_kbest",
        )
        self.assertEqual(len(set(result.local_assignments)),1)
        self.assertEqual(len(result.robot_claims),3)
        self.assertEqual(len({t for r,t in result.robot_claims}),3)
        self.assertEqual(result.local_vote_views[0],result.local_vote_views[1])

    def test_no_global_repair_when_local_claims_collide(self):
        fake=SimpleNamespace(
            robot_claims=((0,0),(1,0)),
            local_assignments=(((0,0),),((1,0),)),
            local_vote_views=(((1,0),(0,1)),((1,0),(0,1))),
        )
        # Two tasks and two robots; an offline observer counts collision
        # and missing task rather than correcting either one.
        scene=SimpleNamespace(
            num_robots=2,num_tasks=2,
            cost_matrix=((1.0,3.0),(2.0,4.0)),
        )
        m=analyze_p2k_local_claims(scene=scene,run=fake)
        self.assertEqual(m["duplicate_task_count"],1)
        self.assertEqual(m["unassigned_task_count"],1)
        self.assertEqual(m["full_valid_allocation"],0)
        self.assertEqual(m["cost_gap_percent_if_valid"],"")

    def test_bad_axis_rejected_without_silent_rounding(self):
        args=SimpleNamespace(
            losses="0.00,0.30",votes="100,200,500,1000",
            robots=100,tasks=100,seeds=2,first_seed=0,k=5,
            epsilon=0.1,temperature=5.0,audit_seeds=1,
        )
        self.assertEqual(validate_p2k_config(args),
                         ((0,30),(100,200,500,1000)))
        args.votes="501"
        with self.assertRaises(ProtocolError):
            validate_p2k_config(args)


if __name__=="__main__":
    unittest.main()
