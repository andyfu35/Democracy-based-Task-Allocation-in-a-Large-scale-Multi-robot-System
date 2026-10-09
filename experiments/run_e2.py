from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import gzip
import math
from pathlib import Path
import statistics

from democracy_mrta.coordination import (
    LossyCoordinationResult,
    simulate_democracy_hungarian_lossy,
    simulate_full_view_hungarian_lossy,
    simulate_ideal_full_information_lossy_reference,
    simulate_leader_hungarian_lossy,
)
from democracy_mrta.metrics import (
    evaluate_assignment_correctness,
    optimality_gap_percent,
)
from democracy_mrta.network import (
    BernoulliLossSampler,
    EmpiricalLatencySampler,
    ensure_rady_dataset,
    load_rady_latency_profile,
    percentile,
    summarize_latency_profile,
)
from democracy_mrta.optimizer import solve_hungarian_assignment
from democracy_mrta.scenario import generate_e0_scenario


DEFAULT_CONDITIONS = ((10, 5), (25, 10), (50, 30), (100, 50), (100, 100))
DEFAULT_LOSS_PROBABILITIES = (0.0, 0.1, 0.3, 0.5, 0.7, 0.9)


def parse_conditions(value: str) -> tuple[tuple[int, int], ...]:
    conditions: list[tuple[int, int]] = []
    for token in value.split(","):
        robots_text, tasks_text = token.lower().split("x", maxsplit=1)
        conditions.append((int(robots_text), int(tasks_text)))
    return tuple(conditions)


def parse_probabilities(value: str) -> tuple[float, ...]:
    return tuple(float(token.strip()) for token in value.split(",") if token.strip())


def parse_seed_set(value: str) -> frozenset[int]:
    if not value.strip():
        return frozenset()
    return frozenset(int(token.strip()) for token in value.split(",") if token.strip())


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def simulate_methods(
    *,
    cost_matrix,
    oracle,
    latency_sampler,
    loss_sampler,
    p_loss: float,
    phase_timeout_ms: float,
) -> tuple[LossyCoordinationResult, ...]:
    return (
        simulate_ideal_full_information_lossy_reference(
            cost_matrix=cost_matrix,
            assignment=oracle,
        ),
        simulate_leader_hungarian_lossy(
            cost_matrix=cost_matrix,
            sampler=latency_sampler,
            loss_sampler=loss_sampler,
            p_loss=p_loss,
            phase_timeout_ms=phase_timeout_ms,
        ),
        simulate_full_view_hungarian_lossy(
            cost_matrix=cost_matrix,
            assignment=oracle,
            sampler=latency_sampler,
            loss_sampler=loss_sampler,
            p_loss=p_loss,
            phase_timeout_ms=phase_timeout_ms,
        ),
        simulate_democracy_hungarian_lossy(
            cost_matrix=cost_matrix,
            sampler=latency_sampler,
            loss_sampler=loss_sampler,
            p_loss=p_loss,
            phase_timeout_ms=phase_timeout_ms,
        ),
    )


def result_row(
    *,
    seed: int,
    num_robots: int,
    num_tasks: int,
    p_loss: float,
    oracle,
    result: LossyCoordinationResult,
) -> dict[str, object]:
    full_success = result.full_assignment_success
    gap = (
        optimality_gap_percent(result.total_cost, oracle.total_cost)
        if full_success
        else float("nan")
    )
    optimal = int(full_success and abs(gap) <= 1e-9)
    correctness = evaluate_assignment_correctness(
        assigned_pairs=result.assigned_pairs,
        oracle_assignment=oracle,
        total_tasks=num_tasks,
    )

    return {
        "seed": seed,
        "robots": num_robots,
        "tasks": num_tasks,
        "p_loss": p_loss,
        "method": result.method,
        "committed_tasks": result.committed_tasks,
        "task_commit_rate": result.task_commit_rate,
        "full_assignment_success": int(full_success),
        "optimal_solution": optimal,
        "protocol_cost": result.total_cost,
        "oracle_cost": oracle.total_cost,
        "optimality_gap_percent": gap,
        "correct_committed_tasks": correctness.correct_committed_tasks,
        "incorrect_committed_tasks": correctness.incorrect_committed_tasks,
        "correct_executor_rate": correctness.correct_executor_rate,
        "correctness_among_committed": correctness.correctness_among_committed,
        "task_timeout_count": result.task_timeout_count,
        "cost_phase_completion_ms": result.cost_phase_completion_ms,
        "decision_completion_ms": result.decision_completion_ms,
        "global_agreement_ms": result.global_agreement_ms,
        "logical_message_count": result.logical_message_count,
        "payload_bytes": result.payload_bytes,
        "lossy_delivery_opportunities": result.lossy_delivery_opportunities,
        "lossy_delivered": result.lossy_delivered,
        "lossy_dropped": result.lossy_dropped,
        "mean_visible_robot_rows": result.mean_visible_robot_rows,
        "retry_count": 0,
        "safety_failures": 0,
    }


