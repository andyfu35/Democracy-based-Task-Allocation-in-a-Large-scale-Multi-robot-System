import unittest

from democracy_mrta.cbba_multitask import (CBBALocal, release_dependent_suffix,
                                           resolve_cbba_action, run_cbba)
from democracy_mrta.multitask_scenario import generate_multitask_scene
from democracy_mrta.multitask_evaluation import audit_routes
from democracy_mrta.multitask_wire import E9MChannel
from democracy_mrta.network import (EmpiricalLatencyProfile, WifiCausalTimingSampler,
                                     WifiTimingConfig)


def test_profile():
    return EmpiricalLatencyProfile("test", "test", "test", "2", "test", "x", "test",
                                   120.0, 181.0, (1.0, 3.0, 5.0))


def channel(robots=4, seed=0, method="cbba"):
    return E9MChannel(robots=robots, method=method, loss_seed=seed,
                      timing=WifiCausalTimingSampler(test_profile(), seed,
                                                     WifiTimingConfig(phy_rate_mbps=144)))


class TestE9MCBBA(unittest.TestCase):
    def test_original_2009_table_17_actions(self):
        i, k, m, n = 0, 1, 2, 3
        L = [0.0] * 4
        fresh = [0.0, 0.0, 3.0, 3.0]
        stale = [0.0] * 4
        baseline = [0.0] * 4
        cases = [
            (k, i, 1.0, 2.0, stale, baseline, "update"),
            (k, i, 2.0, 1.0, stale, baseline, "leave"),
            (k, k, 2.0, 1.0, stale, baseline, "update"),
            (k, -1, 0.0, 1.0, stale, baseline, "update"),
            (k, m, 2.0, 1.0, baseline, fresh, "update"),
            (i, i, 2.0, 1.0, stale, baseline, "leave"),
            (i, k, 2.0, 1.0, stale, baseline, "reset"),
            (i, m, 2.0, 1.0, baseline, fresh, "reset"),
            (i, -1, 2.0, 1.0, stale, baseline, "leave"),
            (m, i, 1.0, 2.0, baseline, fresh, "update"),
            (m, i, 2.0, 1.0, baseline, fresh, "leave"),
            (m, k, 1.0, 1.0, baseline, fresh, "update"),
            (m, k, 1.0, 1.0, stale, baseline, "reset"),
            (m, m, 1.0, 1.0, baseline, fresh, "update"),
            (m, n, 2.0, 1.0, [0, 0, 4, 0], [0, 0, 1, 2], "reset"),
            (-1, i, 2.0, 0.0, stale, baseline, "leave"),
            (-1, k, 2.0, 0.0, stale, baseline, "update"),
            (-1, m, 2.0, 0.0, baseline, fresh, "update"),
        ]
        for sw, lw, lb, rb, ls, rs, expected in cases:
            with self.subTest(sender_winner=sw, local_winner=lw, expected=expected):
                result = resolve_cbba_action(receiver=i, sender=k,
                                             local_winner=lw, remote_winner=sw,
                                             local_bid=lb, remote_bid=rb,
                                             local_stamps=ls, remote_stamps=rs)
                self.assertEqual(result, expected)

    def test_bundle_suffix_path_separate(self):
        agent = CBBALocal(0, 8, 3)
        agent.bundle = [1, 2, 3, 4]
        agent.path = [3, 2, 1, 4]
        for task in agent.bundle:
            agent.winners[task] = 0
            agent.bids[task] = 20.0
        agent.winners[2] = 1
        self.assertEqual(release_dependent_suffix(agent), 3)
        self.assertEqual(agent.bundle, [1])
        self.assertEqual(agent.path, [1])
        self.assertEqual(agent.winners[2], 1)
        self.assertEqual(agent.winners[3], -1)
        self.assertEqual(agent.winners[4], -1)

    def test_complete_multi_task_cbba_0loss(self):
        for seed in range(2):
            scene = generate_multitask_scene(seed, 4, 8, 2)
            result = run_cbba(scene, channel(4, seed), 0.0, 160)
            audit = audit_routes(scene, result.routes)
            self.assertTrue(audit.feasible, (seed, audit, result.failure_code))
            self.assertTrue(result.observer_agreement)
            self.assertEqual(result.local_certificates, 4)


if __name__ == "__main__":
    unittest.main()
