from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import gzip
from pathlib import Path
import statistics
import time

from democracy_mrta.coordination import (
    CoordinationTimingResult,
    simulate_democracy_hungarian,
    simulate_full_view_hungarian,
    simulate_ideal_full_information,
    simulate_leader_hungarian,
)
from democracy_mrta.network import (
    EmpiricalLatencySampler,
    ensure_rady_dataset,
    load_rady_latency_profile,
    percentile,
    summarize_latency_profile,
)
from democracy_mrta.optimizer import solve_hungarian_assignment
from democracy_mrta.scenario import generate_e0_scenario


DEFAULT_CONDITIONS = ((10, 5), (25, 10), (50, 30), (100, 50), (100, 100))


def parse_conditions(value: str) -> tuple[tuple[int, int], ...]:
    conditions: list[tuple[int, int]] = []
    for token in value.split(","):
        robots_text, tasks_text = token.lower().split("x", maxsplit=1)
        conditions.append((int(robots_text), int(tasks_text)))
    return tuple(conditions)


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


def timed_hungarian(cost_matrix) -> tuple[object, float]:
    start_ns = time.perf_counter_ns()
    assignment = solve_hungarian_assignment(cost_matrix)
    elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
    return assignment, elapsed_ms


def simulate_methods(
    *,
    num_robots: int,
    num_tasks: int,
    assignment,
    sampler,
) -> tuple[CoordinationTimingResult, ...]:
    return (
        simulate_ideal_full_information(),
        simulate_leader_hungarian(
            num_robots=num_robots,
            num_tasks=num_tasks,
            sampler=sampler,
        ),
        simulate_full_view_hungarian(
            num_robots=num_robots,
            num_tasks=num_tasks,
            sampler=sampler,
        ),
        simulate_democracy_hungarian(
            num_robots=num_robots,
            num_tasks=num_tasks,
            assignment=assignment,
            sampler=sampler,
        ),
    )


def result_row(
    *,
    seed: int,
    num_robots: int,
    num_tasks: int,
    hungarian_compute_ms: float,
    result: CoordinationTimingResult,
) -> dict[str, object]:
    return {
        "seed": seed,
        "robots": num_robots,
        "tasks": num_tasks,
        "method": result.method,
        "network_cost_exchange_ms": result.cost_exchange_completion_ms,
        "network_actionable_decision_ms": result.actionable_decision_ms,
        "network_global_agreement_ms": result.global_agreement_ms,
        "reference_hungarian_compute_ms": hungarian_compute_ms,
        "message_count": result.message_count,
        "payload_bytes": result.payload_bytes,
    }


def summarize_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups = sorted(
        {
            (int(row["robots"]), int(row["tasks"]), str(row["method"]))
            for row in rows
        }
    )
    summaries: list[dict[str, object]] = []

    for robots, tasks, method in groups:
        selected = [
            row
            for row in rows
            if int(row["robots"]) == robots
            and int(row["tasks"]) == tasks
            and str(row["method"]) == method
        ]
        global_ms = [float(row["network_global_agreement_ms"]) for row in selected]
        actionable_ms = [float(row["network_actionable_decision_ms"]) for row in selected]
        cost_ms = [float(row["network_cost_exchange_ms"]) for row in selected]

        summaries.append(
            {
                "robots": robots,
                "tasks": tasks,
                "method": method,
                "seeds": len(selected),
                "mean_network_global_agreement_ms": statistics.fmean(global_ms),
                "p50_network_global_agreement_ms": percentile(global_ms, 0.50),
                "p95_network_global_agreement_ms": percentile(global_ms, 0.95),
                "p99_network_global_agreement_ms": percentile(global_ms, 0.99),
                "mean_network_actionable_decision_ms": statistics.fmean(actionable_ms),
                "mean_network_cost_exchange_ms": statistics.fmean(cost_ms),
                "mean_reference_hungarian_compute_ms": statistics.fmean(
                    float(row["reference_hungarian_compute_ms"]) for row in selected
                ),
                "mean_message_count": statistics.fmean(
                    float(row["message_count"]) for row in selected
                ),
                "mean_payload_bytes": statistics.fmean(
                    float(row["payload_bytes"]) for row in selected
                ),
            }
        )

    return summaries


