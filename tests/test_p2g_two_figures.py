"""P2G two figure source gates: task-order one-shot versus Global Greedy repeat."""
from __future__ import annotations

from argparse import Namespace
import unittest
import xml.etree.ElementTree as ET

from democracy_mrta.diagnostics import ProtocolError
from experiments.p2g_plot import FAMILIES, render_p2g_figure
from experiments.run_p2g_two_figures import (
    LOSSES, NEW_MODES, validate_p2g_config,
    read_verified_legacy_summary, build_figure_source, case_keys,
    summarize_new_p2g, validate_p2g_grid, validate_p2g_zero_loss,
    measure_p2g_complete_quality,
)
from democracy_mrta.optimizer import (
    solve_visible_batched_greedy_assignment,
    solve_visible_task_ordered_greedy_assignment,
)


def sample_args(**change):
    values=dict(
        losses=",".join(f"{x/100:.2f}" for x in LOSSES),
        seeds=100,first_seed=0,formal=True,
    )
    values.update(change)
    return Namespace(**values)


def record(loss,mode,seed=0,success=True):
    return {
        "loss_percent":loss,"seed":seed,"mode":mode,
        "scene_sha256":"matched_scene","full_info_reference_cost_m":200.,
        "rounds_executed":300 if mode=="centralized_retry" else 1,
        "task_coverage":1. if success else .7,
        "committed_task_count":100 if success else 70,
        "native_sender_bytes":200000,"cost_sender_bytes":81000,
        "native_success":int(success),"final_feasible":int(success),
        "cost_increase_percent":5. if success else "",
        "native_stop_ms":40000.,
    }


def synthetic_plot_row(loss,method,success):
    return {
        "loss_percent":loss,"method":method,"trials":2,
        "native_complete":2 if success else 0,
        "completion_rate_percent":100. if success else 0.,
        "quality_sample_count":2 if success else 0,
        "cost_increase_percent":2.25 if success else "",
        "mean_stop_s":3.0,"mean_sender_kb":115.0,
    }


