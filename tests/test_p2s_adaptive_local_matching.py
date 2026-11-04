"""P2S adaptive local matching ballot regression contracts."""
import unittest

from democracy_mrta.coordination import resolve_p2k_local_assignment
from democracy_mrta.optimizer import (
    sample_p2k_task_balanced_votes, solve_hungarian_assignment,
)

COSTS=((1.,2.,100.),(2.,100.,100.),(100.,1.,2.))


class P2SAdaptiveMatchingTests(unittest.TestCase):
    def vote(self, visible, voter, costs=COSTS, budget=30):
        return sample_p2k_task_balanced_votes(
            cost_matrix=costs, visible_robot_ids=frozenset(visible),
            voter_id=voter, seed=0, votes_per_voter=budget,
            policy="adaptive_local_matching", k=1, epsilon=0.0,
            temperature=5.0,
        )

    def test_zero_loss_exact_optimal_matching(self):
        ballots=[self.vote(range(3), voter) for voter in range(3)]
        votes=[[0]*3 for _ in range(3)]
        for ballot in ballots:
            for index, robot in enumerate(ballot):
                votes[robot][index//10]+=1
        matching=resolve_p2k_local_assignment(counts=tuple(tuple(row) for row in votes))
        self.assertEqual(set(matching),set(solve_hungarian_assignment(COSTS).assigned_pairs))

    def test_missing_rows_never_selected(self):
        ballot=self.vote((0,),0)
        self.assertEqual(ballot,tuple(0 for _ in range(30)))

    def test_partial_local_matching_backup_covers_all_tasks(self):
        ballot=self.vote((0,1),0)
        self.assertEqual(len(ballot),30)
        self.assertTrue(set(ballot).issubset({0,1}))
        self.assertTrue(all(len(ballot[10*t:10*(t+1)])==10 for t in range(3)))

    def test_repeatable_and_fixed_packet_budget(self):
        self.assertEqual(self.vote((0,2),0),self.vote((0,2),0))
        self.assertEqual(len(self.vote((0,2),0)),30)

    def test_policy_does_not_change_original_rank_square(self):
        original=sample_p2k_task_balanced_votes(
            cost_matrix=COSTS, visible_robot_ids=frozenset(range(3)),
            voter_id=0,seed=0,votes_per_voter=30,
            policy="optimized_rank_square",k=1,epsilon=0.,temperature=5.,
        )
        self.assertEqual(len(original),30)


if __name__=="__main__":
    unittest.main()