def summarize_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups = sorted(
        {
            (
                int(row["robots"]),
                int(row["tasks"]),
                float(row["p_loss"]),
                str(row["method"]),
            )
            for row in rows
        }
    )
    summaries: list[dict[str, object]] = []

    for robots, tasks, p_loss, method in groups:
        selected = [
            row
            for row in rows
            if int(row["robots"]) == robots
            and int(row["tasks"]) == tasks
            and float(row["p_loss"]) == p_loss
            and str(row["method"]) == method
        ]
        successful_gaps = [
            float(row["optimality_gap_percent"])
            for row in selected
            if math.isfinite(float(row["optimality_gap_percent"]))
        ]
        global_times = [float(row["global_agreement_ms"]) for row in selected]

        summaries.append(
            {
                "robots": robots,
                "tasks": tasks,
                "p_loss": p_loss,
                "method": method,
                "seeds": len(selected),
                "mean_task_commit_rate": statistics.fmean(
                    float(row["task_commit_rate"]) for row in selected
                ),
                "full_assignment_success_rate": statistics.fmean(
                    int(row["full_assignment_success"]) for row in selected
                ),
                "optimal_solution_rate": statistics.fmean(
                    int(row["optimal_solution"]) for row in selected
                ),
                "mean_correct_executor_rate": statistics.fmean(
                    float(row["correct_executor_rate"]) for row in selected
                ),
                "mean_correctness_among_committed": (
                    statistics.fmean(
                        float(row["correctness_among_committed"])
                        for row in selected
                        if math.isfinite(float(row["correctness_among_committed"]))
                    )
                    if any(
                        math.isfinite(float(row["correctness_among_committed"]))
                        for row in selected
                    )
                    else float("nan")
                ),
                "mean_optimality_gap_percent_successful": (
                    statistics.fmean(successful_gaps)
                    if successful_gaps
                    else float("nan")
                ),
                "mean_timeout_task_rate": statistics.fmean(
                    int(row["task_timeout_count"]) / tasks for row in selected
                ),
                "mean_decision_completion_ms": statistics.fmean(
                    float(row["decision_completion_ms"]) for row in selected
                ),
                "mean_global_agreement_ms": statistics.fmean(global_times),
                "p95_global_agreement_ms": percentile(global_times, 0.95),
                "mean_logical_message_count": statistics.fmean(
                    float(row["logical_message_count"]) for row in selected
                ),
                "mean_payload_bytes": statistics.fmean(
                    float(row["payload_bytes"]) for row in selected
                ),
                "mean_lossy_delivery_opportunities": statistics.fmean(
                    float(row["lossy_delivery_opportunities"]) for row in selected
                ),
                "mean_lossy_dropped": statistics.fmean(
                    float(row["lossy_dropped"]) for row in selected
                ),
                "mean_visible_robot_rows": statistics.fmean(
                    float(row["mean_visible_robot_rows"]) for row in selected
                ),
                "safety_failures": sum(
                    int(row["safety_failures"]) for row in selected
                ),
            }
        )
    return summaries


