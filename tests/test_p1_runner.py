"""P1 frozen formal axes, paired keys and compact evidence presentation."""
import argparse
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from democracy_mrta.diagnostics import ProtocolError
from experiments.run_p1_matched_five import (METHODS,parse_sizes,validate_config,
    validate_complete_grid,summarize,paired_five_quality)
from experiments.p1_plot import render_p1_figure, validate_plot_source


class TestP1Runner(unittest.TestCase):
    @staticmethod
    def args(**kw):
        data=dict(sizes="25,50,100",seeds=100,first_seed=0,loss=.30,
                  guard=160,voting_guard=300,formal=True,
                  methods=",".join(METHODS))
        data.update(kw)
        return argparse.Namespace(**data)

    def test_formal_frozen_grid_and_methods(self):
        self.assertEqual(validate_config(self.args()),(25,50,100))
        for changes in ({"loss":.0},{"methods":"voting,cbba"},
                        {"sizes":"25,50"},{"seeds":3},{"guard":159}):
            with self.subTest(changes=changes), self.assertRaises(ProtocolError):
                validate_config(self.args(**changes))
        with self.assertRaises(ProtocolError):
            parse_sizes("25,25,100")

    def test_grid_rejects_missing_or_duplicate(self):
        rows=[dict(robots=25,seed=0,method=m,scene_sha256="one") for m in METHODS]
        validate_complete_grid(rows,(25,),1,0,METHODS)
        with self.assertRaises(ProtocolError) as exc:
            validate_complete_grid(rows[:-1],(25,),1,0,METHODS)
        self.assertEqual(exc.exception.diagnostic.code,"P1_INCOMPLETE_OR_DUPLICATE_GRID")
        rows[-1]["scene_sha256"]="different"
        with self.assertRaises(ProtocolError) as exc:
            validate_complete_grid(rows,(25,),1,0,METHODS)
        self.assertEqual(exc.exception.diagnostic.code,"P1_PAIRED_SCENE_SHA_MISMATCH")

    def test_provisional_smoke_appends_exact_original_rows_and_manifest(self):
        from experiments import run_p1_matched_five as mod
        def fake_scene(seed,n,_tasks):
            return SimpleNamespace(seed=seed,num_robots=n,num_tasks=n)
        def fake_case(scene,_profile,method,_loss,_guard,_voting_guard):
            return {"robots":scene.num_robots,"tasks":scene.num_robots,"capacity":1,
                    "seed":scene.seed,"scene_sha256":"same-seed-scene",
                    "method":method,"p_loss":0.30,"native_success":1,
                    "native_stop_reason":"paid-or-native","native_guard_censored":0,
                    "native_stop_ms":500.0,"observer_snapshots":5,
                    "first_feasible_seen":1,"first_feasible_ms":400.,
                    "first_feasible_cost_m":12.,"first_feasible_hungarian_ratio":1.2,
                    "final_feasible":1,"final_total_distance_m":12.,
                    "final_makespan_s":3.,"final_hungarian_gap_m":2.,
                    "final_hungarian_ratio":1.2,"oracle_total_m":10.,
                    "native_sender_sends":7,"native_sender_bytes":400,
                    "native_receiver_attempts":10,"native_receiver_drops":3,
                    "original_traffic_ledger_json":"{}","native_assignment_json":"[]",
                    "native_diagnostic":"","method_contract":method}
        with tempfile.TemporaryDirectory() as d:
            args=mod.parse_args(["--sizes","25","--seeds","2",
                                 "--loss","0.30","--output-root",str(Path(d)/"test_run")])
            with patch.object(mod,"generate_e0_scenario",side_effect=fake_scene), \
                 patch.object(mod,"verify_one_scene",return_value="same-seed-scene"), \
                 patch.object(mod,"run_matched_case",side_effect=fake_case), \
                 patch.object(mod,"load_rady_latency_profile",return_value="profile"), \
                 patch.object(mod,"ensure_rady_dataset",return_value="profile_path"), \
                 patch.object(mod,"read_source_sha",return_value="a"*40):
                rows=mod.run_p1(args)
            self.assertEqual(len(rows),10)
            run=Path(d)/"test_run"
            with (run/"manifest_p1.json").open() as f:
                manifest=json.load(f)
            self.assertEqual(manifest["git_sha"],"a"*40)
            self.assertEqual(manifest["config"]["methods"],list(METHODS))
            self.assertEqual(len(manifest["sha256"]),3)
            with self.assertRaises(ProtocolError):
                mod.ensure_new_output(run)

    def test_summary_and_common_quality_never_drop_failure_denominators(self):
        rows=[]
        for n in (25,50,100):
            for seed in (0,1):
                for method in METHODS:
                    native=int(not (seed==1 and method=="price_auction"))
                    rows.append(dict(robots=n,seed=seed,method=method,
                                     native_success=native,final_feasible=native,
                                     first_feasible_seen=native,
                                     native_guard_censored=1-native,
                                     native_diagnostic="",native_stop_ms=1000.,
                                     native_sender_bytes=100,
                                     first_feasible_ms=900.,final_hungarian_ratio=1.1,
                                     method_contract=method))
        summary=summarize(rows,(25,50,100),METHODS)
        one=next(r for r in summary if r["robots"]==100 and r["method"]=="price_auction")
        self.assertEqual((one["trials"],one["native_complete"],one["guard_censored"]),(2,1,1))
        quality=paired_five_quality(rows,(25,50,100),2,0)
        self.assertEqual({r["same_success_paired_seeds"] for r in quality},{1})
        fig=render_p1_figure(summary,quality)
        self.assertIn("First globally feasible",fig)
        self.assertIn("Paid",fig.replace("paid","Paid"))
        self.assertEqual(fig.count('<svg'),1)
        with self.assertRaises(ProtocolError):
            validate_plot_source(summary[:-1],quality)


if __name__=="__main__":
    unittest.main()
