"""E9C-1 real information-wire cost comparison; opt-in only, no new optimizer.

Each method receives physically encoded/decompressed task descriptions.
Each robot computes its own Euclidean cost from its LOCAL pose + received
tasks. Democracy can either pay for peer COST rows (original) or pay for
peer POSE broadcasts first, then derive all costs locally. CBAA pays for
actual iterative winning-bid/winner-ID vectors, never all other COST rows.
No hidden global cost or free remote pose knowledge enters a local voter.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from democracy_mrta.cbaa import simulate_cbaa
from democracy_mrta.coordination import (
    build_received_pose_retirement_snapshot,
    simulate_democracy_hungarian_retirement,
)
from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler, EmpiricalLatencySampler,
    RADY_SOURCE_BLOB_SHA, RADY_SOURCE_COMMIT,
    ensure_rady_dataset, load_rady_latency_profile, summarize_latency_profile,
)
from democracy_mrta.scenario import generate_e0_scenario
from democracy_mrta.task_information import (
    MAX_APPLICATION_PACKET_BYTES, ROBOT_RECORD, TASK_RECORD, WIRE_HEADER,
    broadcast_robot_positions, broadcast_task_information,
    reconstruct_local_cost_rows,
)
from experiments.run_e2 import write_csv
from experiments.run_e2_retirement import read_retirement_revision


OWNER = "experiments.run_e9c_real_information"
DEFAULT_ROOT = Path("results/e9c_real_information_one_seed")


def validate_e9c_case(
    *, robots: int, tasks: int, seed: int,
    cbaa_iterations: tuple[int, ...], max_rounds: int,
) -> None:
    """Limit first information-provenance experiment to no-loss static E0."""
    axes = (robots, tasks, seed, max_rounds)
    if (any(type(x) is not int for x in axes)
        or not 1 <= tasks <= robots <= 100 or seed < 0 or max_rounds < tasks):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_e9c_case", category="data",
            code="E9C_INVALID_CASE_SHAPE",
            expected="1<=tasks<=robots<=100; seed>=0; max_rounds>=tasks",
            actual=axes,
        ))
    if (type(cbaa_iterations) is not tuple or not cbaa_iterations
        or any(type(k) is not int or k <= 0 for k in cbaa_iterations)
        or tuple(sorted(set(cbaa_iterations))) != cbaa_iterations):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_e9c_case", category="data",
            code="E9C_INVALID_CBAA_ITERATIONS",
            expected="nonempty strictly ascending tuple of positive exact integers",
            actual=cbaa_iterations,
        ))


def prepare_e9c_evidence(output_root: Path) -> None:
    """Immutable result root; cannot replace the prior E2/E8/E9A/E9B data."""
    resolved = output_root.resolve()
    results = Path("results").resolve()
    if (resolved == results or resolved in results.parents
        or (resolved.is_relative_to(results)
            and not resolved.relative_to(results).parts[0].startswith("e9c_"))):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="prepare_e9c_evidence", category="state",
            code="E9C_PROTECTED_RESULT_ROOT",
            expected="fresh results/e9c_* directory or outside project historical evidence",
            actual=str(output_root),
        ))
    if output_root.exists() and (
        not output_root.is_dir() or any(output_root.iterdir())
    ):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="prepare_e9c_evidence", category="state",
            code="E9C_OUTPUT_ALREADY_EXISTS",
            expected="new or empty E9C result directory",
            actual=str(output_root),
        ))


def require_local_source_consistency(*, reconstructed, expected) -> None:
    """External contract audit ONLY; never pass the oracle into a local voter."""
    if len(reconstructed) != len(expected) or any(
        len(a) != len(b) or any(x != y for x, y in zip(a, b))
        for a, b in zip(reconstructed, expected)
    ):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="require_local_source_consistency",
            category="contract", code="E9C_TASK_WIRE_COST_RECONSTRUCTION_MISMATCH",
            expected="local Euclidean rows reconstructed exactly from decoded TASK wire data",
            actual="at least one reconstructed own-row cost differs from original scene",
        ))


def summarize_greedy_wire_phases(result) -> dict[str, int]:
    """Independent observer of ACTUALLY emitted Cost/Vote/Score/Commit events."""
    allowed = ("cost", "vote", "vote_score_announcement", "commit")
    phase_bytes = {phase: 0 for phase in allowed}
    for epoch in result.rounds:
        for event in epoch.coordination.events:
            if event.phase not in phase_bytes:
                raise ProtocolError(Diagnostic(
                    owner=OWNER, function="summarize_greedy_wire_phases",
                    category="contract", code="E9C_UNKNOWN_GREEDY_WIRE_PHASE",
                    expected=allowed, actual=event.phase,
                ))
            phase_bytes[event.phase] += event.payload_bytes
    if sum(phase_bytes.values()) != result.payload_bytes:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="summarize_greedy_wire_phases",
            category="contract", code="E9C_GREEDY_BYTES_MISMATCH",
            expected=result.payload_bytes, actual=sum(phase_bytes.values()),
        ))
    return phase_bytes


def assemble_method_row(
    *,
    method: str, seed: int, robots: int, tasks: int,
    task_wire_bytes: int, task_packets: int,
    pose_wire_bytes: int, pose_packets: int,
    coordination_bytes: int, coordination_packets: int,
    cost_bytes: int, vote_bytes: int, score_bytes: int, commit_bytes: int,
    cbaa_bid_bytes: int, cbaa_k: int, complete_count: int,
    completion_kind: str, complete_all: bool,
) -> dict[str, object]:
    """One transparent phase-level sender-application-payload evidence row."""
    end_to_end = task_wire_bytes + pose_wire_bytes + coordination_bytes
    if (end_to_end != task_wire_bytes + pose_wire_bytes + cost_bytes
        + vote_bytes + score_bytes + commit_bytes + cbaa_bid_bytes):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="assemble_method_row",
            category="contract", code="E9C_PHASE_BYTE_SUM_MISMATCH",
            expected=end_to_end,
            actual=task_wire_bytes + pose_wire_bytes + cost_bytes
                   + vote_bytes + score_bytes + commit_bytes + cbaa_bid_bytes,
        ))
    return {
        "method": method, "seed": seed, "robots": robots, "tasks": tasks,
        "information_policy": (
            "task_plus_paid_peer_positions" if pose_packets
            else "task_plus_own_position_only"
        ),
        "task_announcement_packet_count": task_packets,
        "task_announcement_sender_bytes": task_wire_bytes,
        "peer_robot_position_packet_count": pose_packets,
        "peer_robot_position_sender_bytes": pose_wire_bytes,
        "original_coordination_packet_count": coordination_packets,
        "original_coordination_sender_bytes": coordination_bytes,
        "democracy_cost_rows_sender_bytes": cost_bytes,
        "democracy_vote_sender_bytes": vote_bytes,
        "democracy_score_sender_bytes": score_bytes,
        "democracy_commit_sender_bytes": commit_bytes,
        "cbaa_bid_vector_sender_bytes": cbaa_bid_bytes,
        "cbaa_iterations": cbaa_k,
        "end_to_end_sender_application_bytes": end_to_end,
        "sender_application_messages": task_packets + pose_packets + coordination_packets,
        "completed_or_observer_agreed_tasks": complete_count,
        "success_semantics": completion_kind,
        "full_result_of_own_semantics": int(complete_all),
    }


def run_original_methods_from_local_information(
    *,
    cost_matrix, per_receiver_robot_positions,
    robots: int, tasks: int, seed: int,
    task_wire_bytes: int, task_packets: int,
    pose_wire_bytes: int, pose_packets: int,
    profile, timeout_ms: float, max_rounds: int,
    cbaa_iterations: tuple[int, ...],
) -> list[dict[str, object]]:
    """Invoke ONLY original runtime owners; compare optional shared-pose mode."""
    rows: list[dict[str, object]] = []
    for mode in ("original_cost_rows", "paid_peer_positions"):
        snapshot = (
            build_received_pose_retirement_snapshot(
                per_robot_positions=per_receiver_robot_positions
            ) if mode == "paid_peer_positions" else None
        )
        result = simulate_democracy_hungarian_retirement(
            cost_matrix=cost_matrix,
            sampler=EmpiricalLatencySampler(profile, seed=seed),
            loss_sampler=BernoulliLossSampler(seed=seed),
            p_loss=0.0, p_vote_loss=0.0,
            phase_timeout_ms=timeout_ms, max_rounds=max_rounds,
            voting_strategy="greedy_task",
            vote_decision_rule="quarter_plurality",
            vote_repetitions=1,
            preknown_cost_snapshot=snapshot,
        )
        phases = summarize_greedy_wire_phases(result)
        rows.append(assemble_method_row(
            method="democracy_original_cost_rows" if snapshot is None
                   else "democracy_received_peer_positions",
            seed=seed, robots=robots, tasks=tasks,
            task_wire_bytes=task_wire_bytes, task_packets=task_packets,
            pose_wire_bytes=pose_wire_bytes if snapshot else 0,
            pose_packets=pose_packets if snapshot else 0,
            coordination_bytes=result.payload_bytes,
            coordination_packets=result.logical_message_count,
            cost_bytes=phases["cost"], vote_bytes=phases["vote"],
            score_bytes=phases["vote_score_announcement"],
            commit_bytes=phases["commit"], cbaa_bid_bytes=0, cbaa_k=0,
            complete_count=result.committed_tasks,
            completion_kind="actual_reliable_commit",
            complete_all=result.full_assignment_success,
        ))
    for k in cbaa_iterations:
        result = simulate_cbaa(
            cost_matrix=cost_matrix,
            sampler=EmpiricalLatencySampler(profile, seed=seed),
            loss_sampler=BernoulliLossSampler(seed=seed),
            loss_probability=0.0, phase_timeout_ms=timeout_ms,
            max_iterations=k, capture_audit=False,
        )
        rows.append(assemble_method_row(
            method="cbaa_sync_single_assignment_K{}".format(k),
            seed=seed, robots=robots, tasks=tasks,
            task_wire_bytes=task_wire_bytes, task_packets=task_packets,
            pose_wire_bytes=0, pose_packets=0,
            coordination_bytes=result.payload_bytes,
            coordination_packets=result.logical_message_count,
            cost_bytes=0, vote_bytes=0, score_bytes=0, commit_bytes=0,
            cbaa_bid_bytes=result.payload_bytes, cbaa_k=k,
            complete_count=len(result.observer_agreed_pairs),
            completion_kind="posthoc_full_observer_agreement_not_commit",
            complete_all=result.full_observer_agreement,
        ))
    return rows


def write_e9c_evidence(
    *,
    output_root: Path, rows: list[dict[str, object]],
    git_sha: str, scenario_sha: str, dataset: Path,
    robots: int, tasks: int, seed: int, timeout_ms: float,
) -> tuple[Path, Path]:
    """One immutable actual-wire report, with full SHA/protocol provenance."""
    output_root.mkdir(parents=True, exist_ok=True)
    raw = output_root / "actual_wire_bytes.csv"
    manifest = output_root / "manifest.json"
    write_csv(raw, rows)
    manifest.write_text(json.dumps({
        "experiment": "E9C-1 physically emitted application payload from actual binary task/pose information",
        "source_git_sha": git_sha, "robots": robots, "tasks": tasks,
        "seed": seed, "loss_probability": 0.0,
        "source_scenario_cost_sha256": scenario_sha,
        "task_schema": "TASK v1 header <4sHHHHI + per-task <IddIII",
        "robot_pose_schema": "POSE v1 header <4sHHHHI + one <Idd record",
        "task_type": 0, "priority": 1, "deadline_ms": 0,
        "metadata_unused_by_original_E0_euclidean_optimizer": True,
        "max_application_packet_bytes": MAX_APPLICATION_PACKET_BYTES,
        "task_wire_header_bytes": WIRE_HEADER.size,
        "task_record_bytes": TASK_RECORD.size,
        "pose_record_bytes": ROBOT_RECORD.size,
        "task_announcer_is_external_sender_not_allocator": True,
        "each_robot_has_own_pose_locally": True,
        "other_robot_poses_are_not_free_in_paid_mode": True,
        "task_announcement_only_runs_at_zero_loss": True,
        "both_protocols_use_same_received_task_information": True,
        "democracy_original_uses_paid_remote_cost_rows": True,
        "democracy_pose_mode_bypasses_cost_exchange_only_after_paid_all_peer_poses": True,
        "cbaa_uses_local_bids_not_global_cost_matrix_exchange": True,
        "CBAA_observer_agreement_is_not_actual_commit": True,
        "phy_mac_airtime_ack_headers_contention_not_included": True,
        "network_dataset": str(dataset), "phase_timeout_ms": timeout_ms,
        "rady_source_commit": RADY_SOURCE_COMMIT,
        "rady_source_blob_sha": RADY_SOURCE_BLOB_SHA,
        "rows": len(rows), "raw_csv": str(raw),
        "raw_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return raw, manifest


def run_e9c_real_information(
    *, robots: int, tasks: int, seed: int, cbaa_iterations: tuple[int, ...],
    max_rounds: int, dataset_path: Path, output_root: Path,
    allow_download: bool = True,
) -> list[dict[str, object]]:
    """One no-loss physical-information baseline, not a multi-seed loss study."""
    validate_e9c_case(
        robots=robots, tasks=tasks, seed=seed,
        cbaa_iterations=cbaa_iterations, max_rounds=max_rounds,
    )
    prepare_e9c_evidence(output_root)
    dataset = ensure_rady_dataset(dataset_path, allow_download=allow_download)
    profile = load_rady_latency_profile(dataset)
    timeout_ms = float(summarize_latency_profile(profile)["max_ms"])
    scenario = generate_e0_scenario(seed, robots, tasks)

    task_trace = broadcast_task_information(
        task_positions=scenario.task_positions, num_robots=robots,
        sampler=EmpiricalLatencySampler(profile, seed=seed),
        loss_sampler=BernoulliLossSampler(seed=seed),
        p_loss=0.0, phase_timeout_ms=timeout_ms,
    )
    received_local_rows = reconstruct_local_cost_rows(
        local_robot_positions=scenario.robot_positions,
        announced_tasks_by_robot=task_trace.per_robot_tasks,
    )
    require_local_source_consistency(
        reconstructed=received_local_rows, expected=scenario.cost_matrix,
    )
    pose_trace = broadcast_robot_positions(
        robot_positions=scenario.robot_positions,
        sampler=EmpiricalLatencySampler(profile, seed=seed),
        loss_sampler=BernoulliLossSampler(seed=seed),
        p_loss=0.0, phase_timeout_ms=timeout_ms,
    )
    rows = run_original_methods_from_local_information(
        cost_matrix=received_local_rows,
        per_receiver_robot_positions=pose_trace.per_robot_positions,
        robots=robots, tasks=tasks, seed=seed,
        task_wire_bytes=task_trace.sender_bytes,
        task_packets=len(task_trace.events),
        pose_wire_bytes=pose_trace.sender_bytes,
        pose_packets=len(pose_trace.events),
        profile=profile, timeout_ms=timeout_ms, max_rounds=max_rounds,
        cbaa_iterations=cbaa_iterations,
    )
    scenario_sha = hashlib.sha256(repr(scenario.cost_matrix).encode()).hexdigest()
    git_sha = read_retirement_revision()
    raw, manifest = write_e9c_evidence(
        output_root=output_root, rows=rows, git_sha=git_sha,
        scenario_sha=scenario_sha, dataset=dataset,
        robots=robots, tasks=tasks, seed=seed, timeout_ms=timeout_ms,
    )
    print("E9C_SOURCE_SHA={}".format(git_sha))
    print("E9C_REAL_WIRE_RAW={}".format(raw))
    print("E9C_REAL_WIRE_MANIFEST={}".format(manifest))
    print("E9C_SHARED_TASK_PACKETS={} task_bytes={} per_task_record={} header_bytes={}".format(
        len(task_trace.events), task_trace.sender_bytes,
        TASK_RECORD.size, WIRE_HEADER.size,
    ))
    print("E9C_PEER_POSE_PACKETS={} pose_bytes={}".format(
        len(pose_trace.events), pose_trace.sender_bytes,
    ))
    for row in rows:
        print(
            "E9C_RESULT method={} task_bytes={} peer_pose_bytes={} "
            "cost_bytes={} vote_bytes={} score_bytes={} commit_bytes={} "
            "cbaa_vector_bytes={} total_sent_bytes={} "
            "confirmed_tasks={}/{} success_semantics={} full={}".format(
                row["method"], row["task_announcement_sender_bytes"],
                row["peer_robot_position_sender_bytes"],
                row["democracy_cost_rows_sender_bytes"],
                row["democracy_vote_sender_bytes"],
                row["democracy_score_sender_bytes"],
                row["democracy_commit_sender_bytes"],
                row["cbaa_bid_vector_sender_bytes"],
                row["end_to_end_sender_application_bytes"],
                row["completed_or_observer_agreed_tasks"], tasks,
                row["success_semantics"], row["full_result_of_own_semantics"],
            )
        )
    print("E9C_SCOPE=ACTUAL_BINARY_APPLICATION_BYTES_NOT_MAC_AIRTIME_OR_PACKET_LOSS")
    return rows


def parse_iterations(value: str) -> tuple[int, ...]:
    """One CLI iteration-grid parser."""
    try:
        return tuple(int(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("iterations must be comma-separated integers") from exc


def main() -> None:
    parser = argparse.ArgumentParser(
        description="E9C-1 physically transmitted TASK and POSE packet Bytes vs actual protocol traffic"
    )
    parser.add_argument("--robots", type=int, default=100)
    parser.add_argument("--tasks", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--cbaa-iterations", type=parse_iterations, default=(1, 3, 8))
    parser.add_argument("--max-rounds", type=int, default=300)
    parser.add_argument("--dataset", type=Path, default=Path(
        "data/external/rady/perama_range_testing.json"
    ))
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    run_e9c_real_information(
        robots=args.robots, tasks=args.tasks, seed=args.seed,
        cbaa_iterations=args.cbaa_iterations, max_rounds=args.max_rounds,
        dataset_path=args.dataset, output_root=args.output_root,
        allow_download=not args.no_download,
    )


if __name__ == "__main__":
    main()
