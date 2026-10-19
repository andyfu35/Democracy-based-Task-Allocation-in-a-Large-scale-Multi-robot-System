"""P2G two large family figure source, missing-cost and frozen evidence tests."""
from __future__ import annotations

from argparse import Namespace
import unittest
import xml.etree.ElementTree as ET

from democracy_mrta.diagnostics import ProtocolError
from experiments.p2g_plot import FAMILIES, render_p2g_figure
from experiments.run_p2g_two_figures import (
    LOSSES, NEW_MODES, validate_p2g_config,
    read_verified_legacy_summary, build_figure_source, case_keys,
    summarize_new_p2g, validate_p2g_grid,
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
        "scene_sha256":"matched_scene","full_info_greedy_cost_m":200.,
        "rounds_executed":100 if mode=="sequential_once" else 4,
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

    def test_exact_two_new_modes_and_paired_geometry(self):
        expected=((0,0,"sequential_once"),(0,0,"centralized_retry"),
                  (0,1,"sequential_once"),(0,1,"centralized_retry"))
        self.assertEqual(case_keys((0,),0,2),expected)
        good=[record(0,mode) for mode in NEW_MODES]
        validate_p2g_grid(good,(0,),0,1)
        bad=[dict(r) for r in good]
        bad[1]["scene_sha256"]="different"
        with self.assertRaises(ProtocolError) as caught:
            validate_p2g_grid(bad,(0,),0,1)
        self.assertEqual(caught.exception.diagnostic.code,"P2G_SCENE_NOT_PAIRED")

    def test_missing_cost_is_not_zero_in_new_summary(self):
        summary=summarize_new_p2g(
            [record(90,"sequential_once",success=False),
             record(90,"centralized_retry",success=False)],(90,)
        )
        self.assertEqual(len(summary),2)
        for r in summary:
            self.assertEqual(r["native_complete"],0)
            self.assertEqual(r["quality_sample_count"],0)
            self.assertEqual(r["cost_increase_percent"],"")
            self.assertGreater(r["mean_sender_kb"],0)
            self.assertGreater(r["mean_stop_s"],0)

    def test_big_figures_are_four_panel_svg_with_own_methods(self):
        for family,methods in FAMILIES.items():
            rows=[synthetic_plot_row(loss,m,success=(loss==0))
                  for loss in (0,90) for m in methods]
            svg=render_p2g_figure(rows,(0,90),family)
            self.assertIn('viewBox="0 0 1800 1240"',svg)
            self.assertIn("A. Full allocation success",svg)
            self.assertIn("B. Cost increase",svg)
            self.assertIn("C. Communication stop time",svg)
            self.assertIn("D. Attempted communication payload",svg)
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

    def test_historical_new_source_exact_mapping(self):
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
            {r["method"] for r in figures["repeatable"]},
            set(FAMILIES["repeatable"]),
        )


if __name__=="__main__":
    unittest.main()
