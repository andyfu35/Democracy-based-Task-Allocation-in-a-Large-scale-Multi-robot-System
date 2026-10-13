"""Native protocol observational invariance: callback must not change SEND/decisions."""
import unittest

from democracy_mrta.network import (
    BernoulliLossSampler, EmpiricalLatencyProfile,
    WifiCausalTimingSampler, WifiTimingConfig,
)
from democracy_mrta.scenario import generate_e0_scenario
from democracy_mrta.optimizer import solve_hungarian_assignment
from experiments.run_e9h_adaptive_deadline import (
    build_e9h_deadline_schedule, run_e9h_original_voting_case,
    DEFAULT_OLD_FIXED_MS,
)
from experiments.run_e9i_cost30_scaling import selected_e9i_arms
from democracy_mrta.multitask_scenario import generate_multitask_scene
from democracy_mrta.multitask_wire import E9MChannel
from democracy_mrta.cbaa import simulate_cbaa
from democracy_mrta.price_auction import simulate_price_auction
from democracy_mrta.cbba_multitask import run_cbba
from democracy_mrta.voting_multitask import run_voting_multitask
from experiments.p1_feasibility import FirstFeasibleObserver


def profile():
    return EmpiricalLatencyProfile('test','test','test','2','test','x','test',
                                  120.,181.,(1.,3.,5.))


def sampler(seed):
    return WifiCausalTimingSampler(profile(),seed,
                                   WifiTimingConfig(phy_rate_mbps=144.))


def channel(method,seed):
    return E9MChannel(robots=4,method=method,loss_seed=seed,
                      timing=sampler(seed))


class TestP1NativeObservers(unittest.TestCase):
    def test_cbba_optional_observer_never_alters_native_result(self):
        scene=generate_multitask_scene(0,4,4,1)
        pure=run_cbba(scene,channel('cbba',5),0.,160)
        obs=FirstFeasibleObserver(4)
        observed=run_cbba(scene,channel('cbba',5),0.,160,
                          external_observer=obs.observe)
        self.assertEqual(pure.routes,observed.routes)
        self.assertEqual(pure.ledger,observed.ledger)
        self.assertEqual(pure.rounds,observed.rounds)
        self.assertEqual(pure.elapsed_ms,observed.elapsed_ms)
        self.assertGreater(obs.observed_phases,0)
        self.assertIsNotNone(obs.first_feasible_ms)
        self.assertLessEqual(obs.first_feasible_ms,observed.elapsed_ms)

    def test_multitask_voting_callback_does_not_change_paid_commits(self):
        scene=generate_multitask_scene(0,4,4,1)
        pure=run_voting_multitask(scene,channel('voting_multitask',5),0.)
        obs=FirstFeasibleObserver(4)
        observed=run_voting_multitask(scene,channel('voting_multitask',5),0.,
                                     external_observer=obs.observe)
        self.assertEqual(pure.routes,observed.routes)
        self.assertEqual(pure.ledger,observed.ledger)
        self.assertEqual(pure.elapsed_ms,observed.elapsed_ms)
        self.assertEqual(obs.observed_phases,4)
        self.assertAlmostEqual(obs.first_feasible_ms,observed.elapsed_ms)

    def test_original_greedy_voting_observer_never_changes_cost_vote_score_commit(self):
        scene=generate_e0_scenario(0,4,4)
        prof=profile()
        arm=next(x for x in selected_e9i_arms() if x[0]=="adaptive_guarded_k1_received")
        cost,votes=build_e9h_deadline_schedule(profile=prof,robots=4,
                                               design_rate_mbps=144.,margin_factor=1.)
        guarded=max(cost.deadline_ms,DEFAULT_OLD_FIXED_MS)
        native=dict(scenario=scene,profile=prof,n=4,seed=0,p_loss=0.,
                    p_vote_loss=0.,rate=144.,max_rounds=30,
                    fixed_timeout_ms=DEFAULT_OLD_FIXED_MS,
                    arm=arm,schedules={1.0:(cost,votes)},
                    oracle_total_cost=solve_hungarian_assignment(scene.cost_matrix).total_cost,
                    guarded_cost_ms=guarded)
        pure=run_e9h_original_voting_case(**native)
        observer=FirstFeasibleObserver(4)
        observed=run_e9h_original_voting_case(**native,external_observer=observer.observe)
        self.assertEqual(pure,observed)
        self.assertGreater(observer.observed_phases,0)

    def test_original_cbaa_observer_never_changes_consensus(self):
        scenario=generate_e0_scenario(0,4,4)
        kwargs=dict(cost_matrix=scenario.cost_matrix,loss_probability=0.,
                    phase_timeout_ms=50.,max_iterations=160,
                    stop_mode='local_certification')
        pure=simulate_cbaa(sampler=sampler(7),loss_sampler=BernoulliLossSampler(7),**kwargs)
        obs=FirstFeasibleObserver(4)
        seen=simulate_cbaa(sampler=sampler(7),loss_sampler=BernoulliLossSampler(7),
                           external_observer=obs.observe,**kwargs)
        self.assertEqual(pure.observer_agreed_pairs,seen.observer_agreed_pairs)
        self.assertEqual(pure.payload_bytes,seen.payload_bytes)
        self.assertEqual(pure.iterations,seen.iterations)
        self.assertGreater(obs.observed_phases,0)

    def test_original_price_auction_bid_award_callback_no_policy_effect(self):
        scenario=generate_e0_scenario(0,4,4)
        kwargs=dict(cost_matrix=scenario.cost_matrix,bid_loss=0.,award_loss=0.,
                    epsilon=10.,stage_window_ms=50.,safety_rounds=160)
        pure=simulate_price_auction(sampler=sampler(7),loss_sampler=BernoulliLossSampler(7),**kwargs)
        obs=FirstFeasibleObserver(4)
        seen=simulate_price_auction(sampler=sampler(7),loss_sampler=BernoulliLossSampler(7),
                                    external_observer=obs.observe,**kwargs)
        self.assertEqual(pure.assignment,seen.assignment)
        self.assertEqual(pure.sender_bytes,seen.sender_bytes)
        self.assertEqual(pure.stop_reason,seen.stop_reason)
        self.assertGreater(obs.observed_phases,0)


if __name__=='__main__':
    unittest.main()
