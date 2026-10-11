"""E9C-2: actual protocol SEND-payload traffic for 100 paired zero-loss E0 seeds.

One shared binary TASK dissemination per independent method trial.
Democracy: locally computed Cost row -> original Cost broadcast -> Vote/Score/Commit.
CBAA: locally computed own bid -> original repeated winning-bid/origin broadcasts.
Optional cbaa_with_raw_robot_info is an explicitly NON-STANDARD counterfactual
that also physically broadcasts every robot's own raw POSE packet. Published
CBAA does not need peer robot poses and its source-faithful row never pays it.

Source-faithful algorithm owners and existing E9C-1 remain unmodified.
The minimum K meeting post-hoc full observer agreement is an OFFLINE lower
bound only: distributed CBAA has no implemented convergence-detection stop.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
from datetime import datetime, timezone

from democracy_mrta.cbaa import simulate_cbaa
from democracy_mrta.coordination import simulate_democracy_hungarian_retirement
from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler, EmpiricalLatencySampler,
    RADY_SOURCE_BLOB_SHA, RADY_SOURCE_COMMIT,
    ensure_rady_dataset, load_rady_latency_profile, summarize_latency_profile,
)
from democracy_mrta.scenario import generate_e0_scenario
from democracy_mrta.task_information import (
    MAX_APPLICATION_PACKET_BYTES, TASK_RECORD, ROBOT_RECORD, WIRE_HEADER,
    broadcast_robot_positions, broadcast_task_information,
    reconstruct_local_cost_rows,
)
from experiments.run_e2_retirement import read_retirement_revision
from experiments.run_e9c_real_information import (
    assemble_method_row, parse_iterations,
    require_local_source_consistency, summarize_greedy_wire_phases,
)

OWNER = "experiments.run_e9c_100seed_comms"
DEFAULT_OUTPUT_ROOT = Path("results/e9c_100seed_comms")


class ConstantLatencySampler:
    """Fully specified network timing for portable zero-loss SEND-byte tests."""
    def sample_ms(self, key: str) -> float:
        return 1.0


def validate_100seed_comms_config(
    *,
    robots: int,
    tasks: int,
    seeds: int,
    first_seed: int,
    cbaa_iterations: tuple[int, ...],
    max_rounds: int,
    latency_mode: str,
) -> None:
    """One experiment data/planning boundary, no algorithm-level checks here."""
    dims = (robots, tasks, seeds, first_seed, max_rounds)
    if (any(type(item) is not int for item in dims)
        or not (1 <= tasks <= robots <= 100)
        or not (1 <= seeds <= 10000)
        or first_seed < 0 or max_rounds < tasks):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_100seed_comms_config",
            category="data", code="E9C2_INVALID_SCENARIO_GRID",
            expected="1<=tasks<=robots<=100, 1<=seeds<=10000, seed>=0, rounds>=tasks",
            actual=dims,
        ))
    if (not isinstance(cbaa_iterations, tuple)
        or not cbaa_iterations or any(type(x) is not int or x < 1 for x in cbaa_iterations)
        or tuple(sorted(set(cbaa_iterations))) != cbaa_iterations):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_100seed_comms_config",
            category="data", code="E9C2_INVALID_K_GRID",
            expected="sorted unique tuple of positive CBAA iteration integers",
            actual=cbaa_iterations,
        ))
    if latency_mode not in ("constant", "rady"):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_100seed_comms_config",
            category="planning", code="E9C2_UNKNOWN_LATENCY_MODE",
            expected="constant or rady", actual=latency_mode,
        ))


def prepare_100seed_comms_output(root: Path) -> None:
    """Do not rewrite old E0-E9C experiment evidence or existing result directories."""
    resolved, results = root.resolve(), Path("results").resolve()
    if (resolved == results or resolved in results.parents
        or (resolved.is_relative_to(results)
            and not resolved.relative_to(results).parts[0].startswith("e9c_"))):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="prepare_100seed_comms_output",
            category="state", code="E9C2_PROTECTED_OUTPUT_ROOT",
            expected="fresh results/e9c_* root or dedicated external output path",
            actual=str(root),
        ))
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="prepare_100seed_comms_output",
            category="state", code="E9C2_OUTPUT_EXISTS",
            expected="nonexistent/empty evidence root", actual=str(root),
        ))


def select_network_sampler(*, latency_mode: str, dataset: Path, allow_download: bool):
    """Network dependency owner: either pinned empirical Rady or explicit fixed 1ms."""
    if latency_mode == "constant":
        return None, 10.0, "deterministic_constant_1ms; deadline_10ms"
    path = ensure_rady_dataset(dataset, allow_download=allow_download)
    profile = load_rady_latency_profile(path)
    timeout = float(summarize_latency_profile(profile)["max_ms"])
    return profile, timeout, str(path)


def create_seed_sampler(*, profile, seed: int):
    """Each independent method gets a fresh seed-bound original latency sampler."""
    return ConstantLatencySampler() if profile is None else EmpiricalLatencySampler(profile, seed=seed)


def capture_seed_information(
    *,
    seed: int, robots: int, tasks: int, profile, timeout_ms: float,
    include_raw_robot_info: bool,
):
    """One physically serialized common task source; local rows not an oracle."""
    scenario = generate_e0_scenario(seed, robots, tasks)
    task_trace = broadcast_task_information(
        task_positions=scenario.task_positions, num_robots=robots,
        sampler=create_seed_sampler(profile=profile, seed=seed),
        loss_sampler=BernoulliLossSampler(seed=seed), p_loss=0.0,
        phase_timeout_ms=timeout_ms,
    )
    local_cost_rows = reconstruct_local_cost_rows(
        local_robot_positions=scenario.robot_positions,
        announced_tasks_by_robot=task_trace.per_robot_tasks,
    )
    require_local_source_consistency(
        reconstructed=local_cost_rows, expected=scenario.cost_matrix,
    )
    pose_trace = (
        broadcast_robot_positions(
            robot_positions=scenario.robot_positions,
            sampler=create_seed_sampler(profile=profile, seed=seed),
            loss_sampler=BernoulliLossSampler(seed=seed),
            p_loss=0.0, phase_timeout_ms=timeout_ms,
        )
        if include_raw_robot_info else None
    )
    return scenario, local_cost_rows, task_trace, pose_trace


def run_democracy_100seed_case(
    *,
    cost_rows, task_trace, seed: int, robots: int, tasks: int,
    profile, timeout_ms: float, max_rounds: int,
) -> dict[str, object]:
    """Original Greedy pure quarter-plurality actor, never another voting engine."""
    result = simulate_democracy_hungarian_retirement(
        cost_matrix=cost_rows,
        sampler=create_seed_sampler(profile=profile, seed=seed),
        loss_sampler=BernoulliLossSampler(seed=seed),
        p_loss=0.0, p_vote_loss=0.0,
        phase_timeout_ms=timeout_ms, max_rounds=max_rounds,
        voting_strategy="greedy_task",
        vote_decision_rule="quarter_plurality", vote_repetitions=1,
    )
    phase = summarize_greedy_wire_phases(result)
    row = assemble_method_row(
        method="democracy_task_cost_vote",
        seed=seed, robots=robots, tasks=tasks,
        task_wire_bytes=task_trace.sender_bytes,
        task_packets=len(task_trace.events),
        pose_wire_bytes=0, pose_packets=0,
        coordination_bytes=result.payload_bytes,
        coordination_packets=result.logical_message_count,
        cost_bytes=phase["cost"], vote_bytes=phase["vote"],
        score_bytes=phase["vote_score_announcement"],
        commit_bytes=phase["commit"], cbaa_bid_bytes=0, cbaa_k=0,
        complete_count=result.committed_tasks,
        completion_kind="actual_reliable_commit",
        complete_all=result.full_assignment_success,
    )
    row["reference_scenario_source"] = "locally_decoded_task_records_plus_own_pose"
    row["raw_robot_info_extra_not_standard_cbaa"] = 0
    row["electoral_attempts"] = len(result.rounds)
    return row


def run_cbaa_100seed_cases(
    *,
    cost_rows, task_trace, pose_trace, seed: int,
    robots: int, tasks: int, profile, timeout_ms: float,
    cbaa_iterations: tuple[int, ...],
    include_raw_robot_info: bool,
) -> list[dict[str, object]]:
    """Run published-family CBAA K times; optional robot-POSE stage is ablation."""
    rows: list[dict[str, object]] = []
    for k in cbaa_iterations:
        result = simulate_cbaa(
            cost_matrix=cost_rows,
            sampler=create_seed_sampler(profile=profile, seed=seed),
            loss_sampler=BernoulliLossSampler(seed=seed),
            loss_probability=0.0, phase_timeout_ms=timeout_ms,
            max_iterations=k, capture_audit=False,
        )
        for raw_robots in ((False, True) if include_raw_robot_info else (False,)):
            if raw_robots and pose_trace is None:
                raise ProtocolError(Diagnostic(
                    owner=OWNER, function="run_cbaa_100seed_cases",
                    category="dependency", code="E9C2_ROBOT_INFO_NOT_TRANSMITTED",
                    expected="physically received POSE packets", actual=None,
                ))
            row = assemble_method_row(
                method=("cbaa_raw_robot_information_K{}".format(k)
                        if raw_robots else "cbaa_original_local_bid_K{}".format(k)),
                seed=seed, robots=robots, tasks=tasks,
                task_wire_bytes=task_trace.sender_bytes,
                task_packets=len(task_trace.events),
                pose_wire_bytes=pose_trace.sender_bytes if raw_robots else 0,
                pose_packets=len(pose_trace.events) if raw_robots else 0,
                coordination_bytes=result.payload_bytes,
                coordination_packets=result.logical_message_count,
                cost_bytes=0, vote_bytes=0, score_bytes=0, commit_bytes=0,
                cbaa_bid_bytes=result.payload_bytes, cbaa_k=k,
                complete_count=len(result.observer_agreed_pairs),
                completion_kind="posthoc_observer_unanimity_not_distributed_commit",
                complete_all=result.full_observer_agreement,
            )
            row["reference_scenario_source"] = "locally_decoded_task_records_plus_own_pose"
            row["raw_robot_info_extra_not_standard_cbaa"] = int(raw_robots)
            row["electoral_attempts"] = 0
            rows.append(row)
    return rows


def require_complete_seed_pairing(
    *,
    rows: list[dict[str, object]], seed: int, tasks: int,
    k_grid: tuple[int, ...], include_raw_robot_info: bool,
) -> None:
    """One contract check: every requested actor outcome is preserved, even failures."""
    expected = 1 + len(k_grid) * (2 if include_raw_robot_info else 1)
    observed_methods = [str(row["method"]) for row in rows]
    if (len(rows) != expected or len(set(observed_methods)) != expected
        or any(row["seed"] != seed for row in rows)
        or any(int(row["completed_or_observer_agreed_tasks"]) > tasks for row in rows)
        or any(int(row["full_result_of_own_semantics"])
               != int(int(row["completed_or_observer_agreed_tasks"]) == tasks)
               for row in rows)):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="require_complete_seed_pairing",
            category="contract", code="E9C2_PAIRED_OUTCOME_COVERAGE",
            expected={"seed": seed, "methods": expected, "tasks": tasks},
            actual={"methods": observed_methods,
                    "task_counts": [row["completed_or_observer_agreed_tasks"] for row in rows]},
        ))


def summarize_100seed_conditions(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """All seeds in denominator, separate actual Commit and observer agreement."""
    conditions: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        conditions.setdefault(str(row["method"]), []).append(row)
    output: list[dict[str, object]] = []
    for method, bucket in sorted(conditions.items()):
        bytes_series = [int(row["end_to_end_sender_application_bytes"]) for row in bucket]
        completed = [int(row["full_result_of_own_semantics"]) for row in bucket]
        confirmed = [int(row["completed_or_observer_agreed_tasks"]) for row in bucket]
        complete_bytes = [value for value, success in zip(bytes_series, completed) if success]
        output.append({
            "method": method, "seeds": len(bucket),
            "full_result_count": sum(completed),
            "full_result_rate": sum(completed)/len(bucket),
            "mean_confirmed_tasks": statistics.mean(confirmed),
            "mean_sender_bytes_all_seeds": statistics.mean(bytes_series),
            "min_sender_bytes_all_seeds": min(bytes_series),
            "max_sender_bytes_all_seeds": max(bytes_series),
            "mean_sender_bytes_full_result_only": (
                statistics.mean(complete_bytes) if complete_bytes else ""
            ),
            "success_semantics": bucket[0]["success_semantics"],
            "cbaa_iterations": bucket[0]["cbaa_iterations"],
            "is_nonstandard_raw_robot_information_ablation": int(
                bucket[0]["raw_robot_info_extra_not_standard_cbaa"]
            ),
        })
    return output


def calculate_offline_minimum_k(
    *,
    rows: list[dict[str, object]], cbaa_iterations: tuple[int, ...],
    include_raw_robot_info: bool,
) -> list[dict[str, object]]:
    """Only EXTERNAL post-hoc lower bound, NEVER feedback to a robot or CBAA."""
    by_seed: dict[int, list[dict[str, object]]] = {}
    for row in rows:
        by_seed.setdefault(int(row["seed"]), []).append(row)
    output = []
    for seed, trial in sorted(by_seed.items()):
        democracy = next(x for x in trial if x["method"] == "democracy_task_cost_vote")
        cbaa = [
            x for x in trial
            if str(x["method"]).startswith("cbaa_original_local_bid_K")
            and int(x["full_result_of_own_semantics"])
        ]
        best = min(cbaa, key=lambda x: int(x["cbaa_iterations"])) if cbaa else None
        democracy_bytes = int(democracy["end_to_end_sender_application_bytes"])
        min_bytes = int(best["end_to_end_sender_application_bytes"]) if best else None
        output.append({
            "seed": seed,
            "democracy_actual_commit_full": democracy["full_result_of_own_semantics"],
            "democracy_actual_sender_bytes": democracy_bytes,
            "offline_cbaa_first_full_K": int(best["cbaa_iterations"]) if best else "",
            "offline_cbaa_sender_bytes_at_first_full": min_bytes if min_bytes is not None else "",
            "offline_cbaa_raw_robot_sender_bytes_at_first_full": (
                min_bytes + 36 * int(democracy["robots"])
                if min_bytes is not None and include_raw_robot_info else ""
            ),
            "democracy_minus_offline_cbaa_bytes": (
                democracy_bytes - min_bytes if min_bytes is not None else ""
            ),
            "offline_oracle_cannot_stop_distributed_algorithm": 1,
        })
    return output


def summarize_offline_paired_comparison(rows: list[dict[str, object]]) -> dict[str, object]:
    """Paired lower-bound difference; no unsuccessful CBAA seed is dropped silently."""
    complete = [
        row for row in rows if row["offline_cbaa_sender_bytes_at_first_full"] != ""
    ]
    differences = [int(row["democracy_minus_offline_cbaa_bytes"]) for row in complete]
    k_values = [int(row["offline_cbaa_first_full_K"]) for row in complete]
    count = len(complete)
    return {
        "paired_all_seed_count": len(rows),
        "cbaa_full_achieved_within_requested_K_grid_count": count,
        "cbaa_not_full_within_grid_count": len(rows)-count,
        "mean_democracy_minus_offline_cbaa_sender_bytes_when_full": (
            statistics.mean(differences) if differences else None
        ),
        "mean_democracy_saving_percent_vs_offline_cbaa_when_full": (
            statistics.mean([
                -100.0 * int(row["democracy_minus_offline_cbaa_bytes"])
                / int(row["offline_cbaa_sender_bytes_at_first_full"])
                for row in complete
            ]) if complete else None
        ),
        "cbaa_first_full_K_distribution": {
            str(k): sum(v == k for v in k_values)
            for k in sorted(set(k_values))
        },
        "interpretation": "Offline K lower bound only; CBAA no decentralized stop-detection or final Commit",
    }


def write_100seed_comms_evidence(
    *,
    root: Path, raw_partial: Path, rows: list[dict[str, object]],
    robots: int, tasks: int, seeds: int, first_seed: int, k_grid: tuple[int, ...],
    max_rounds: int, latency_mode: str, latency_detail: str,
    include_raw_robot_info: bool, source_sha: str,
) -> tuple[Path, Path, Path, Path]:
    """Atomic raw finalization, summary, paired offline bound, SHA256 manifest."""
    raw = root / "per_seed_method_bytes.csv"
    os.replace(raw_partial, raw)
    summary = root / "summary.csv"
    paired = root / "offline_min_cbaa_k_per_seed.csv"
    manifest = root / "manifest.json"
    summary_rows = summarize_100seed_conditions(rows)
    paired_rows = calculate_offline_minimum_k(
        rows=rows, cbaa_iterations=k_grid,
        include_raw_robot_info=include_raw_robot_info,
    )
    for path, records in ((summary, summary_rows), (paired, paired_rows)):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    manifest.write_text(json.dumps({
        "experiment": "E9C-2 100-seed zero-loss original Democracy Cost/Vote vs source-faithful CBAA",
        "git_sha": source_sha, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "robots": robots, "tasks": tasks, "seeds": seeds, "first_seed": first_seed,
        "cbaa_iterations_grid": list(k_grid), "greedy_max_rounds": max_rounds,
        "loss_probability": 0.0, "latency_mode": latency_mode,
        "latency_detail": latency_detail,
        "network_source_commit_when_rady": RADY_SOURCE_COMMIT if latency_mode=="rady" else None,
        "network_source_blob_sha_when_rady": RADY_SOURCE_BLOB_SHA if latency_mode=="rady" else None,
        "information": {
            "task_data": "same real decoded binary TASK announcements for every method",
            "task_header_struct": "<4sHHHHI", "task_record_struct": "<IddIII",
            "task_record_bytes": TASK_RECORD.size,
            "pose_record_struct": "<Idd", "pose_record_bytes": ROBOT_RECORD.size,
            "header_bytes": WIRE_HEADER.size,
            "max_application_packet_bytes": MAX_APPLICATION_PACKET_BYTES,
            "robot_fields": ["robot_id", "x", "y"],
            "each_robot_locally_knows_own_pose": True,
            "cost_calculated_locally_from_decoded_task_and_own_pose": True,
        },
        "methods": {
            "democracy_task_cost_vote": "original Cost broadcast once, real Vote/Score/Commit SENDs",
            "cbaa_original_local_bid_K": "published-family CBAA own cost and full bid/winner vectors",
            "cbaa_raw_robot_information_K": "nonstandard physically paid extra all-robot POSE stage",
        },
        "include_raw_robot_info_ablation": include_raw_robot_info,
        "cbaa_no_decentralized_stop": True,
        "cbaa_no_final_commit": True,
        "offline_minimum_K_is_not_runtime_stopping": True,
        "disagreement_and_partial_outcomes_not_excluded": True,
        "original_cost_vote_and_cbaa_vectors_use_existing_event_payload_sizes": True,
        "task_and_raw_robot_pose_physically_binary_encoded": True,
        "not_full_ip_mac_phy_airtime": True,
        "byte_accounting": "sender application payload per actual physical SEND, multicast counted once",
        "all_rows": len(rows),
        "expected_rows": seeds * (1 + len(k_grid) * (2 if include_raw_robot_info else 1)),
        "paired_offline_lower_bound": summarize_offline_paired_comparison(paired_rows),
        "sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (raw, summary, paired)
        },
    }, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    return raw, summary, paired, manifest


def run_e9c_100seed_comms(
    *,
    robots: int=100, tasks: int=50, seeds: int=100, first_seed: int=0,
    cbaa_iterations: tuple[int, ...]=(1, 2, 3, 4, 5, 6, 8),
    max_rounds: int=300, latency_mode: str="constant",
    dataset_path: Path=Path("data/external/rady/perama_range_testing.json"),
    include_raw_robot_info: bool=True,
    output_root: Path=DEFAULT_OUTPUT_ROOT,
    allow_download: bool=True,
) -> list[dict[str, object]]:
    """Independent replayable paired seeds, with flushed partial raw evidence."""
    validate_100seed_comms_config(
        robots=robots, tasks=tasks, seeds=seeds, first_seed=first_seed,
        cbaa_iterations=cbaa_iterations, max_rounds=max_rounds,
        latency_mode=latency_mode,
    )
    prepare_100seed_comms_output(output_root)
    profile, timeout_ms, latency_detail = select_network_sampler(
        latency_mode=latency_mode, dataset=dataset_path, allow_download=allow_download,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    raw_partial = output_root / "per_seed_method_bytes.partial.csv"
    rows: list[dict[str, object]] = []
    with raw_partial.open("w", encoding="utf-8", newline="") as handle:
        writer = None
        for index in range(seeds):
            seed = first_seed+index
            _scenario, local_costs, task_trace, pose_trace = capture_seed_information(
                seed=seed, robots=robots, tasks=tasks, profile=profile,
                timeout_ms=timeout_ms, include_raw_robot_info=include_raw_robot_info,
            )
            current = [run_democracy_100seed_case(
                cost_rows=local_costs, task_trace=task_trace, seed=seed,
                robots=robots, tasks=tasks, profile=profile,
                timeout_ms=timeout_ms, max_rounds=max_rounds,
            )]
            current.extend(run_cbaa_100seed_cases(
                cost_rows=local_costs, task_trace=task_trace,
                pose_trace=pose_trace, seed=seed,
                robots=robots, tasks=tasks, profile=profile,
                timeout_ms=timeout_ms, cbaa_iterations=cbaa_iterations,
                include_raw_robot_info=include_raw_robot_info,
            ))
            require_complete_seed_pairing(
                rows=current, seed=seed, tasks=tasks, k_grid=cbaa_iterations,
                include_raw_robot_info=include_raw_robot_info,
            )
            if writer is None:
                writer = csv.DictWriter(handle, fieldnames=list(current[0]))
                writer.writeheader()
            for row in current:
                writer.writerow(row)
            handle.flush()
            rows.extend(current)
            if (index+1) % 10 == 0 or index+1 == seeds:
                print("E9C2_PROGRESS completed_seeds={}/{} source_sha={}".format(
                    index+1, seeds, read_retirement_revision()
                ), flush=True)
    source_sha = read_retirement_revision()
    raw, summary, paired, manifest = write_100seed_comms_evidence(
        root=output_root, raw_partial=raw_partial, rows=rows,
        robots=robots, tasks=tasks, seeds=seeds, first_seed=first_seed,
        k_grid=cbaa_iterations, max_rounds=max_rounds,
        latency_mode=latency_mode, latency_detail=latency_detail,
        include_raw_robot_info=include_raw_robot_info, source_sha=source_sha,
    )
    for row in summarize_100seed_conditions(rows):
        print("E9C2_RESULT method={} seeds={} full={} mean_tasks={:.4f} "
              "mean_sender_bytes={:.2f} complete_mean_sender_bytes={}".format(
                  row["method"], row["seeds"],
                  row["full_result_count"], row["mean_confirmed_tasks"],
                  row["mean_sender_bytes_all_seeds"],
                  row["mean_sender_bytes_full_result_only"],
              ), flush=True)
    lb = summarize_offline_paired_comparison(calculate_offline_minimum_k(
        rows=rows, cbaa_iterations=cbaa_iterations,
        include_raw_robot_info=include_raw_robot_info,
    ))
    print("E9C2_OFFLINE_K_BOUND="+json.dumps(lb, sort_keys=True), flush=True)
    print("E9C2_RAW={}\nE9C2_SUMMARY={}\nE9C2_PAIRED={}\nE9C2_MANIFEST={}".format(
        raw, summary, paired, manifest
    ), flush=True)
    print("E9C2_INTERPRETATION=OBSERVED_SEND_APPLICATION_BYTES_NOT_MAC_AIRTIME; "
          "POSTHOC_CBAA_AGREEMENT_NOT_COMMIT; OFFLINE_MIN_K_NOT_REAL_STOP",
          flush=True)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="E9C-2 paired 100-seed end-to-end SEND-byte benchmarking")
    parser.add_argument("--robots", type=int, default=100)
    parser.add_argument("--tasks", type=int, default=50)
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--first-seed", type=int, default=0)
    parser.add_argument("--cbaa-iterations", type=parse_iterations,
                        default=(1,2,3,4,5,6,8))
    parser.add_argument("--max-rounds", type=int, default=300)
    parser.add_argument("--latency-mode", choices=("constant","rady"), default="constant")
    parser.add_argument("--dataset", type=Path, default=Path("data/external/rady/perama_range_testing.json"))
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--no-cbaa-raw-robot-info", action="store_true")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args=parser.parse_args()
    run_e9c_100seed_comms(
        robots=args.robots, tasks=args.tasks, seeds=args.seeds,
        first_seed=args.first_seed, cbaa_iterations=args.cbaa_iterations,
        max_rounds=args.max_rounds, latency_mode=args.latency_mode,
        dataset_path=args.dataset, allow_download=not args.no_download,
        include_raw_robot_info=not args.no_cbaa_raw_robot_info,
        output_root=args.output_root,
    )


if __name__=="__main__":
    main()
