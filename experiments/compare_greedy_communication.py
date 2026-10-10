"""Greedy-only analysis of PREEXISTING paired Majority and 25%-plurality E2 runs.

Never runs a robot simulator, Hungarian solver, or alternate voting state machine.
The only reference is each scenario's original zero-loss sequential Greedy.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics

from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from experiments.run_e2 import parse_probabilities, write_csv
from experiments.run_e2_retirement import read_retirement_revision

OWNER = "experiments.compare_greedy_communication"
RULES = ("strict_majority", "quarter_plurality")
METHODS = {
    "strict_majority": "democracy_greedy_retirement",
    "quarter_plurality": "democracy_greedy_quarter_plurality_retirement",
}
DEFAULT_MAJORITY = Path("results/e2_joint_loss_diagonal_100r50t")
DEFAULT_QUARTER = Path("results/e2_greedy_quarter_plurality_no_fallback_100r50t")
DEFAULT_OUTPUT = Path("results/e2_greedy_only_communication_comparison")
DEFAULT_LOSSES = (0.0, 0.10, 0.20, 0.30, 0.40, 0.50)
REQUIRED_COLUMNS = frozenset({
    "seed", "git_sha", "robots", "tasks", "max_rounds",
    "method", "p_cost_loss", "p_vote_loss", "full_assignment_success",
    "committed_tasks", "task_commit_rate", "greedy_correct_executor_rate",
    "total_cost", "greedy_reference_cost", "rounds_executed",
    "total_elapsed_ms", "logical_message_count", "payload_bytes",
    "quorum_failed_attempts", "safety_failures",
    "cost_packet_attempts", "cost_packet_dropped",
    "remote_vote_attempts", "remote_vote_dropped",
})


def comparison_error(
    *,
    function: str,
    category: str,
    code: str,
    expected: object,
    actual: object,
    details: str = "",
) -> ProtocolError:
    return ProtocolError(Diagnostic(
        owner=OWNER, function=function, category=category,
        code=code, expected=expected, actual=actual, details=details,
    ))


def validate_comparison_configuration(
    *,
    robots: int, tasks: int, seeds: int, max_rounds: int,
    losses: tuple[float, ...],
) -> None:
    """Fail before touching evidence when a paired Greedy design is invalid."""
    if (
        type(robots) is not int or type(tasks) is not int
        or not 1 <= tasks <= robots <= 100
        or type(seeds) is not int or seeds < 1
        or type(max_rounds) is not int or max_rounds < tasks
    ):
        raise comparison_error(
            function="validate_comparison_configuration", category="data",
            code="INVALID_GREEDY_COMPARISON_SHAPE",
            expected="1 <= tasks <= robots <= 100, seeds >= 1, max_rounds >= tasks",
            actual=(robots, tasks, seeds, max_rounds),
        )
    if (
        not losses or losses[0] != 0.0
        or tuple(sorted(set(losses))) != losses
        or any(not math.isfinite(p) or not 0 <= p <= 1 for p in losses)
    ):
        raise comparison_error(
            function="validate_comparison_configuration", category="data",
            code="INVALID_GREEDY_COMPARISON_LOSS_AXIS",
            expected="nonempty sorted unique diagonal loss levels in [0,1], including 0",
            actual=losses,
        )


def locate_single_raw_evidence(*, root: Path, rule: str) -> Path:
    """Require ONE historical raw CSV, never choose an arbitrary timestamp."""
    matches = sorted((root / "raw").glob("retirement_*.csv"))
    if len(matches) != 1:
        raise comparison_error(
            function="locate_single_raw_evidence",
            category="dependency" if not matches else "contract",
            code="MISSING_GREEDY_RAW_EVIDENCE" if not matches else "AMBIGUOUS_GREEDY_RAW_EVIDENCE",
            expected="exactly one retirement_*.csv in input raw directory",
            actual=[str(p) for p in matches],
            details=f"rule={rule}; root={root}",
        )
    return matches[0]


def validate_greedy_evidence_row(
    *,
    row: dict[str, str], rule: str,
    robots: int, tasks: int, max_rounds: int, seeds: int,
) -> tuple[int, float]:
    """Validate source identity, row arithmetic and the original one-task rule."""
    try:
        seed = int(row["seed"])
        n_robots = int(row["robots"])
        n_tasks = int(row["tasks"])
        n_rounds = int(row["max_rounds"])
        p_cost = float(row["p_cost_loss"])
        p_vote = float(row["p_vote_loss"])
        full = int(row["full_assignment_success"])
        completed = int(row["committed_tasks"])
        commit_rate = float(row["task_commit_rate"])
        greedy_accuracy = float(row["greedy_correct_executor_rate"])
        cost = float(row["total_cost"])
        greedy_cost = float(row["greedy_reference_cost"])
        executed = int(row["rounds_executed"])
        elapsed = float(row["total_elapsed_ms"])
        messages = int(row["logical_message_count"])
        payload = int(row["payload_bytes"])
        failed_attempts = int(row["quorum_failed_attempts"])
        safety = int(row["safety_failures"])
        cost_attempts, cost_dropped = int(row["cost_packet_attempts"]), int(row["cost_packet_dropped"])
        vote_attempts, vote_dropped = int(row["remote_vote_attempts"]), int(row["remote_vote_dropped"])
    except (KeyError, TypeError, ValueError) as exc:
        raise comparison_error(
            function="validate_greedy_evidence_row", category="data",
            code="INVALID_GREEDY_RAW_VALUE",
            expected="parseable complete raw Greedy row",
            actual=str(exc), details=f"rule={rule}; seed={row.get('seed')}",
        ) from exc

    declared_rule = row.get("vote_decision_rule", "")
    # The original 51%-majority source predates this optional explicit column.
    rule_ok = declared_rule == rule or (
        rule == "strict_majority" and declared_rule == ""
    )
    identity_ok = (
        row["method"] == METHODS[rule] and rule_ok
        and row.get("git_sha", "").strip()
        and n_robots == robots and n_tasks == tasks
        and n_rounds == max_rounds and 0 <= seed < seeds
        and math.isfinite(p_cost) and math.isfinite(p_vote)
        and 0 <= p_cost <= 1 and abs(p_cost - p_vote) < 1e-12
    )
    accounting_ok = (
        full in (0, 1) and 0 <= completed <= tasks
        and bool(full) == (completed == tasks)
        and math.isfinite(commit_rate)
        and math.isclose(commit_rate, completed / tasks, abs_tol=1e-9)
        and math.isfinite(greedy_accuracy) and 0 <= greedy_accuracy <= 1
        and math.isfinite(cost) and cost >= 0
        and math.isfinite(greedy_cost) and greedy_cost > 0
        and 1 <= executed <= max_rounds
        and math.isfinite(elapsed) and elapsed >= 0
        and messages >= 0 and payload >= 0 and failed_attempts >= 0
        and safety == 0
        and 0 <= cost_dropped <= cost_attempts
        and 0 <= vote_dropped <= vote_attempts
    )
    if not identity_ok or not accounting_ok:
        raise comparison_error(
            function="validate_greedy_evidence_row", category="contract",
            code="GREEDY_RAW_CONTRACT_MISMATCH",
            expected={
                "rule": rule, "method": METHODS[rule],
                "robots": robots, "tasks": tasks, "max_rounds": max_rounds,
                "seed_range": f"0..{seeds - 1}",
                "diagonal_loss": True, "safety_failures": 0,
                "commit_accounting": "full == (committed==tasks)",
            },
            actual={
                "method": row["method"], "declared_rule": declared_rule,
                "robots": n_robots, "tasks": n_tasks, "max_rounds": n_rounds,
                "seed": seed, "p_cost": p_cost, "p_vote": p_vote,
                "full": full, "committed": completed, "safety_failures": safety,
                "identity_ok": bool(identity_ok), "accounting_ok": bool(accounting_ok),
            },
        )
    return seed, p_cost


def read_greedy_raw_evidence(
    *,
    path: Path, rule: str, robots: int, tasks: int, seeds: int,
    max_rounds: int, losses: tuple[float, ...],
) -> tuple[dict[tuple[int, float], dict[str, str]], str]:
    """Validate one source revision and exact coverage on the selected loss axis."""
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames or ()))
        if missing:
            raise comparison_error(
                function="read_greedy_raw_evidence", category="dependency",
                code="MISSING_GREEDY_RAW_COLUMNS",
                expected=sorted(REQUIRED_COLUMNS), actual=missing,
                details=str(path),
            )
        selected: dict[tuple[int, float], dict[str, str]] = {}
        all_keys: set[tuple[int, float]] = set()
        revisions: set[str] = set()
        for row in reader:
            seed, p_loss = validate_greedy_evidence_row(
                row=row, rule=rule, robots=robots, tasks=tasks,
                max_rounds=max_rounds, seeds=seeds,
            )
            key = seed, p_loss
            if key in all_keys:
                raise comparison_error(
                    function="read_greedy_raw_evidence", category="contract",
                    code="DUPLICATE_GREEDY_SEED_CONDITION",
                    expected="one original row for each seed and Cost=Vote loss",
                    actual=key, details=str(path),
                )
            all_keys.add(key)
            revisions.add(row["git_sha"])
            if p_loss in losses:
                selected[key] = row

    expected = {(seed, p) for seed in range(seeds) for p in losses}
    if len(revisions) != 1 or selected.keys() != expected:
        raise comparison_error(
            function="read_greedy_raw_evidence", category="contract",
            code="GREEDY_SEED_LOSS_COVERAGE_MISMATCH",
            expected={"seeds": seeds, "losses": losses, "count": len(expected),
                      "source_revisions": 1},
            actual={"keys": len(selected), "missing": sorted(expected - selected.keys())[:12],
                    "extra": sorted(selected.keys() - expected)[:12],
                    "source_revisions": sorted(revisions)},
            details=str(path),
        )
    return selected, next(iter(revisions))


def validate_paired_greedy_scenarios(
    *,
    evidence: dict[str, dict[tuple[int, float], dict[str, str]]],
    losses: tuple[float, ...], seeds: int,
) -> None:
    """Prove both archives have identical per-seed zero-loss Greedy references."""
    for seed in range(seeds):
        base = evidence["strict_majority"][(seed, 0.0)]
        quarter_base = evidence["quarter_plurality"][(seed, 0.0)]
        reference = float(base["greedy_reference_cost"])
        for rule in RULES:
            for loss in losses:
                row = evidence[rule][(seed, loss)]
                if not math.isclose(
                    float(row["greedy_reference_cost"]), reference,
                    rel_tol=1e-10, abs_tol=1e-8,
                ):
                    raise comparison_error(
                        function="validate_paired_greedy_scenarios",
                        category="contract", code="PAIRED_GREEDY_SCENE_MISMATCH",
                        expected=reference,
                        actual=row["greedy_reference_cost"],
                        details=f"seed={seed}; loss={loss}; rule={rule}",
                    )
        for rule, zero in (("strict_majority", base), ("quarter_plurality", quarter_base)):
            if not (
                int(zero["full_assignment_success"]) == 1
                and math.isclose(float(zero["total_cost"]), reference, rel_tol=1e-10, abs_tol=1e-8)
                and math.isclose(float(zero["greedy_correct_executor_rate"]), 1.0, abs_tol=1e-12)
            ):
                raise comparison_error(
                    function="validate_paired_greedy_scenarios",
                    category="contract", code="ZERO_LOSS_GREEDY_BASELINE_MISMATCH",
                    expected="every seed fully assigned to identical full-information Greedy at 0% loss",
                    actual={"seed": seed, "rule": rule, "full": zero["full_assignment_success"],
                            "actual_cost": zero["total_cost"],
                            "greedy_reference_cost": reference,
                            "greedy_correct_executor_rate": zero["greedy_correct_executor_rate"]},
                )


def build_greedy_per_seed_rows(
    *,
    evidence: dict[str, dict[tuple[int, float], dict[str, str]]],
    losses: tuple[float, ...], seeds: int,
) -> list[dict[str, object]]:
    """Compare ONLY each algorithm with its own matching zero-loss Greedy run."""
    rows: list[dict[str, object]] = []
    for rule in RULES:
        for loss in losses:
            for seed in range(seeds):
                row = evidence[rule][(seed, loss)]
                baseline = evidence[rule][(seed, 0.0)]
                full = int(row["full_assignment_success"])
                cost = float(row["total_cost"])
                baseline_cost = float(baseline["total_cost"])
                delta_cost = (
                    (cost / baseline_cost - 1) * 100 if full else float("nan")
                )
                rows.append({
                    "seed": seed,
                    "robots": int(row["robots"]),
                    "tasks": int(row["tasks"]),
                    "max_rounds": int(row["max_rounds"]),
                    "p_cost_loss": loss,
                    "p_vote_loss": loss,
                    "vote_decision_rule": rule,
                    "method": METHODS[rule],
                    "source_git_sha": row["git_sha"],
                    "full_assignment_success": full,
                    "committed_tasks": int(row["committed_tasks"]),
                    "task_commit_rate": float(row["task_commit_rate"]),
                    "greedy_correct_executor_rate": float(row["greedy_correct_executor_rate"]),
                    "greedy_correctness_among_committed": float(
                        row.get("greedy_correctness_among_committed") or "nan"
                    ),
                    "cost_comparison_eligible": full,
                    "total_cost_complete_only": cost if full else float("nan"),
                    "no_loss_greedy_cost": baseline_cost,
                    "cost_degradation_vs_own_zero_loss_pct": delta_cost,
                    "rounds_executed": int(row["rounds_executed"]),
                    "failed_vote_attempts": int(row["quorum_failed_attempts"]),
                    "elapsed_ms": float(row["total_elapsed_ms"]),
                    "elapsed_extra_vs_own_zero_loss_ms": (
                        float(row["total_elapsed_ms"]) - float(baseline["total_elapsed_ms"])
                    ),
                    "logical_messages": int(row["logical_message_count"]),
                    "extra_messages_vs_own_zero_loss": (
                        int(row["logical_message_count"]) - int(baseline["logical_message_count"])
                    ),
                    "payload_bytes": int(row["payload_bytes"]),
                    "extra_payload_vs_own_zero_loss_bytes": (
                        int(row["payload_bytes"]) - int(baseline["payload_bytes"])
                    ),
                    "cost_packet_attempts": int(row["cost_packet_attempts"]),
                    "cost_packet_dropped": int(row["cost_packet_dropped"]),
                    "remote_vote_attempts": int(row["remote_vote_attempts"]),
                    "remote_vote_dropped": int(row["remote_vote_dropped"]),
                })
    return rows


def finite_mean(values) -> float:
    usable = [float(v) for v in values if math.isfinite(float(v))]
    return statistics.fmean(usable) if usable else float("nan")


def summarize_greedy_rule_curves(
    *,
    rows: list[dict[str, object]], losses: tuple[float, ...],
    seeds: int,
) -> list[dict[str, object]]:
    """Do not include incomplete assignments in any full-batch cost average."""
    summaries = []
    for rule in RULES:
        for loss in losses:
            selected = [
                row for row in rows
                if row["vote_decision_rule"] == rule and row["p_cost_loss"] == loss
            ]
            full_count = sum(int(r["full_assignment_success"]) for r in selected)
            cost_attempts = sum(int(r["cost_packet_attempts"]) for r in selected)
            vote_attempts = sum(int(r["remote_vote_attempts"]) for r in selected)
            summaries.append({
                "robots": selected[0]["robots"],
                "tasks": selected[0]["tasks"],
                "seeds": seeds,
                "p_cost_loss": loss,
                "p_vote_loss": loss,
                "vote_decision_rule": rule,
                "source_git_sha": selected[0]["source_git_sha"],
                "full_assignment_success_rate": full_count / seeds,
                "complete_case_cost_count": full_count,
                "mean_task_commit_rate": statistics.fmean(r["task_commit_rate"] for r in selected),
                "mean_greedy_correct_executor_rate": statistics.fmean(
                    r["greedy_correct_executor_rate"] for r in selected
                ),
                "mean_greedy_correctness_among_committed": finite_mean(
                    r["greedy_correctness_among_committed"] for r in selected
                ),
                "mean_cost_degradation_vs_own_zero_loss_pct_complete_only": finite_mean(
                    r["cost_degradation_vs_own_zero_loss_pct"] for r in selected
                ),
                "mean_rounds_executed": statistics.fmean(r["rounds_executed"] for r in selected),
                "mean_failed_vote_attempts": statistics.fmean(
                    r["failed_vote_attempts"] for r in selected
                ),
                "mean_elapsed_ms": statistics.fmean(r["elapsed_ms"] for r in selected),
                "mean_elapsed_extra_vs_own_zero_loss_ms": statistics.fmean(
                    r["elapsed_extra_vs_own_zero_loss_ms"] for r in selected
                ),
                "mean_logical_messages": statistics.fmean(r["logical_messages"] for r in selected),
                "mean_extra_messages_vs_own_zero_loss": statistics.fmean(
                    r["extra_messages_vs_own_zero_loss"] for r in selected
                ),
                "mean_payload_bytes": statistics.fmean(r["payload_bytes"] for r in selected),
                "mean_extra_payload_vs_own_zero_loss_bytes": statistics.fmean(
                    r["extra_payload_vs_own_zero_loss_bytes"] for r in selected
                ),
                "observed_cost_loss": (
                    sum(int(r["cost_packet_dropped"]) for r in selected) / cost_attempts
                    if cost_attempts else float("nan")
                ),
                "observed_vote_loss": (
                    sum(int(r["remote_vote_dropped"]) for r in selected) / vote_attempts
                    if vote_attempts else float("nan")
                ),
            })
    return summaries


def summarize_paired_protocol_differences(
    *,
    rows: list[dict[str, object]], losses: tuple[float, ...],
    seeds: int,
) -> list[dict[str, object]]:
    """Use identical seed subsets for protocol differences and cost comparisons."""
    keyed = {
        (r["vote_decision_rule"], r["seed"], r["p_cost_loss"]): r
        for r in rows
    }
    summaries = []
    for loss in losses:
        pairs = [
            (keyed[("strict_majority", seed, loss)],
             keyed[("quarter_plurality", seed, loss)])
            for seed in range(seeds)
        ]
        both = [
            (majority, quarter) for majority, quarter in pairs
            if majority["full_assignment_success"] and quarter["full_assignment_success"]
        ]
        only_quarter = sum(int(not a["full_assignment_success"] and b["full_assignment_success"]) for a, b in pairs)
        only_majority = sum(int(a["full_assignment_success"] and not b["full_assignment_success"]) for a, b in pairs)
        neither = sum(int(not a["full_assignment_success"] and not b["full_assignment_success"]) for a, b in pairs)
        majority_full = sum(int(a["full_assignment_success"]) for a, _ in pairs)
        quarter_full = sum(int(b["full_assignment_success"]) for _, b in pairs)
        summaries.append({
            "robots": pairs[0][0]["robots"],
            "tasks": pairs[0][0]["tasks"],
            "paired_seeds": seeds,
            "p_cost_loss": loss,
            "p_vote_loss": loss,
            "majority_full_assignment_success_rate": majority_full / seeds,
            "quarter_full_assignment_success_rate": quarter_full / seeds,
            "quarter_minus_majority_full_success_percentage_points": (
                (quarter_full - majority_full) / seeds * 100
            ),
            "both_completed_count": len(both),
            "only_quarter_completed_count": only_quarter,
            "only_majority_completed_count": only_majority,
            "neither_completed_count": neither,
            "mean_quarter_minus_majority_cost_pct_of_no_loss_greedy_common_completed": finite_mean(
                (b["total_cost_complete_only"] - a["total_cost_complete_only"])
                / a["no_loss_greedy_cost"] * 100 for a, b in both
            ),
            "mean_quarter_minus_majority_greedy_executor_accuracy_percentage_points": (
                statistics.fmean(
                    b["greedy_correct_executor_rate"] - a["greedy_correct_executor_rate"]
                    for a, b in pairs
                ) * 100
            ),
            "mean_quarter_minus_majority_elapsed_ms": statistics.fmean(
                b["elapsed_ms"] - a["elapsed_ms"] for a, b in pairs
            ),
            "mean_quarter_minus_majority_messages": statistics.fmean(
                b["logical_messages"] - a["logical_messages"] for a, b in pairs
            ),
            "mean_quarter_minus_majority_payload_bytes": statistics.fmean(
                b["payload_bytes"] - a["payload_bytes"] for a, b in pairs
            ),
        })
    return summaries


def write_greedy_only_comparison(
    *,
    output_root: Path, source_files: dict[str, Path],
    source_revisions: dict[str, str],
    losses: tuple[float, ...], seeds: int,
    per_seed: list[dict[str, object]],
    curves: list[dict[str, object]],
    paired: list[dict[str, object]],
) -> None:
    """Write a NEW derived report; the historical raw files are immutable."""
    resolved_output = output_root.resolve()
    source_roots = {p.parent.parent.resolve() for p in source_files.values()}
    if any(
        resolved_output == source_root
        or source_root in resolved_output.parents
        or resolved_output in source_root.parents
        for source_root in source_roots
    ):
        raise comparison_error(
            function="write_greedy_only_comparison", category="state",
            code="GREEDY_ANALYSIS_SOURCE_OUTPUT_COLLISION",
            expected="a new report directory outside both historical source trees",
            actual=str(output_root),
        )
    if output_root.exists() and (
        not output_root.is_dir()
        or any(p.name != "README.md" for p in output_root.iterdir())
    ):
        raise comparison_error(
            function="write_greedy_only_comparison", category="state",
            code="GREEDY_ANALYSIS_OUTPUT_EXISTS",
            expected="new/README-only report root, no previous generated CSVs",
            actual=str(output_root),
        )
    output_root.mkdir(parents=True, exist_ok=True)
    write_csv(output_root / "greedy_per_seed.csv", per_seed)
    write_csv(output_root / "greedy_rule_curve.csv", curves)
    write_csv(output_root / "greedy_protocol_delta.csv", paired)
    manifest = {
        "format_version": 1,
        "analysis_git_sha": read_retirement_revision(),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "robots": per_seed[0]["robots"], "tasks": per_seed[0]["tasks"],
        "max_rounds": per_seed[0]["max_rounds"], "seeds": seeds,
        "loss_probabilities_cost_equals_vote": list(losses),
        "reference": "same-seed fully assigned zero-loss sequential Greedy only",
        "cost_denominator": "only fully assigned runs; no missing-task penalty imputed",
        "rules": list(RULES),
        "paired_protocol_comparison": "only identical seed/loss pairs; cost only if BOTH full",
        "source_evidence": {
            rule: {
                "raw_csv": str(source_files[rule]),
                "source_git_sha": source_revisions[rule],
                "raw_sha256": hashlib.sha256(source_files[rule].read_bytes()).hexdigest(),
            }
            for rule in RULES
        },
        "limitations": [
            "Cost and Vote losses share a numeric probability but packet draws are independent",
            "Original historical majority rows may omit vote_decision_rule; method identifies strict majority",
            "Qualified candidate announcements and commits remain modeled as reliable",
            "Communication elapsed_ms is simulated coordination time, not Python wall-clock runtime",
            "No Hungarian reference or optimality-gap metric is used in this derived report",
        ],
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def compare_existing_greedy_evidence(
    *,
    majority_root: Path = DEFAULT_MAJORITY,
    quarter_root: Path = DEFAULT_QUARTER,
    output_root: Path = DEFAULT_OUTPUT,
    robots: int = 100, tasks: int = 50,
    max_rounds: int = 100, seeds: int = 100,
    losses: tuple[float, ...] = DEFAULT_LOSSES,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Orchestrate read -> validate pairs -> Greedy-only derive -> isolated write."""
    validate_comparison_configuration(
        robots=robots, tasks=tasks, seeds=seeds,
        max_rounds=max_rounds, losses=losses,
    )
    roots = {"strict_majority": majority_root, "quarter_plurality": quarter_root}
    source_files = {
        rule: locate_single_raw_evidence(root=roots[rule], rule=rule)
        for rule in RULES
    }
    evidence = {}
    revisions = {}
    for rule in RULES:
        evidence[rule], revisions[rule] = read_greedy_raw_evidence(
            path=source_files[rule], rule=rule,
            robots=robots, tasks=tasks, max_rounds=max_rounds,
            seeds=seeds, losses=losses,
        )
    validate_paired_greedy_scenarios(evidence=evidence, losses=losses, seeds=seeds)
    per_seed = build_greedy_per_seed_rows(evidence=evidence, losses=losses, seeds=seeds)
    curves = summarize_greedy_rule_curves(rows=per_seed, losses=losses, seeds=seeds)
    paired = summarize_paired_protocol_differences(rows=per_seed, losses=losses, seeds=seeds)
    write_greedy_only_comparison(
        output_root=output_root, source_files=source_files, source_revisions=revisions,
        losses=losses, seeds=seeds, per_seed=per_seed, curves=curves, paired=paired,
    )
    print(f"GREEDY_ONLY_COMPLETE rules=2 seeds={seeds} losses={len(losses)} "
          f"source_rows={len(per_seed)} paired_conditions={len(paired)}")
    print(f"GREEDY_ONLY_OUTPUT_ROOT={output_root}")
    for row in paired:
        print(
            "GREEDY_PROTOCOL_COMPARE "
            f"loss={row['p_cost_loss']:.2f} "
            f"majority_full={row['majority_full_assignment_success_rate']:.4f} "
            f"quarter_full={row['quarter_full_assignment_success_rate']:.4f} "
            f"improvement_pp={row['quarter_minus_majority_full_success_percentage_points']:.2f} "
            f"both_completed={row['both_completed_count']}/{seeds}"
        )
    return curves, paired


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze two existing E2 raw archives using zero-loss Greedy only"
    )
    parser.add_argument("--majority-root", type=Path, default=DEFAULT_MAJORITY)
    parser.add_argument("--quarter-root", type=Path, default=DEFAULT_QUARTER)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--robots", type=int, default=100)
    parser.add_argument("--tasks", type=int, default=50)
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--max-rounds", type=int, default=100)
    parser.add_argument(
        "--loss-probabilities", type=parse_probabilities, default=DEFAULT_LOSSES,
        help="Same numeric Cost/Vote loss levels, sorted, must include zero",
    )
    args = parser.parse_args()
    compare_existing_greedy_evidence(
        majority_root=args.majority_root, quarter_root=args.quarter_root,
        output_root=args.output_root, robots=args.robots, tasks=args.tasks,
        max_rounds=args.max_rounds, seeds=args.seeds, losses=args.loss_probabilities,
    )


if __name__ == "__main__":
    main()