def write_audit_records(
    writer,
    *,
    seed: int,
    num_robots: int,
    num_tasks: int,
    p_loss: float,
    result: LossyCoordinationResult,
) -> None:
    for event in result.events:
        writer.writerow(
            {
                "record_type": "logical_message",
                "seed": seed,
                "robots": num_robots,
                "tasks": num_tasks,
                "p_loss": p_loss,
                "method": result.method,
                "phase": event.phase,
                "sender_id": event.sender_id,
                "receiver_id": event.receiver_id,
                "task_id": "" if event.task_id is None else event.task_id,
                "delivered": "",
                "send_time_ms": event.send_time_ms,
                "latency_ms": event.latency_ms,
                "arrival_time_ms": event.arrival_time_ms,
                "payload_bytes": event.payload_bytes,
            }
        )

    for observation in result.deliveries:
        writer.writerow(
            {
                "record_type": "delivery",
                "seed": seed,
                "robots": num_robots,
                "tasks": num_tasks,
                "p_loss": p_loss,
                "method": result.method,
                "phase": observation.phase,
                "sender_id": observation.sender_id,
                "receiver_id": observation.receiver_id,
                "task_id": "" if observation.task_id is None else observation.task_id,
                "delivered": int(observation.delivered),
                "send_time_ms": "",
                "latency_ms": "",
                "arrival_time_ms": (
                    ""
                    if observation.arrival_time_ms is None
                    else observation.arrival_time_ms
                ),
                "payload_bytes": "",
            }
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run E2 Bernoulli packet-loss robustness experiment"
    )
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument(
        "--conditions",
        type=parse_conditions,
        default=DEFAULT_CONDITIONS,
    )
    parser.add_argument(
        "--loss-probabilities",
        type=parse_probabilities,
        default=DEFAULT_LOSS_PROBABILITIES,
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/external/rady/perama_range_testing.json"),
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
    )
    parser.add_argument(
        "--event-log-seeds",
        type=parse_seed_set,
        default=frozenset({0}),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("results/e2_packet_loss"),
    )
    args = parser.parse_args()

    if args.seeds <= 0:
        raise ValueError("--seeds must be positive")

    dataset_path = ensure_rady_dataset(
        args.dataset,
        allow_download=not args.no_download,
    )
    profile = load_rady_latency_profile(dataset_path)
    profile_summary = summarize_latency_profile(profile)
    phase_timeout_ms = float(profile_summary["max_ms"])

    print(f"E2_PROFILE_LOCATION={profile.location} {profile.location_label}")
    print(f"E2_PROFILE_CONFIG={profile.config} {profile.config_label}")
    print(f"E2_PROFILE_SAMPLES={profile_summary['sample_count']}")
    print(f"E2_PHASE_TIMEOUT_MS={phase_timeout_ms:.6f}")
    print(
        "E2_LOSS_PROBABILITIES="
        + ",".join(f"{value:.3f}" for value in args.loss_probabilities)
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = args.output_root / "raw" / f"e2_{timestamp}.csv"
    summary_path = args.output_root / "summary.csv"
    events_path = args.output_root / "events" / f"e2_events_{timestamp}.csv.gz"

    raw_rows: list[dict[str, object]] = []
    events_path.parent.mkdir(parents=True, exist_ok=True)

    audit_fields = [
        "record_type",
        "seed",
        "robots",
        "tasks",
        "p_loss",
        "method",
        "phase",
        "sender_id",
        "receiver_id",
        "task_id",
        "delivered",
        "send_time_ms",
        "latency_ms",
        "arrival_time_ms",
        "payload_bytes",
    ]

    with gzip.open(events_path, "wt", newline="", encoding="utf-8") as handle:
        audit_writer = csv.DictWriter(handle, fieldnames=audit_fields)
        audit_writer.writeheader()

        for num_robots, num_tasks in args.conditions:
            for seed in range(args.seeds):
                scenario = generate_e0_scenario(seed, num_robots, num_tasks)
                oracle = solve_hungarian_assignment(scenario.cost_matrix)

                for p_loss in args.loss_probabilities:
                    latency_sampler = EmpiricalLatencySampler(profile, seed=seed)
                    loss_sampler = BernoulliLossSampler(seed=seed)

                    for result in simulate_methods(
                        cost_matrix=scenario.cost_matrix,
                        oracle=oracle,
                        latency_sampler=latency_sampler,
                        loss_sampler=loss_sampler,
                        p_loss=p_loss,
                        phase_timeout_ms=phase_timeout_ms,
                    ):
                        raw_rows.append(
                            result_row(
                                seed=seed,
                                num_robots=num_robots,
                                num_tasks=num_tasks,
                                p_loss=p_loss,
                                oracle=oracle,
                                result=result,
                            )
                        )
                        if seed in args.event_log_seeds:
                            write_audit_records(
                                audit_writer,
                                seed=seed,
                                num_robots=num_robots,
                                num_tasks=num_tasks,
                                p_loss=p_loss,
                                result=result,
                            )

    write_csv(raw_path, raw_rows)
    summary_rows = summarize_rows(raw_rows)
    write_csv(summary_path, summary_rows)

    print(f"E2_RAW={raw_path}")
    print(f"E2_EVENTS={events_path}")
    print(f"E2_SUMMARY={summary_path}")

    for row in summary_rows:
        gap = float(row["mean_optimality_gap_percent_successful"])
        gap_text = "nan" if not math.isfinite(gap) else f"{gap:.6f}%"
        print(
            "E2_RESULT "
            f"robots={row['robots']} tasks={row['tasks']} "
            f"p_loss={float(row['p_loss']):.1f} method={row['method']} "
            f"task_commit={float(row['mean_task_commit_rate']):.6f} "
            f"full_success={float(row['full_assignment_success_rate']):.6f} "
            f"optimal_rate={float(row['optimal_solution_rate']):.6f} "
            f"cer={float(row['mean_correct_executor_rate']):.6f} "
            f"correct_given_commit={float(row['mean_correctness_among_committed']):.6f} "
            f"gap_successful={gap_text} "
            f"timeout_task_rate={float(row['mean_timeout_task_rate']):.6f} "
            f"decision_mean={float(row['mean_decision_completion_ms']):.6f}ms "
            f"drops_mean={float(row['mean_lossy_dropped']):.1f} "
            f"messages_mean={float(row['mean_logical_message_count']):.1f} "
            f"visible_rows_mean={float(row['mean_visible_robot_rows']):.3f} "
            f"safety_failures={row['safety_failures']}"
        )


if __name__ == "__main__":
    main()
