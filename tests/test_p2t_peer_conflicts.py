"""Focused P2T peer-vs-owner-free semantics and physical observation tests."""
from types import SimpleNamespace
import unittest

from democracy_mrta.claim_resolution import (
    P2LClaim, P2TIntent, choose_p2t_peer_winners,
    coordinate_p2t_peer_conflicts, encode_p2t_peer_intent,
    decode_p2t_peer_intent, encode_p2t_execution_notice,
    decode_p2t_execution_notice,
)
from democracy_mrta.diagnostics import ProtocolError

COSTS=((1.,50.,99.),(2.,49.,98.),(80.,81.,1.))


class FakeSampler:
    def sample_ms(self, key):
        return 1.0


class Loss:
    def __init__(self, blind_to_robot_one=False):
        self.blind = blind_to_robot_one

    def is_delivered(self, key, p_loss):
        if (self.blind and "broadcast|p2t_intent|1|0|round=1" in key):
            return False
        return True


def native_run(claims, conflict=False):
    rows=[[0]*3 for _ in range(3)]
    if conflict:
        rows[0][0]=10
        rows[1][0]=20
        rows[2][1]=30
        rows[2][2]=30
    else:
        rows[0][0]=30
        rows[1][1]=30
        rows[2][2]=30
    view=tuple(tuple(row) for row in rows)
    return SimpleNamespace(
        robot_claims=claims,
        local_vote_views=(view,view,view),
        local_assignments=((),(),()),
        cost_visible_rows=(frozenset(range(3)),)*3,
        decision_time_ms=0.0,
        events=(),
    )


class P2TPeerConflictTests(unittest.TestCase):
    def execute(self, run, blind=False):
        return coordinate_p2t_peer_conflicts(
            run=run,cost_matrix=COSTS,votes_per_voter=30,
            sampler=FakeSampler(),loss_sampler=Loss(blind),
            p_loss=0.30 if blind else 0.0,
            max_rounds=5,intent_repetitions=3,
            announcement_repetitions=3,
        )

    def test_zero_loss_one_round_no_owner_exact_matching(self):
        run=native_run(((0,0),(1,1),(2,2)))
        result=self.execute(run)
        self.assertEqual(set(result.attempted_pairs),
                         {(0,0),(1,1),(2,2)})
        self.assertEqual(result.rounds_executed,1)
        self.assertEqual(result.unique_task_count,3)
        self.assertEqual(result.duplicate_task_count,0)
        self.assertIsNone(result.first_diagnostic)
        self.assertEqual({event.phase for event in result.events},
                         {"p2t_intent","p2t_execution"})
        self.assertEqual(sum(e.phase=="p2t_intent" for e in result.events),9)
        self.assertEqual(sum(e.phase=="p2t_execution" for e in result.events),9)
        self.assertEqual(set(e.payload_bytes for e in result.events),{16,36})

    def test_conflicting_peers_see_each_other_and_loser_retargets(self):
        run=native_run(((0,0),(1,0),(2,2)),conflict=True)
        result=self.execute(run)
        self.assertEqual(set(result.attempted_pairs),
                         {(0,1),(1,0),(2,2)})
        self.assertEqual(result.rounds_executed,2)
        self.assertGreaterEqual(result.yielded_candidates,1)
        self.assertIsNone(result.first_diagnostic)

    def test_hidden_peer_conflict_is_exposed_not_oracle_corrected(self):
        run=native_run(((0,0),(1,0),(2,2)),conflict=True)
        result=self.execute(run,blind=True)
        self.assertIn((0,0),result.attempted_pairs)
        self.assertIn((1,0),result.attempted_pairs)
        self.assertEqual(result.duplicate_task_count,1)
        self.assertEqual(result.first_diagnostic.category,"safety")
        self.assertEqual(result.first_diagnostic.code,
                         "P2T_UNOBSERVED_PEER_COLLISION")

    def test_tie_breaks_on_announced_own_cost_not_hidden_cost(self):
        a=P2TIntent(P2LClaim(0,0,0,10,2,10),own_cost=5.)
        b=P2TIntent(P2LClaim(0,1,0,10,2,10),own_cost=2.)
        view={0:{0:a,1:b},1:{1:b,0:a}}
        wins,losses,conflicts=choose_p2t_peer_winners(
            intents=(a,b),locally_received=view,
        )
        self.assertEqual([i.claim.robot_id for i in wins],[1])
        self.assertEqual([i.claim.robot_id for i in losses],[0])
        self.assertEqual(conflicts,2)

    def test_p2t_packets_reject_mismatched_wire_identity(self):
        a=P2TIntent(P2LClaim(0,1,0,10,2,10),own_cost=5.)
        packet=encode_p2t_peer_intent(a)
        self.assertEqual(len(packet),36)
        decoded=decode_p2t_peer_intent(
            packet,sender_id=1,claim_round=0,robots=3,tasks=3,
            tickets_per_task=10,
        )
        self.assertEqual(decoded,a)
        with self.assertRaises(ProtocolError):
            decode_p2t_peer_intent(
                packet,sender_id=0,claim_round=0,robots=3,tasks=3,
                tickets_per_task=10,
            )
        notice=encode_p2t_execution_notice(
            claim_round=0,robot_id=1,task_id=2,
        )
        self.assertEqual(len(notice),16)
        with self.assertRaises(ProtocolError):
            decode_p2t_execution_notice(
                notice,sender_id=0,claim_round=0,robots=3,tasks=3,
            )


if __name__=="__main__":
    unittest.main()
