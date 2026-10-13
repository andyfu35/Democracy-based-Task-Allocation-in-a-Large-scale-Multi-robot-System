import unittest
from democracy_mrta.multitask_scenario import generate_multitask_scene, best_insertion
from democracy_mrta.multitask_evaluation import audit_routes
from democracy_mrta.voting_multitask import run_voting_multitask, choose_plurality
from test_e9m_cbba import channel


class TestE9MVoting(unittest.TestCase):
    def test_plurailty_and_insertion(self):
        self.assertEqual(choose_plurality({0: 2, 1: 3, 2: 3}), 1)
        scene = generate_multitask_scene(0, 4, 8, 2)
        marginal, index = best_insertion(scene, 0, [], 3)
        self.assertGreater(marginal, 0)
        self.assertEqual(index, 0)

    def test_zero_and_loss30_feasible(self):
        for loss in (0.0, 0.30):
            scene = generate_multitask_scene(0, 4, 8, 2)
            result = run_voting_multitask(scene, channel(4, 5, "voting_multitask"), loss)
            audit = audit_routes(scene, result.routes)
            self.assertTrue(audit.feasible)
            self.assertEqual(result.local_certificates, scene.robots)
            self.assertEqual(result.rounds, scene.tasks)
            self.assertTrue(result.ledger["voting_commit"]["sender_bytes"] > 0)


if __name__ == "__main__":
    unittest.main()
