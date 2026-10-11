"""Reproducible, separate E8 CBAA single-assignment packet-loss smoke benchmark.

CBAA uses its own auction/consensus, NOT our vote, Greedy task scheduler,
reliable qualified-score announcement, or a central commit. Global consistency
is assessed AFTER the run for evaluation only, never fed into the algorithm.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path
import statistics

from democracy_mrta.cbaa import CBAAResult, simulate_cbaa
from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler,
    EmpiricalLatencySampler,
    RADY_SOURCE_BLOB_SHA,
    RADY_SOURCE_COMMIT,
    ensure_rady_dataset,
    load_rady_latency_profile,
    summarize_latency_profile,
    validate_packet_loss_probability,
)
from democracy_mrta.optimizer import solve_sequential_greedy_reference
from democracy_mrta.scenario import generate_e0_scenario
from experiments.run_e2 import parse_probabilities, write_csv
from experiments.run_e2_retirement import read_retirement_revision


OWNER = "experiments.run_cbaa_baseline"
DEFAULT_LOSSES = (0.0, 0.30, 0.50)
DEFAULT_OUTPUT_ROOT = Path("results/e8_cbaa_single_assignment_smoke")


def validate_cbaa_benchmark_axes(
    *,
    robots: int,
    tasks: int,
    seeds: int,
    max_iterations: int,
    loss_probabilities: tuple[float, ...],
) -> None:
    """Validate the paired fixed-budget experimental grid, independently of CBAA."""
    if (
        type(robots) is not int or type(tasks) is not int
        or type(seeds) is not int or type(max_iterations) is not int
        or not 1 <= tasks <= robots <= 100
        or seeds < 1 or max_iterations < 1
    ):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_cbaa_benchmark_axes",
            category="data", code="INVALID_CBAA_BENCHMARK_AXES",
            expected="1 <= T <= R <= 100; seeds >= 1; max_iterations >= 1, all integers",
            actual=(robots, tasks, seeds, max_iterations),
        ))
    if (
        not loss_probabilities
        or tuple(sorted(set(loss_probabilities))) != loss_probabilities
    ):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_cbaa_benchmark_axes",
            category="data", code="INVALID_CBAA_LOSS_AXIS",
            expected="nonempty strictly ascending unique probabilities in [0,1]",
            actual=loss_probabilities,
        ))
    for loss in loss_probabilities:
        validate_packet_loss_probability(loss)


def prepare_cbaa_output(output_root: Path) -> None:
    """Never overwrite previous empirical baselines, including repeated-Vote raw."""
    root = output_root.resolve()
    protected = tuple(Path(name).resolve() for name in (
        "results/e2_joint_loss_diagonal_100r50t",
        "results/e2_greedy_quarter_plurality_no_fallback_100r50t",
        "results/e2_greedy_quarter_plurality_100r50t",
        "results/e2_repeat2_majority_100r50t",
        "results/e2_repeat3_majority_100r50t",
        "results/e3_e4_scaling_100robot_cap",
    ))
    if any(root == other or root in other.parents or other in root.parents
           for other in protected):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="prepare_cbaa_output", category="state",
            code="CBAA_OUTPUT_SOURCE_COLLISION",
            expected="new separate E8 directory outside all immutable historical result roots",
            actual=str(output_root),
        ))
    if output_root.exists() and (
        not output_root.is_dir()
        or any(file.name != "README.md" for file in output_root.iterdir())
    ):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="prepare_cbaa_output", category="state",
            code="CBAA_OUTPUT_ALREADY_EXISTS",
            expected="new or README-only output root",
            actual=str(output_root),
        ))
    output_root.mkdir(parents=True, exist_ok=True)


def cbaa_result_row(
    *,
    seed: int,
    robots: int,
    tasks: int,
    loss: float,
    max_iterations: int,
    phase_timeout_ms: float,
    greedy_reference_cost: float,
    result: CBAAResult,
    git_sha: str,
    timestamp: str,
) -> dict[str, object]:
    """An external observer reports agreement, never an invented actual Commit."""
    full = result.full_observer_agreement
    # Full-batch cost belongs to cbaa_full_batch_cost and is NaN if incomplete.
    return {
        "timestamp_utc": timestamp,
        "git_sha": git_sha,
        "method": result.method,
        "score_rule": "1/(1+nonnegative_cost)",
        "communication": "synchronous_complete_graph_broadcast",
        "termination": "fixed_iterations_no_global_stop_signal",
        "seed": seed,
        "robots": robots,
        "tasks": tasks,
        "p_consensus_loss": loss,
        "max_iterations": max_iterations,
        "phase_timeout_ms": phase_timeout_ms,
        "iterations": result.iterations,
        "local_claim_count": len(result.local_claims),
        "local_duplicate_claim_task_count": len(result.conflicting_task_ids),
        "observer_agreed_task_count": len(result.observer_agreed_pairs),
        "observer_unconfirmed_task_count": len(result.unconfirmed_task_ids),
        "task_agreement_rate": result.task_agreement_rate,
        "full_observer_agreement": int(full),
        "greedy_reference_cost": greedy_reference_cost,
        "elapsed_ms": result.elapsed_ms,
        "logical_message_count": result.logical_message_count,
        "payload_bytes": result.payload_bytes,
        "delivery_attempts": result.delivery_attempts,
        "delivery_drops": result.delivery_drops,
        "late_deliveries": result.late_deliveries,
        "observed_packet_loss": (
            result.delivery_drops / result.delivery_attempts
            if result.delivery_attempts else float("nan")
        ),
        "observer_agreed_pairs": repr(result.observer_agreed_pairs),
        "raw_local_claims": repr(result.local_claims),
        "conflicting_task_ids": repr(result.conflicting_task_ids),
        "unconfirmed_task_ids": repr(result.unconfirmed_task_ids),
    }


def cbaa_full_batch_cost(
    *,
    cost_matrix: tuple[tuple[float, ...], ...],
    result: CBAAResult,
) -> float:
    """External evaluation cost only if every task's local beliefs agree."""
    if not result.full_observer_agreement:
        return float("nan")
    return float(sum(cost_matrix[r][task] for r, task in result.observer_agreed_pairs))