class P2GStudyTests(unittest.TestCase):
    def test_formal_is_100_seeds_10_losses(self):
        self.assertEqual(validate_p2g_config(sample_args()),LOSSES)
        for changes in (
            {"seeds":2},{"losses":"0.00,0.90"},
            {"losses":"0.00,0.25,0.90"},
            {"first_seed":1},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ProtocolError):
                    validate_p2g_config(sample_args(**changes))

    def test_verified_published_historical_50_groups_not_replaced(self):
        legacy,provenance=read_verified_legacy_summary(LOSSES)
        self.assertEqual(len(legacy),50)
        self.assertEqual(len(provenance["p2de_verified_blob"]),40)
        self.assertEqual(len(provenance["p2de_verified_sha256"]),64)
        self.assertEqual(sum(r["method"]=="cbaa" for r in legacy),10)

    def test_three_new_modes_have_exact_paired_geometry_and_reference(self):
        expected=tuple((0,seed,mode) for seed in range(2) for mode in NEW_MODES)
        self.assertEqual(case_keys((0,),0,2),expected)
        good=[record(0,mode) for mode in NEW_MODES]
        validate_p2g_grid(good,(0,),0,1)
        bad=[dict(r) for r in good]
        bad[1]["scene_sha256"]="different"
        with self.assertRaises(ProtocolError) as caught:
            validate_p2g_grid(bad,(0,),0,1)
        self.assertEqual(caught.exception.diagnostic.code,"P2G_SCENE_NOT_PAIRED")
        bad=[dict(r) for r in good]
        bad[1]["full_info_reference_cost_m"]=202.
        with self.assertRaises(ProtocolError):
            validate_p2g_grid(bad,(0,),0,1)

    def test_no_loss_requires_matching_family_greedy_cost(self):
        rows=[record(0,mode) for mode in NEW_MODES]
        for row in rows:
            row["cost_increase_percent"]=0.
        validate_p2g_zero_loss(rows)
        rows[0]["cost_increase_percent"]=1.0
        with self.assertRaises(ProtocolError) as caught:
            validate_p2g_zero_loss(rows)
        self.assertEqual(caught.exception.diagnostic.code,"P2G_ZERO_LOSS_FAILED")

    def test_missing_cost_is_not_zero_in_new_summary(self):
        summary=summarize_new_p2g(
            [record(90,mode,success=False) for mode in NEW_MODES],(90,)
        )
        self.assertEqual(len(summary),3)
        for r in summary:
            self.assertEqual(r["native_complete"],0)
            self.assertEqual(r["quality_sample_count"],0)
            self.assertEqual(r["cost_increase_percent"],"")
            self.assertGreater(r["mean_sender_kb"],0)
            self.assertGreater(r["mean_stop_s"],0)

    def test_big_figures_are_four_panel_svg_with_correct_reference(self):
        for family,methods in FAMILIES.items():
            rows=[synthetic_plot_row(loss,m,success=(loss==0))
                  for loss in (0,90) for m in methods]
            svg=render_p2g_figure(rows,(0,90),family)
            self.assertIn('viewBox="0 0 1800 1240"',svg)
            self.assertIn("A. Full allocation success",svg)
            self.assertIn("B. Cost increase",svg)
            self.assertIn("C. Communication stop time",svg)
            self.assertIn("D. Attempted communication payload",svg)
            self.assertIn(
                "task-ordered Greedy" if family=="one_attempt"
                else "Global Greedy", svg,
            )
            root=ET.fromstring(svg)
            self.assertTrue(root.tag.endswith("svg"))
            self.assertEqual(len(methods),2 if family=="one_attempt" else 4)

    def test_missing_success_cost_cannot_be_imputed(self):
        rows=[synthetic_plot_row(90,m,False)
              for m in FAMILIES["one_attempt"]]
        rows[0]["cost_increase_percent"]=0
        with self.assertRaises(ProtocolError) as caught:
            render_p2g_figure(rows,(90,),"one_attempt")
        self.assertEqual(caught.exception.diagnostic.code,
                         "P2G_FAKE_OR_MISSING_QUALITY")

    def test_historical_new_source_mapping_does_not_reuse_old_central_one_shot(self):
        legacy,_=read_verified_legacy_summary(LOSSES)
        new=[]
        for p in LOSSES:
            for m in NEW_MODES:
                new.append({
                    "loss_percent":p,"method":m,"trials":100,
                    "native_complete":100,"completion_rate_percent":100,
                    "mean_task_coverage":1.,"quality_sample_count":100,
                    "cost_increase_percent":0.,
                    "mean_stop_s":1.,"mean_sender_kb":120.,
                })
        figures=build_figure_source(new,legacy,LOSSES)
        self.assertEqual(len(figures["one_attempt"]),20)
        self.assertEqual(len(figures["repeatable"]),40)
        self.assertEqual(
            {r["method"] for r in figures["one_attempt"]},
            set(FAMILIES["one_attempt"]),
        )
        self.assertEqual(
            {r["method"] for r in figures["repeatable"]},
            set(FAMILIES["repeatable"]),
        )
        self.assertNotIn(
            "centralized_one_shot",
            {r["method"] for rows in figures.values() for r in rows},
        )

    def test_mode_specific_reference_planner_is_not_a_single_hidden_oracle(self):
        matrix=((2.,1.),(3.,100.))
        global_plan=solve_visible_batched_greedy_assignment(matrix,{0,1})
        order_plan=solve_visible_task_ordered_greedy_assignment(matrix,{0,1})
        self.assertEqual(global_plan.assigned_pairs,((1,0),(0,1)))
        self.assertEqual(order_plan.assigned_pairs,((0,0),(1,1)))
        scene=Namespace(cost_matrix=matrix,num_robots=2)
        native=dict(native_success=1,final_feasible=1,
                    final_total_distance_m=order_plan.total_cost)
        for mode in ("task_ordered_vote_once","centralized_task_ordered_once"):
            denom,total,gap=measure_p2g_complete_quality(scene,native,mode)
            self.assertEqual(denom,order_plan.total_cost)
            self.assertEqual(gap,0.)
        denom,total,gap=measure_p2g_complete_quality(scene,native,"centralized_retry")
        self.assertEqual(denom,global_plan.total_cost)
        self.assertGreater(gap,0.)


if __name__=="__main__":
    unittest.main()
