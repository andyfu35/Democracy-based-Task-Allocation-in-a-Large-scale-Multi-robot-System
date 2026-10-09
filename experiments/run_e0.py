from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import statistics

from democracy_mrta.metrics import evaluate_e0
from democracy_mrta.protocol import run_zero_loss_allocation_epoch
from democracy_mrta.scenario import generate_e0_scenario


DEFAULT_CONDITIONS = ((10, 5), (25, 10), (50, 30), (100, 50), (100, 100))


def parse_conditions(value: str) -> tuple[tuple[int, int], ...]:
    conditions: list[tuple[int, int]] = []
    for token in value.split(","):
        robots_text, tasks_text = token.lower().split("x", maxsplit=1)
        conditions.append((int(robots_text), int(tasks_text)))
    return tuple(conditions)


def mean_ci95(values: list[float]) -> tuple[float, float]:
    if not values:
        return float("nan"), float("nan")
    mean_value = statistics.fmean(values)
    if len(values) < 2:
        return mean_value, 0.0
    sem = statistics.stdev(values) / (len(values) ** 0.5)
    return mean_value, 1.96 * sem


def run_one_seed(seed: int, num_robots: int, num_tasks: int) -> dict[str, object]:
    scenario = generate_e0_scenario(seed, num_robots, num_tasks)
    allocation = run_zero_loss_allocation_epoch(scenario.cost_matrix)
    metrics = evaluate_e0(cost_matrix=scenario.cost_matrix, allocation=allocation)

    replay_scenario = generate_e0_scenario(seed, num_robots, num_tasks)
    replay_allocation = run_zero_loss_allocation_epoch(replay_scenario.cost_matrix)
    deterministic_replay_failure = int(
        scenario != replay_scenario or allocation != replay_allocation
    )

    return {
        "seed": seed,
        "robots": num_robots,
        "tasks": num_tasks,
        "protocol_cost": metrics.protocol_cost,
        "oracle_cost": metrics.oracle_cost,
        "optimality_gap_percent": metrics.optimality_gap_percent,
        "assignment_success_rate": metrics.assignment_success_rate,
        "multiple_winner_failures": allocation.multiple_winner_failures,
        "duplicate_execution_failures": allocation.duplicate_execution_failures,
        "duplicate_vote_counted_failures": allocation.duplicate_vote_counted_failures,
        "stale_vote_accepted_failures": allocation.stale_vote_accepted_failures,
        "deterministic_replay_failures": deterministic_replay_failure,
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    conditions = sorted({(int(row["robots"]), int(row["tasks"])) for row in rows})
    summary_rows: list[dict[str, object]] = []
    for robots, tasks in conditions:
        selected = [row for row in rows if row["robots"] == robots and row["tasks"] == tasks]
        gaps = [float(row["optimality_gap_percent"]) for row in selected]
        gap_mean, gap_ci = mean_ci95(gaps)
        summary_rows.append(
            {
                "robots": robots,
                "tasks": tasks,
                "seeds": len(selected),
                "mean_optimality_gap_percent": gap_mean,
                "ci95_halfwidth_optimality_gap_percent": gap_ci,
                "mean_assignment_success_rate": statistics.fmean(
                    float(row["assignment_success_rate"]) for row in selected
                ),
                "multiple_winner_failures": sum(
                    int(row["multiple_winner_failures"]) for row in selected
                ),
                "duplicate_execution_failures": sum(
                    int(row["duplicate_execution_failures"]) for row in selected
                ),
                "duplicate_vote_counted_failures": sum(
                    int(row["duplicate_vote_counted_failures"]) for row in selected
                ),
                "stale_vote_accepted_failures": sum(
                    int(row["stale_vote_accepted_failures"]) for row in selected
                ),
                "deterministic_replay_failures": sum(
                    int(row["deterministic_replay_failures"]) for row in selected
                ),
            }
        )
    return summary_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run E0 Protocol Correctness Preflight")
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument(
        "--conditions",
        type=parse_conditions,
        default=DEFAULT_CONDITIONS,
        help="comma-separated ROBOTSxTASKS list, e.g. 10x5,25x10,100x100",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("results/e0_protocol_correctness"),
    )
    args = parser.parse_args()

    if args.seeds <= 0:
        raise ValueError("--seeds must be positive")

    raw_rows: list[dict[str, object]] = []
    for num_robots, num_tasks in args.conditions:
        for seed in range(args.seeds):
            raw_rows.append(run_one_seed(seed, num_robots, num_tasks))

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = args.output_root / "raw" / f"e0_{timestamp}.csv"
    summary_path = args.output_root / "summary.csv"

    write_csv(raw_path, raw_rows)
    summary_rows = build_summary(raw_rows)
    write_csv(summary_path, summary_rows)

    print(f"E0_RAW={raw_path}")
    print(f"E0_SUMMARY={summary_path}")
    for row in summary_rows:
        print(
            "E0_RESULT "
            f"robots={row['robots']} tasks={row['tasks']} seeds={row['seeds']} "
            f"gap_mean={float(row['mean_optimality_gap_percent']):.6f}% "
            f"gap_ci95=+/-{float(row['ci95_halfwidth_optimality_gap_percent']):.6f}% "
            f"asr={float(row['mean_assignment_success_rate']):.6f} "
            f"safety_failures="
            f"{int(row['multiple_winner_failures']) + int(row['duplicate_execution_failures']) + int(row['duplicate_vote_counted_failures']) + int(row['stale_vote_accepted_failures'])} "
            f"replay_failures={row['deterministic_replay_failures']}"
        )


if __name__ == "__main__":
    main()