def write_selected_events(
    handle,
    *,
    seed: int,
    num_robots: int,
    num_tasks: int,
    result: CoordinationTimingResult,
) -> None:
    for event in result.events:
        handle.writerow(
            {
                "seed": seed,
                "robots": num_robots,
                "tasks": num_tasks,
                "method": result.method,
                "phase": event.phase,
                "sender_id": event.sender_id,
                "receiver_id": event.receiver_id,
                "task_id": "" if event.task_id is None else event.task_id,
                "send_time_ms": event.send_time_ms,
                "latency_ms": event.latency_ms,
                "arrival_time_ms": event.arrival_time_ms,
                "payload_bytes": event.payload_bytes,
            }
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run E1 trace-driven Wi-Fi communication-time experiment"
    )
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument(
        "--conditions",
        type=parse_conditions,
        default=DEFAULT_CONDITIONS,
        help="comma-separated ROBOTSxTASKS list",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/external/rady/perama_range_testing.json"),
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="fail instead of downloading the pinned dataset if missing",
    )
    parser.add_argument(
        "--event-log-seeds",
        type=parse_seed_set,
        default=frozenset({0}),
        help="comma-separated seeds whose per-message events are saved; default: 0",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("results/e1_latency"),
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

    print(f"E1_PROFILE_LOCATION={profile.location} {profile.location_label}")
    print(f"E1_PROFILE_CONFIG={profile.config} {profile.config_label}")
    print(f"E1_PROFILE_SAMPLES={profile_summary['sample_count']}")
    print(f"E1_PROFILE_MEAN_MS={profile_summary['mean_ms']:.6f}")
    print(f"E1_PROFILE_P50_MS={profile_summary['p50_ms']:.6f}")
    print(f"E1_PROFILE_P95_MS={profile_summary['p95_ms']:.6f}")
    print(f"E1_PROFILE_P99_MS={profile_summary['p99_ms']:.6f}")
    print(f"E1_PROFILE_MAX_MS={profile_summary['max_ms']:.6f}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = args.output_root / "raw" / f"e1_{timestamp}.csv"
    summary_path = args.output_root / "summary.csv"
    events_path = args.output_root / "events" / f"e1_events_{timestamp}.csv.gz"

    args.output_root.mkdir(parents=True, exist_ok=True)
    events_path.parent.mkdir(parents=True, exist_ok=True)

    raw_rows: list[dict[str, object]] = []

    with gzip.open(events_path, "wt", newline="", encoding="utf-8") as event_file:
        event_fields = [
            "seed",
            "robots",
            "tasks",
            "method",
            "phase",
            "sender_id",
            "receiver_id",
            "task_id",
            "send_time_ms",
            "latency_ms",
            "arrival_time_ms",
            "payload_bytes",
        ]
        event_writer = csv.DictWriter(event_file, fieldnames=event_fields)
        event_writer.writeheader()

        for num_robots, num_tasks in args.conditions:
            for seed in range(args.seeds):
                scenario = generate_e0_scenario(seed, num_robots, num_tasks)
                assignment, compute_ms = timed_hungarian(scenario.cost_matrix)
                sampler = EmpiricalLatencySampler(profile, seed=seed)

                for result in simulate_methods(
                    num_robots=num_robots,
                    num_tasks=num_tasks,
                    assignment=assignment,
                    sampler=sampler,
                ):
                    raw_rows.append(
                        result_row(
                            seed=seed,
                            num_robots=num_robots,
                            num_tasks=num_tasks,
                            hungarian_compute_ms=compute_ms,
                            result=result,
                        )
                    )
                    if seed in args.event_log_seeds:
                        write_selected_events(
                            event_writer,
                            seed=seed,
                            num_robots=num_robots,
                            num_tasks=num_tasks,
                            result=result,
                        )

    write_csv(raw_path, raw_rows)
    summary_rows = summarize_rows(raw_rows)
    write_csv(summary_path, summary_rows)

    print(f"E1_RAW={raw_path}")
    print(f"E1_EVENTS={events_path}")
    print(f"E1_SUMMARY={summary_path}")

    for row in summary_rows:
        print(
            "E1_RESULT "
            f"robots={row['robots']} tasks={row['tasks']} method={row['method']} "
            f"network_mean={float(row['mean_network_global_agreement_ms']):.6f}ms "
            f"network_p95={float(row['p95_network_global_agreement_ms']):.6f}ms "
            f"actionable_mean={float(row['mean_network_actionable_decision_ms']):.6f}ms "
            f"cost_exchange_mean={float(row['mean_network_cost_exchange_ms']):.6f}ms "
            f"messages_mean={float(row['mean_message_count']):.1f} "
            f"payload_bytes_mean={float(row['mean_payload_bytes']):.1f} "
            f"hungarian_compute_mean={float(row['mean_reference_hungarian_compute_ms']):.6f}ms"
        )


if __name__ == "__main__":
    main()
