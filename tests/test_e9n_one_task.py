"""E9N formal grid, true historical geometry, evidence integrity and plot tests."""
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.multitask_scenario import generate_multitask_scene
from experiments.plot_e9m_unified_comparison import validate_legacy_source
from experiments.plot_e9n_unified import (
    SIZES, compose_five_method_rows, render_five_method_svg, require_e9n_plot_grid)
from experiments.run_e9n_one_task import (
    parse_e9n_sizes, validate_e9n_contract, verify_geometry_identity,
    summarize_e9n_cases, prepare_e9n_output)


class TestE9NOneTask(unittest.TestCase):
    def test_original_e9i_j_l_scenarios_match_exact_geometry(self):
        for n in (5, 25, 100):
            for seed in (0, 17, 99):
                scene = generate_multitask_scene(seed, n, n, 1)
                fingerprint = verify_geometry_identity(scene)
                self.assertEqual(len(fingerprint), 64)
                self.assertEqual(fingerprint, verify_geometry_identity(scene))

    def test_preregistered_formal_grid_and_smoke_contract(self):
        self.assertEqual(parse_e9n_sizes("5,25,100"), (5, 25, 100))
        with self.assertRaises(ProtocolError) as c:
            parse_e9n_sizes("5,25,25")
        self.assertEqual(c.exception.diagnostic.code, "E9N_INVALID_SIZES")
        args = Namespace(sizes=",".join(map(str, SIZES)),seeds=100,
                         loss=.30,max_rounds=160,formal=True)
        self.assertEqual(validate_e9n_contract(args), SIZES)
        args.seeds=99
        with self.assertRaises(ProtocolError) as c:
            validate_e9n_contract(args)
        self.assertEqual(c.exception.diagnostic.code, "E9N_FORMAL_CONFIG_FROZEN")
        args.formal=False
        with self.assertRaises(ProtocolError) as c:
            validate_e9n_contract(args)
        self.assertEqual(c.exception.diagnostic.code, "E9N_SMOKE_TOO_LARGE")

    def test_keep_failed_seed_in_all_seed_time_bytes_denominator(self):
        rows = [
            {"robots":5,"method":"cbba","seed":0,"success":1,
             "guard_censored":0,"allocation_ms":1000.0,"sender_bytes":100,
             "sender_sends":2,"total_distance_m":20,"makespan_s":5,
             "discounted_reward":100},
            {"robots":5,"method":"cbba","seed":1,"success":0,
             "guard_censored":1,"allocation_ms":9000.0,"sender_bytes":900,
             "sender_sends":20,"total_distance_m":0,"makespan_s":0,
             "discounted_reward":0},
            {"robots":5,"method":"voting_multitask","seed":0,"success":1,
             "guard_censored":0,"allocation_ms":4000.0,"sender_bytes":200,
             "sender_sends":5,"total_distance_m":30,"makespan_s":10,
             "discounted_reward":88},
            {"robots":5,"method":"voting_multitask","seed":1,"success":1,
             "guard_censored":0,"allocation_ms":6000.0,"sender_bytes":400,
             "sender_sends":8,"total_distance_m":40,"makespan_s":12,
             "discounted_reward":99},
        ]
        output = summarize_e9n_cases(rows,(5,),2)
        self.assertEqual(len(output),2)
        cbba = next(x for x in output if x['method']=='cbba')
        self.assertEqual(cbba['completed_seeds'],1)
        self.assertEqual(cbba['completion_rate'],.5)
        self.assertEqual(cbba['guard_censored_seeds'],1)
        self.assertEqual(cbba['mean_all_seed_stop_ms'],5000)
        self.assertEqual(cbba['mean_all_seed_sender_bytes'],500)
        self.assertEqual(cbba['mean_success_only_total_distance_m'],20)

    def test_one_five_method_figure_and_no_invented_e9i_j_success(self):
        legacy = validate_legacy_source(
            Path('docs/figures/e9l_price/formal/three_algorithm_plot_source_20point.csv'))
        new = []
        for n in SIZES:
            for method in ('voting_multitask','cbba'):
                new.append({'robots':n,'method':method,'total_seeds':100,
                            'mean_all_seed_stop_ms':n*100,
                            'mean_all_seed_sender_bytes':n*1000,
                            'completion_rate':1.0})
        rows=compose_five_method_rows(legacy,new)
        self.assertEqual(len(rows),20*5)
        missing=[r for r in rows if r['method'] in ('voting_e9i','cbaa_e9j')]
        self.assertTrue(all(r['success_rate']=='' for r in missing))
        self.assertEqual(len([r for r in rows if r['method']=='auction_e9l']),20)
        svg=render_five_method_svg(rows)
        self.assertIn('Original CBBA C1',svg)
        self.assertIn('same capacity-one',svg)
        self.assertNotIn('Paid CBAA',svg)
        import xml.etree.ElementTree as ET
        self.assertEqual(ET.fromstring(svg).tag,'{http://www.w3.org/2000/svg}svg')
        with self.assertRaises(ProtocolError) as c:
            require_e9n_plot_grid(new[:-1])
        self.assertEqual(c.exception.diagnostic.code,'E9N_INCOMPLETE_PLOT_GRID')

    def test_immutable_output_root(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/'e9n'
            prepare_e9n_output(p)
            with self.assertRaises(ProtocolError) as c:
                prepare_e9n_output(p)
            self.assertEqual(c.exception.diagnostic.code,'E9N_OUTPUT_EXISTS')


if __name__=='__main__':
    unittest.main()
