"""E9C-1 independent wire-format, physical information, and original-owner tests."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from democracy_mrta.coordination import (
    build_received_pose_retirement_snapshot,
    cost_row_payload_bytes,
    simulate_democracy_hungarian_retirement,
)
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import BernoulliLossSampler
from democracy_mrta.task_information import (
    MAX_APPLICATION_PACKET_BYTES, TASK_RECORD, ROBOT_RECORD, WIRE_HEADER,
    broadcast_task_information, broadcast_robot_positions,
    decode_task_announcement, encode_task_announcement,
    reconstruct_local_cost_rows,
)
from experiments.run_e9c_real_information import (
    prepare_e9c_evidence, run_e9c_real_information, validate_e9c_case,
)


class ConstantLatency:
    def sample_ms(self, key: str) -> float:
        return 5.0


class RealInformationWireTests(unittest.TestCase):
    def tasks(self):
        return ((1.5, 2.5), (3.0, 4.0))

    def poses(self):
        return ((0.0, 0.0), (5.0, 5.0))

    def task_trace(self):
        return broadcast_task_information(
            task_positions=self.tasks(), num_robots=2,
            sampler=ConstantLatency(), loss_sampler=BernoulliLossSampler(seed=0),
            p_loss=0.0, phase_timeout_ms=10.0,
        )

    def pose_trace(self):
        return broadcast_robot_positions(
            robot_positions=self.poses(), sampler=ConstantLatency(),
            loss_sampler=BernoulliLossSampler(seed=0),
            p_loss=0.0, phase_timeout_ms=10.0,
        )

    def run_small(self, root: Path, *, cbaa_iterations=(1, 3)):
        with (
            patch("experiments.run_e9c_real_information.ensure_rady_dataset", return_value=root),
            patch("experiments.run_e9c_real_information.load_rady_latency_profile", return_value=object()),
            patch("experiments.run_e9c_real_information.summarize_latency_profile", return_value={"max_ms": 10.0}),
            patch("experiments.run_e9c_real_information.EmpiricalLatencySampler", return_value=ConstantLatency()),
            patch("experiments.run_e9c_real_information.read_retirement_revision", return_value="test-e9c-sha"),
        ):
            return run_e9c_real_information(
                robots=2, tasks=2, seed=0, cbaa_iterations=cbaa_iterations,
                max_rounds=8, dataset_path=root,
                output_root=root / "e9c_smoke", allow_download=False,
            )

    def test_real_wire_frame_sizes_for_100_robots_50_tasks(self):
        locations = tuple((float(i), float(i * 2)) for i in range(50))
        frames = encode_task_announcement(locations)
        self.assertEqual((WIRE_HEADER.size, TASK_RECORD.size, ROBOT_RECORD.size), (16, 32, 20))
        self.assertEqual(len(frames), 2)
        self.assertEqual(tuple(len(packet) for packet in frames), (1200, 432))
        self.assertEqual(sum(map(len, frames)), 1632)
        self.assertTrue(all(len(frame) <= MAX_APPLICATION_PACKET_BYTES for frame in frames))
        decoded = decode_task_announcement(frames, expected_tasks=50)
        self.assertEqual(
            tuple((task.x, task.y) for task in decoded), locations,
        )
        self.assertEqual(
            {(task.task_type, task.priority, task.deadline_ms) for task in decoded},
            {(0, 1, 0)},
        )

    def test_task_information_sent_once_to_all_receivers_not_free_matrix(self):
        trace = self.task_trace()
        self.assertEqual(len(trace.events), 1)
        self.assertEqual((trace.sender_bytes, trace.events[0].payload_bytes), (80, 80))
        self.assertEqual(trace.events[0].sender_id, 2)
        self.assertEqual(len(trace.deliveries), 2)
        self.assertTrue(all(item.delivered for item in trace.deliveries))
        self.assertEqual(
            tuple(tuple((t.x, t.y) for t in tasks) for tasks in trace.per_robot_tasks),
            (self.tasks(), self.tasks()),
        )
        rows = reconstruct_local_cost_rows(
            local_robot_positions=self.poses(),
            announced_tasks_by_robot=trace.per_robot_tasks,
        )
        self.assertEqual(rows[0][0], 2.9154759474226504)

    def test_paid_peer_position_packets_are_36_bytes_each_and_decoded(self):
        result = self.pose_trace()
        self.assertEqual((result.sender_bytes, len(result.events)), (72, 2))
        self.assertEqual(len(result.deliveries), 2)
        self.assertEqual(result.per_robot_positions, (self.poses(), self.poses()))
        snapshot = build_received_pose_retirement_snapshot(
            per_robot_positions=result.per_robot_positions,
        )
        self.assertEqual(snapshot.visible_by_voter, (frozenset((0, 1)),) * 2)
        self.assertEqual(snapshot.events, ())
        self.assertEqual(snapshot.deliveries, ())

    def test_total_loss_in_task_announcement_is_dependency_not_hidden_data(self):
        with self.assertRaises(ProtocolError) as cm:
            broadcast_task_information(
                task_positions=self.tasks(), num_robots=2,
                sampler=ConstantLatency(), loss_sampler=BernoulliLossSampler(seed=0),
                p_loss=1.0, phase_timeout_ms=10.0,
            )
        d = cm.exception.diagnostic
        self.assertEqual((d.owner, d.function, d.category, d.code), (
            "democracy_mrta.task_information", "broadcast_task_information",
            "dependency", "TASK_ANNOUNCEMENT_INCOMPLETE",
        ))

    def test_total_loss_in_peer_positions_is_dependency_not_hidden_data(self):
        with self.assertRaises(ProtocolError) as cm:
            broadcast_robot_positions(
                robot_positions=self.poses(), sampler=ConstantLatency(),
                loss_sampler=BernoulliLossSampler(seed=0),
                p_loss=1.0, phase_timeout_ms=10.0,
            )
        self.assertEqual(cm.exception.diagnostic.code, "ROBOT_POSE_VIEWS_INCOMPLETE")
        self.assertEqual(cm.exception.diagnostic.category, "dependency")

    def test_malformed_task_frame_cannot_be_treated_as_success(self):
        raw = encode_task_announcement(self.tasks())
        bad = (b"NOPE" + raw[0][4:],)
        with self.assertRaises(ProtocolError) as cm:
            decode_task_announcement(bad, expected_tasks=2)
        self.assertEqual(cm.exception.diagnostic.code, "TASK_FRAME_MALFORMED")

    def test_received_positions_enable_existing_greedy_without_cost_broadcast(self):
        task_trace, pose_trace = self.task_trace(), self.pose_trace()
        matrix = reconstruct_local_cost_rows(
            local_robot_positions=self.poses(),
            announced_tasks_by_robot=task_trace.per_robot_tasks,
        )
        common = dict(
            cost_matrix=matrix, sampler=ConstantLatency(),
            loss_sampler=BernoulliLossSampler(seed=1),
            p_loss=0.0, p_vote_loss=0.0,
            phase_timeout_ms=10.0, max_rounds=8,
            voting_strategy="greedy_task",
            vote_decision_rule="quarter_plurality", vote_repetitions=1,
        )
        original = simulate_democracy_hungarian_retirement(**common)
        snapshot = build_received_pose_retirement_snapshot(
            per_robot_positions=pose_trace.per_robot_positions,
        )
        shared = simulate_democracy_hungarian_retirement(
            **common, preknown_cost_snapshot=snapshot,
        )
        self.assertEqual(original.assigned_pairs, shared.assigned_pairs)
        self.assertEqual(original.committed_tasks, 2)
        self.assertEqual(
            sum(event.payload_bytes for trace in original.rounds
                for event in trace.coordination.events if event.phase == "cost"),
            2 * cost_row_payload_bytes(2),
        )
        self.assertFalse(any(
            event.phase == "cost" for trace in shared.rounds
            for event in trace.coordination.events
        ))
        self.assertEqual(shared.payload_bytes + 72,
                         original.payload_bytes - 64 + 72)

    def test_incomplete_pose_provenance_rejected_at_actual_owner(self):
        with self.assertRaises(ProtocolError) as cm:
            build_received_pose_retirement_snapshot(
                per_robot_positions=(((0.0, 0.0),), ((1.0, 1.0), (0.0, 0.0))),
            )
        d = cm.exception.diagnostic
        self.assertEqual((d.function, d.category, d.code), (
            "build_received_pose_retirement_snapshot", "dependency",
            "INCOMPLETE_PEER_POSE_VIEWS",
        ))

    def test_runner_one_seed_rows_and_sha256_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            rows = self.run_small(root)
            self.assertEqual(len(rows), 4)
            self.assertEqual([row["method"] for row in rows], [
                "democracy_original_cost_rows",
                "democracy_received_peer_positions",
                "cbaa_sync_single_assignment_K1",
                "cbaa_sync_single_assignment_K3",
            ])
            self.assertTrue(all(row["task_announcement_sender_bytes"] == 80 for row in rows))
            self.assertEqual(rows[0]["democracy_cost_rows_sender_bytes"], 64)
            self.assertEqual(rows[1]["democracy_cost_rows_sender_bytes"], 0)
            self.assertEqual(rows[1]["peer_robot_position_sender_bytes"], 72)
            self.assertTrue(all(row["cbaa_bid_vector_sender_bytes"] == 0 for row in rows[:2]))
            self.assertEqual([row["cbaa_bid_vector_sender_bytes"] for row in rows[2:]], [80, 240])
            self.assertTrue(all(
                row["end_to_end_sender_application_bytes"] ==
                row["task_announcement_sender_bytes"] +
                row["peer_robot_position_sender_bytes"] +
                row["original_coordination_sender_bytes"]
                for row in rows
            ))
            self.assertEqual(rows[0]["completed_or_observer_agreed_tasks"], 2)
            self.assertEqual(rows[1]["completed_or_observer_agreed_tasks"], 2)
            self.assertEqual(rows[0]["success_semantics"], "actual_reliable_commit")
            self.assertEqual(rows[2]["success_semantics"], "posthoc_full_observer_agreement_not_commit")
            raw = root / "e9c_smoke" / "actual_wire_bytes.csv"
            manifest = json.loads((root / "e9c_smoke" / "manifest.json").read_text())
            self.assertEqual(manifest["source_git_sha"], "test-e9c-sha")
            self.assertEqual(manifest["raw_sha256"], hashlib.sha256(raw.read_bytes()).hexdigest())
            with raw.open(encoding="utf-8", newline="") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 4)

    def test_old_results_and_new_raw_cannot_be_overwritten(self):
        with self.assertRaises(ProtocolError) as cm:
            prepare_e9c_evidence(Path("results/e9b_equal_sender_budget_pilot"))
        self.assertEqual(cm.exception.diagnostic.code, "E9C_PROTECTED_RESULT_ROOT")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.run_small(root, cbaa_iterations=(1,))
            with self.assertRaises(ProtocolError) as cm:
                self.run_small(root, cbaa_iterations=(1,))
            self.assertEqual(cm.exception.diagnostic.code, "E9C_OUTPUT_ALREADY_EXISTS")

    def test_benchmark_axes_are_not_guessed_from_user_input(self):
        for shape in ({"robots": 0}, {"tasks": 3}, {"seed": -1},
                      {"max_rounds": 1}, {"robots": True}):
            args = dict(robots=2, tasks=2, seed=0, max_rounds=2,
                        cbaa_iterations=(1, 3))
            args.update(shape)
            with self.subTest(shape=shape), self.assertRaises(ProtocolError):
                validate_e9c_case(**args)
        with self.assertRaises(ProtocolError):
            validate_e9c_case(
                robots=2, tasks=2, seed=0, max_rounds=2,
                cbaa_iterations=(3, 1),
            )


if __name__ == "__main__":
    unittest.main()
