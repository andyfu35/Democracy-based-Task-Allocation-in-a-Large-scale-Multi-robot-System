"""E3/E4 full-factorial size/load benchmark, delegating voting to E2 owner.

No new voting, quorum, retirement or packet-loss implementation lives here.
Existing E2 per-cell raw/round/audit records are the primary evidence.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path

from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import validate_packet_loss_probability
from experiments.run_e2 import parse_probabilities, write_csv
from experiments.run_e2_retirement import (
    read_retirement_revision,
    run_retirement_experiment,
)


MAX_ROBOTS = 100
DEFAULT_ROBOTS = (10, 20, 40, 60, 80, 100)
DEFAULT_RATIOS = (0.10, 0.25, 0.50, 0.75, 1.0)
DEFAULT_LOSSES = (0.0, 0.30)
DEFAULT_OUTPUT_ROOT = Path("results/e3_e4_scaling_100robot_cap")
DEFAULT_DATASET = Path("data/external/rady/perama_range_testing.json")
METHOD = "democracy_greedy_quarter_plurality_retirement"
VOTE_RULE = "quarter_plurality"
PLAN_VERSION = 1


@dataclass(frozen=True)
class ScalingCell:
    robots: int
    tasks: int
    target_load_ratio: float

    @property
    def actual_load_ratio(self) -> float:
        return self.tasks / self.robots

    @property
    def identifier(self) -> str:
        return f"R{self.robots:03d}_T{self.tasks:03d}"


def validate_scaling_axes(
    *,
    robot_levels: tuple[int, ...],
    load_ratios: tuple[float, ...],
    losses: tuple[float, ...],
    seeds: int,
    attempts_per_task: int,
) -> None:
    """Validate benchmark configuration, not network or robot planning."""
    owner = "experiments.run_e3_e4_scaling"
    function = "validate_scaling_axes"

    if (
        not robot_levels
        or any(type(n) is not int or n < 1 or n > MAX_ROBOTS for n in robot_levels)
        or tuple(sorted(set(robot_levels))) != robot_levels
    ):
        raise ProtocolError(Diagnostic(
            owner=owner, function=function, category="data",
            code="INVALID_SCALING_ROBOT_LEVELS",
            expected=f"nonempty, strictly increasing unique integers in [1,{MAX_ROBOTS}]",
            actual=robot_levels,
        ))
    if (
        not load_ratios
        or any(not math.isfinite(r) or r <= 0 or r > 1 for r in load_ratios)
        or tuple(sorted(set(load_ratios))) != load_ratios
    ):
        raise ProtocolError(Diagnostic(
            owner=owner, function=function, category="data",
            code="INVALID_SCALING_LOAD_RATIOS",
            expected="strictly increasing unique fractions in (0,1]",
            actual=load_ratios,
        ))
    if (
        not losses
        or tuple(sorted(set(losses))) != losses
    ):
        raise ProtocolError(Diagnostic(
            owner=owner, function=function, category="data",
            code="INVALID_SCALING_LOSS_LEVELS",
            expected="strictly increasing unique equal Cost/Vote loss levels",
            actual=losses,
        ))
    for p in losses:
        validate_packet_loss_probability(p)

    if type(seeds) is not int or seeds < 1:
        raise ProtocolError(Diagnostic(
            owner=owner, function=function, category="data",
            code="INVALID_SCALING_SEEDS",
            expected="seeds >= 1", actual=seeds,
        ))
    if type(attempts_per_task) is not int or attempts_per_task < 1:
        raise ProtocolError(Diagnostic(
            owner=owner, function=function, category="data",
            code="INVALID_SCALING_ATTEMPT_MULTIPLIER",
            expected="attempts_per_task >= 1", actual=attempts_per_task,
        ))


def build_scaling_cells(
    *,
    robot_levels: tuple[int, ...],
    load_ratios: tuple[float, ...],
) -> tuple[ScalingCell, ...]:
    """Apply deterministic half-up rounding and enforce tasks <= robots."""
    cells: list[ScalingCell] = []
    owner = "experiments.run_e3_e4_scaling"
    for robots in robot_levels:
        seen_tasks: set[int] = set()
        for load in load_ratios:
            tasks = math.floor(robots * load + 0.5)
            if tasks < 1 or tasks > robots:
                raise ProtocolError(Diagnostic(
                    owner=owner, function="build_scaling_cells", category="data",
                    code="SCALING_TASK_COUNT_OUT_OF_RANGE",
                    expected=f"1 <= tasks <= {robots}", actual=tasks,
                    details=f"target_ratio={load}",
                ))
            if tasks in seen_tasks:
                raise ProtocolError(Diagnostic(
                    owner=owner, function="build_scaling_cells", category="contract",
                    code="SCALING_DUPLICATE_TASK_CELL",
                    expected="distinct integer task count for each ratio at each robot level",
                    actual=(robots, tasks),
                    details=f"target_ratio={load}; remove rounded duplicate",
                ))
            seen_tasks.add(tasks)
            cells.append(ScalingCell(robots=robots, tasks=tasks, target_load_ratio=load))
    return tuple(cells)


def make_scaling_plan(
    *,
    cells: tuple[ScalingCell, ...],
    robot_levels: tuple[int, ...],
    load_ratios: tuple[float, ...],
    losses: tuple[float, ...],
    seeds: int,
    attempts_per_task: int,
    dataset: Path,
    git_sha: str,
) -> dict[str, object]:
    """Freeze configuration and source revision for safe restart."""
    return {
        "schema_version": PLAN_VERSION,
        "git_sha": git_sha,
        "method": METHOD,
        "vote_decision_rule": VOTE_RULE,
        "robot_cap": MAX_ROBOTS,
        "robot_levels": list(robot_levels),
        "target_load_ratios": list(load_ratios),
        "loss_probabilities_cost_equals_vote": list(losses),
        "seeds": seeds,
        "max_attempts_formula": "attempts_per_task * tasks",
        "attempts_per_task": attempts_per_task,
        "dataset": str(dataset),
        "scenario_generator": "generate_e0_scenario",
        "scenario_world_size": 100.0,
        "cells": [
            {
                "robots": c.robots,
                "tasks": c.tasks,
                "target_load_ratio": c.target_load_ratio,
                "actual_load_ratio": c.actual_load_ratio,
                "max_rounds": attempts_per_task * c.tasks,
            }
            for c in cells
        ],
    }


def prepare_scaling_output(
    *,
    output_root: Path,
    plan: dict[str, object],
    resume: bool,
) -> None:
    """Prevent incompatible source/seed/grid experiments sharing raw evidence."""
    plan_path = output_root / "benchmark_plan.json"
    if plan_path.is_file():
        if not resume:
            raise ProtocolError(Diagnostic(
                owner="experiments.run_e3_e4_scaling",
                function="prepare_scaling_output", category="state",
                code="SCALING_OUTPUT_ALREADY_EXISTS",
                expected="new root or explicitly request --resume",
                actual=str(output_root),
            ))
        previous = json.loads(plan_path.read_text(encoding="utf-8"))
        if previous != plan:
            raise ProtocolError(Diagnostic(
                owner="experiments.run_e3_e4_scaling",
                function="prepare_scaling_output", category="contract",
                code="SCALING_RESUME_PLAN_MISMATCH",
                expected=previous, actual=plan,
                details="source SHA, size grid, loss levels, seeds, and dataset must match",
            ))
        return
    if output_root.exists() and any(output_root.iterdir()):
        raise ProtocolError(Diagnostic(
            owner="experiments.run_e3_e4_scaling",
            function="prepare_scaling_output", category="state",
            code="SCALING_UNMANAGED_OUTPUT_ROOT",
            expected="empty/new output root or a matching benchmark_plan.json",
            actual=str(output_root),
        ))
    output_root.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_completed_scaling_cell(
    *,
    cell_root: Path,
    cell: ScalingCell,
    losses: tuple[float, ...],
    seeds: int,
    attempts_per_task: int,
    git_sha: str,
) -> list[dict[str, str]]:
    """Audit existing per-cell evidence before accepting a resumed result."""
    owner = "experiments.run_e3_e4_scaling"
    function = "read_completed_scaling_cell"
    summary_path = cell_root / "summary.csv"
    raw_files = sorted((cell_root / "raw").glob("retirement_*.csv"))
    round_files = sorted((cell_root / "rounds").glob("retirement_rounds_*.csv"))
    audit_files = sorted((cell_root / "events").glob("retirement_audit_*.csv.gz"))
    if (
        not summary_path.is_file()
        or len(raw_files) != 1 or len(round_files) != 1
        or len(audit_files) != 1
    ):
        raise ProtocolError(Diagnostic(
            owner=owner, function=function, category="contract",
            code="SCALING_CELL_EVIDENCE_INCOMPLETE",
            expected="summary.csv and exactly one raw, rounds and compressed audit file",
            actual={
                "summary": summary_path.is_file(), "raw": len(raw_files),
                "rounds": len(round_files), "audit": len(audit_files),
            },
            details=str(cell_root),
        ))
    with summary_path.open(newline="", encoding="utf-8") as stream:
        summaries = list(csv.DictReader(stream))
    with raw_files[0].open(newline="", encoding="utf-8") as stream:
        raw = list(csv.DictReader(stream))

    expected_pairs = {(p, p) for p in losses}
    summary_pairs = {
        (float(row["p_cost_loss"]), float(row["p_vote_loss"])) for row in summaries
    }
    raw_keys = {
        (int(row["seed"]), float(row["p_cost_loss"]), float(row["p_vote_loss"]))
        for row in raw
    }
    expected_raw_keys = {
        (seed, p, p) for seed in range(seeds) for p in losses
    }
    row_shapes_ok = all(
        int(row["robots"]) == cell.robots
        and int(row["tasks"]) == cell.tasks
        and int(row["max_rounds"]) == cell.tasks * attempts_per_task
        and row["method"] == METHOD
        and row["vote_decision_rule"] == VOTE_RULE
        for row in (*raw, *summaries)
    )
    raw_revisions_ok = all(row["git_sha"] == git_sha for row in raw)
    seeds_ok = all(int(row["seeds"]) == seeds for row in summaries)

    if not (
        len(summaries) == len(losses)
        and summary_pairs == expected_pairs
        and len(raw) == seeds * len(losses)
        and raw_keys == expected_raw_keys
        and row_shapes_ok and raw_revisions_ok and seeds_ok
    ):
        raise ProtocolError(Diagnostic(
            owner=owner, function=function, category="contract",
            code="SCALING_CELL_PROVENANCE_MISMATCH",
            expected={
                "robots": cell.robots, "tasks": cell.tasks,
                "seeds": seeds, "loss_pairs": sorted(expected_pairs),
                "git_sha": git_sha, "method": METHOD,
            },
            actual={
                "raw_rows": len(raw), "summary_rows": len(summaries),
                "raw_unique_keys": len(raw_keys),
                "summary_pairs": sorted(summary_pairs),
                "shape_valid": row_shapes_ok,
                "revision_valid": raw_revisions_ok,
                "seeds_valid": seeds_ok,
            },
            details=str(cell_root),
        ))
    return summaries


def build_scaling_aggregate_rows(
    *,
    cell: ScalingCell,
    cell_summary: list[dict[str, str]],
    cell_root: Path,
    output_root: Path,
    git_sha: str,
) -> list[dict[str, object]]:
    """Normalize communication/time by requested tasks, preserving old metrics."""
    return [
        {
            **summary,
            "git_sha": git_sha,
            "target_load_ratio": cell.target_load_ratio,
            "actual_load_ratio": cell.actual_load_ratio,
            "attempts_per_task": int(summary["max_rounds"]) / cell.tasks,
            "mean_committed_tasks": cell.tasks * float(summary["mean_task_commit_rate"]),
            "mean_attempts_per_task": float(summary["mean_rounds_executed"]) / cell.tasks,
            "mean_elapsed_ms_per_requested_task": float(summary["mean_elapsed_ms"]) / cell.tasks,
            "mean_messages_per_requested_task": float(summary["mean_logical_message_count"]) / cell.tasks,
            "mean_payload_bytes_per_requested_task": float(summary["mean_payload_bytes"]) / cell.tasks,
            "cell_id": cell.identifier,
            "cell_summary_path": str((cell_root / "summary.csv").relative_to(output_root)),
        }
        for summary in cell_summary
    ]


def run_scaling_benchmark(
    *,
    robot_levels: tuple[int, ...] = DEFAULT_ROBOTS,
    load_ratios: tuple[float, ...] = DEFAULT_RATIOS,
    losses: tuple[float, ...] = DEFAULT_LOSSES,
    seeds: int = 100,
    attempts_per_task: int = 2,
    dataset: Path = DEFAULT_DATASET,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    allow_download: bool = True,
    resume: bool = False,
) -> list[dict[str, object]]:
    """Run independent 100-seed size/load cells through the proven E2 owner."""
    validate_scaling_axes(
        robot_levels=robot_levels,
        load_ratios=load_ratios,
        losses=losses, seeds=seeds,
        attempts_per_task=attempts_per_task,
    )
    cells = build_scaling_cells(robot_levels=robot_levels, load_ratios=load_ratios)
    git_sha = read_retirement_revision()
    plan = make_scaling_plan(
        cells=cells, robot_levels=robot_levels, load_ratios=load_ratios,
        losses=losses, seeds=seeds, attempts_per_task=attempts_per_task,
        dataset=dataset, git_sha=git_sha,
    )
    prepare_scaling_output(output_root=output_root, plan=plan, resume=resume)

    print(
        "E3E4_SCALING_CONFIG "
        f"robot_levels={len(robot_levels)} load_ratios={len(load_ratios)} "
        f"size_cells={len(cells)} loss_levels={len(losses)} "
        f"seeds={seeds} total_seed_conditions={len(cells) * len(losses) * seeds} "
        f"max_robots={MAX_ROBOTS} max_tasks={max(c.tasks for c in cells)} "
        f"method={METHOD} cost_equals_vote=true "
        f"round_limit_per_cell={attempts_per_task}*tasks git_sha={git_sha}",
        flush=True,
    )

    aggregated: list[dict[str, object]] = []
    for index, cell in enumerate(cells, start=1):
        cell_root = output_root / "cells" / cell.identifier
        summary_path = cell_root / "summary.csv"
        if summary_path.is_file():
            if not resume:
                raise ProtocolError(Diagnostic(
                    owner="experiments.run_e3_e4_scaling",
                    function="run_scaling_benchmark", category="state",
                    code="SCALING_EXISTING_CELL_REQUIRES_RESUME",
                    expected="--resume for any existing cell", actual=str(cell_root),
                ))
            print(
                f"E3E4_CELL_REUSE index={index}/{len(cells)} "
                f"robots={cell.robots} tasks={cell.tasks}",
                flush=True,
            )
        else:
            if cell_root.exists() and any(cell_root.iterdir()):
                raise ProtocolError(Diagnostic(
                    owner="experiments.run_e3_e4_scaling",
                    function="run_scaling_benchmark", category="state",
                    code="SCALING_PARTIAL_CELL_REQUIRES_MANUAL_REVIEW",
                    expected="empty cell output directory or complete validated evidence",
                    actual=str(cell_root),
                    details="preserve/move interrupted artifacts before restarting this cell",
                ))
            print(
                f"E3E4_CELL_START index={index}/{len(cells)} "
                f"robots={cell.robots} tasks={cell.tasks} "
                f"target_load={cell.target_load_ratio:.2f} "
                f"actual_load={cell.actual_load_ratio:.3f} "
                f"max_attempts={cell.tasks * attempts_per_task}",
                flush=True,
            )
            run_retirement_experiment(
                robots=cell.robots, tasks=cell.tasks, seeds=seeds,
                cost_losses=losses, p_vote_loss=0.0,
                vote_losses=losses, loss_pairing="diagonal",
                vote_decision_rule=VOTE_RULE,
                max_rounds=cell.tasks * attempts_per_task,
                dataset_path=dataset, output_root=cell_root,
                allow_download=allow_download,
            )

        validated = read_completed_scaling_cell(
            cell_root=cell_root, cell=cell, losses=losses,
            seeds=seeds, attempts_per_task=attempts_per_task,
            git_sha=git_sha,
        )
        aggregated.extend(build_scaling_aggregate_rows(
            cell=cell, cell_summary=validated,
            cell_root=cell_root, output_root=output_root, git_sha=git_sha,
        ))
        # A complete and validated prefix is preserved even if interrupted.
        write_csv(output_root / "summary.csv", aggregated)
        print(
            f"E3E4_CELL_COMPLETE index={index}/{len(cells)} "
            f"robots={cell.robots} tasks={cell.tasks} "
            f"aggregated_conditions={len(aggregated)} "
            f"summary={output_root / 'summary.csv'}",
            flush=True,
        )

    print(
        f"E3E4_SCALING_COMPLETE cells={len(cells)} "
        f"conditions={len(aggregated)} "
        f"seed_conditions={len(cells) * len(losses) * seeds} "
        f"git_sha={git_sha}",
        flush=True,
    )
    return aggregated


def parse_int_levels(text: str) -> tuple[int, ...]:
    return tuple(int(value.strip()) for value in text.split(",") if value.strip())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="E3/E4 pure-25pct Greedy R/T scale grid, at most 100 robots and T<=R"
    )
    parser.add_argument("--robot-levels", type=parse_int_levels, default=DEFAULT_ROBOTS)
    parser.add_argument("--load-ratios", type=parse_probabilities, default=DEFAULT_RATIOS)
    parser.add_argument("--loss-probabilities", type=parse_probabilities, default=DEFAULT_LOSSES)
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--attempts-per-task", type=int, default=2)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    run_scaling_benchmark(
        robot_levels=args.robot_levels,
        load_ratios=args.load_ratios,
        losses=args.loss_probabilities,
        seeds=args.seeds,
        attempts_per_task=args.attempts_per_task,
        dataset=args.dataset,
        output_root=args.output_root,
        allow_download=not args.no_download,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()