def summarize_cbaa_conditions(
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Keep unfinished/conflicted runs in success, not in full-set cost means."""
    summary: list[dict[str, object]] = []
    for loss in sorted({float(row["p_consensus_loss"]) for row in rows}):
        selected = [r for r in rows if r["p_consensus_loss"] == loss]
        completes = [r for r in selected if r["full_observer_agreement"] == 1]
        mean = lambda key: statistics.fmean(float(r[key]) for r in selected)
        physical = sum(int(r["delivery_attempts"]) for r in selected)
        drops = sum(int(r["delivery_drops"]) for r in selected)
        summary.append({
            "method": selected[0]["method"],
            "robots": selected[0]["robots"],
            "tasks": selected[0]["tasks"],
            "seeds": len(selected),
            "max_iterations": selected[0]["max_iterations"],
            "p_consensus_loss": loss,
            "full_observer_agreement_rate": mean("full_observer_agreement"),
            "complete_case_cost_count": len(completes),
            "mean_full_batch_cost_complete_only": (
                statistics.fmean(float(r["full_batch_cost_complete_only"]) for r in completes)
                if completes else float("nan")
            ),
            "mean_cost_change_vs_sequential_greedy_pct_complete_only": (
                statistics.fmean(float(r["cost_change_vs_sequential_greedy_pct_complete_only"])
                                for r in completes)
                if completes else float("nan")
            ),
            "mean_task_agreement_rate": mean("task_agreement_rate"),
            "mean_unconfirmed_task_count": mean("observer_unconfirmed_task_count"),
            "mean_duplicate_claim_task_count": mean("local_duplicate_claim_task_count"),
            "mean_local_claim_count": mean("local_claim_count"),
            "mean_elapsed_ms": mean("elapsed_ms"),
            "mean_logical_message_count": mean("logical_message_count"),
            "mean_payload_bytes": mean("payload_bytes"),
            "mean_delivery_attempts": mean("delivery_attempts"),
            "mean_late_deliveries": mean("late_deliveries"),
            "observed_packet_loss": drops / physical if physical else float("nan"),
        })
    return summary


def write_cbaa_seed_zero_audit(
    writer: csv.DictWriter,
    *,
    seed: int,
    loss: float,
    result: CBAAResult,
) -> None:
    """Physical broadcast and per-receiver delivery audit; no fabricated Commit."""
    for event in result.audit_events:
        writer.writerow({
            "kind": "broadcast",
            "seed": seed,
            "p_consensus_loss": loss,
            "iteration": event.round_id,
            "phase": event.phase,
            "sender_id": event.sender_id,
            "receiver_id": event.receiver_id,
            "delivered": "",
            "send_ms": event.send_time_ms,
            "arrival_ms": event.arrival_time_ms,
            "payload_bytes": event.payload_bytes,
        })
    for observation in result.audit_deliveries:
        writer.writerow({
            "kind": "delivery",
            "seed": seed,
            "p_consensus_loss": loss,
            "iteration": observation.round_id,
            "phase": observation.phase,
            "sender_id": observation.sender_id,
            "receiver_id": observation.receiver_id,
            "delivered": int(observation.delivered),
            "send_ms": "",
            "arrival_ms": observation.arrival_time_ms if observation.delivered else "",
            "payload_bytes": "",
        })
    for state in result.states:
        writer.writerow({
            "kind": "final_local_state",
            "seed": seed,
            "p_consensus_loss": loss,
            "iteration": result.iterations,
            "phase": "local_observation",
            "sender_id": state.robot_id,
            "receiver_id": state.robot_id,
            "assigned_task": state.assigned_task if state.assigned_task is not None else "",
            "winning_bids": repr(state.winning_bids),
            "winning_robots": repr(state.winning_robots),
        })


def run_cbaa_baseline(
    *,
    robots: int,
    tasks: int,
    seeds: int,
    loss_probabilities: tuple[float, ...],
    max_iterations: int,
    dataset_path: Path,
    output_root: Path,
    allow_download: bool = True,
) -> list[dict[str, object]]:
    """One independent CBAA experiment owner; no call into Greedy vote engine."""
    validate_cbaa_benchmark_axes(
        robots=robots, tasks=tasks, seeds=seeds,
        max_iterations=max_iterations,
        loss_probabilities=loss_probabilities,
    )
    prepare_cbaa_output(output_root)
    dataset = ensure_rady_dataset(dataset_path, allow_download=allow_download)
    profile = load_rady_latency_profile(dataset)
    phase_timeout_ms = float(summarize_latency_profile(profile)["max_ms"])
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    sha = read_retirement_revision()
    raw_rows: list[dict[str, object]] = []
    audit_path = output_root / "events" / f"cbaa_audit_{timestamp}.csv.gz"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(audit_path, "wt", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "kind", "seed", "p_consensus_loss", "iteration", "phase",
            "sender_id", "receiver_id", "delivered", "send_ms", "arrival_ms",
            "payload_bytes", "assigned_task", "winning_bids", "winning_robots",
        ])
        writer.writeheader()
        for seed in range(seeds):
            scenario = generate_e0_scenario(seed, robots, tasks)
            greedy_reference = solve_sequential_greedy_reference(scenario.cost_matrix)
            for loss in loss_probabilities:
                result = simulate_cbaa(
                    cost_matrix=scenario.cost_matrix,
                    sampler=EmpiricalLatencySampler(profile, seed=seed),
                    loss_sampler=BernoulliLossSampler(seed=seed),
                    loss_probability=loss,
                    phase_timeout_ms=phase_timeout_ms,
                    max_iterations=max_iterations,
                    capture_audit=seed == 0,
                )
                row = cbaa_result_row(
                    seed=seed, robots=robots, tasks=tasks, loss=loss,
                    max_iterations=max_iterations,
                    phase_timeout_ms=phase_timeout_ms,
                    greedy_reference_cost=greedy_reference.total_cost,
                    result=result, git_sha=sha, timestamp=timestamp,
                )
                row["full_batch_cost_complete_only"] = cbaa_full_batch_cost(
                    cost_matrix=scenario.cost_matrix, result=result,
                )
                row["cost_change_vs_sequential_greedy_pct_complete_only"] = (
                    100 * (row["full_batch_cost_complete_only"] /
                           greedy_reference.total_cost - 1)
                    if result.full_observer_agreement else float("nan")
                )
                raw_rows.append(row)
                if seed == 0:
                    write_cbaa_seed_zero_audit(
                        writer, seed=seed, loss=loss, result=result,
                    )
            if (seed + 1) % 10 == 0 or seed + 1 == seeds:
                print(f"CBAA_PROGRESS seeds={seed + 1}/{seeds}", flush=True)

    raw_path = output_root / "raw" / f"cbaa_{timestamp}.csv"
    write_csv(raw_path, raw_rows)
    summary = summarize_cbaa_conditions(raw_rows)
    summary_path = output_root / "summary.csv"
    write_csv(summary_path, summary)
    (output_root / "manifest.json").write_text(
        json.dumps({
            "method": "cbaa_sync_single_assignment",
            "research_source_doi": "10.1109/TRO.2009.2022423",
            "implementation": "single-assignment phase1 auction + phase2 bid max-consensus",
            "adaptations": [
                "score=1/(1+cost), not a normalized global objective",
                "origin-ID piggyback for deterministic ties and stable propagation",
                "synchronous complete-graph repeated broadcasts with fixed iteration budget",
                "observer agreement is post-hoc evaluation, NOT a distributed Commit",
                "each CBAA consensus packet has one Bernoulli loss stage, not Cost+Vote",
            ],
            "source_git_sha": sha,
            "utc": timestamp,
            "robots": robots, "tasks": tasks, "seeds": seeds,
            "loss_probabilities": list(loss_probabilities),
            "max_iterations": max_iterations,
            "phase_timeout_ms": phase_timeout_ms,
            "network_dataset_source_commit": RADY_SOURCE_COMMIT,
            "network_dataset_source_blob_sha": RADY_SOURCE_BLOB_SHA,
            "raw_path": str(raw_path), "audit_path": str(audit_path),
            "latency_model": "one empirical delay per broadcast, independent receiver loss",
            "full_cost_rule": "NaN for any non-fully-agreed batch",
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    print(f"CBAA_METHOD=cbaa_sync_single_assignment")
    print(f"CBAA_HEAD={sha}")
    print(f"CBAA_RAW={raw_path}")
    print(f"CBAA_AUDIT={audit_path}")
    print(f"CBAA_SUMMARY={summary_path}")
    for row in summary:
        print(
            "CBAA_RESULT "
            f"robots={robots} tasks={tasks} p_loss={row['p_consensus_loss']:.2f} "
            f"full_agreement={row['full_observer_agreement_rate']:.4f} "
            f"task_agreement={row['mean_task_agreement_rate']:.4f} "
            f"duplicate_claims={row['mean_duplicate_claim_task_count']:.2f} "
            f"unconfirmed={row['mean_unconfirmed_task_count']:.2f} "
            f"bytes={row['mean_payload_bytes']:.0f} "
            f"elapsed_ms={row['mean_elapsed_ms']:.2f}"
        )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Independent CBAA synchronous auction/consensus benchmark (no reliable Commit)"
    )
    parser.add_argument("--robots", type=int, default=10)
    parser.add_argument("--tasks", type=int, default=5)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--loss-probabilities", type=parse_probabilities,
                        default=DEFAULT_LOSSES)
    parser.add_argument("--max-iterations", type=int, default=20)
    parser.add_argument("--dataset", type=Path, default=Path(
        "data/external/rady/perama_range_testing.json"
    ))
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    run_cbaa_baseline(
        robots=args.robots, tasks=args.tasks, seeds=args.seeds,
        loss_probabilities=args.loss_probabilities,
        max_iterations=args.max_iterations,
        dataset_path=args.dataset,
        output_root=args.output_root,
        allow_download=not args.no_download,
    )


if __name__ == "__main__":
    main()
