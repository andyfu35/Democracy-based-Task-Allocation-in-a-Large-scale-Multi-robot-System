import tempfile
import unittest
from pathlib import Path
from argparse import Namespace
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.multitask_scenario import generate_multitask_scene
from experiments.run_e9m_multitask import (prepare_e9m_output, run_e9m_case,
                                           summarize_e9m, validate_e9m_arguments)
from test_e9m_cbba import test_profile


class TestE9MRunner(unittest.TestCase):
    def test_invalid_capacity_and_duplicate_method(self):
        args = Namespace(robots=25, tasks=101, capacity=4, loss=0.0,
                         seeds=3, max_rounds=160, methods="cbba,cbba")
        with self.assertRaises(ProtocolError):
            validate_e9m_arguments(args)
        args.tasks = 100
        with self.assertRaises(ProtocolError):
            validate_e9m_arguments(args)

    def test_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "e9m"
            prepare_e9m_output(path)
            with self.assertRaises(ProtocolError):
                prepare_e9m_output(path)

    def test_paired_scene_case_and_summary(self):
        scene = generate_multitask_scene(1, 4, 8, 2)
        a = run_e9m_case(scene, "cbba", test_profile(), 0, 160)
        b = run_e9m_case(scene, "voting_multitask", test_profile(), .30, 160)
        self.assertEqual(a["success"], 1, a)
        self.assertEqual(b["success"], 1, b)
        summary = summarize_e9m([a, b], ("cbba", "voting_multitask"))
        self.assertEqual([x["completion_rate"] for x in summary], [1.0, 1.0])


if __name__ == "__main__":
    unittest.main()
