"""E9A: READ-ONLY observed transmitted-byte calibration for Greedy 25% vs CBAA.

This does not simulate, throttle, stop, choose winners, or alter any agent.
It compares previously recorded physical SEND payload, not per-recipient copies.
Only p=0 Greedy bytes choose a CBAA iteration configuration, without looking
at CBAA success or at the selected loss condition's outcomes. Until BOTH
methods have a runtime byte cap and equivalent failure/control-message models,
this is calibration/feasibility evidence, NOT a causal equal-budget benchmark.
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


OWNER = "experiments.compare_cbaa_budget"
DEFAULT_QUARTER = Path("results/e2_greedy_quarter_plurality_no_fallback_100r50t")
DEFAULT_CBAA = (Path("results/e8_cbaa_100r50t_pilot"),)
DEFAULT_OUTPUT = Path("results/e9_cbaa_budget_calibration")
DEFAULT_LOSSES = (0.0, 0.30, 0.50)
E2_METHOD = "democracy_greedy_quarter_plurality_retirement"
CBAA_METHOD = "cbaa_sync_single_assignment"
GREEDY_REQUIRED = frozenset({
    "seed", "git_sha", "robots", "tasks", "max_rounds", "method",
    "vote_decision_rule", "p_cost_loss", "p_vote_loss",
    "full_assignment_success", "committed_tasks", "task_commit_rate",
    "greedy_correct_executor_rate", "greedy_reference_cost",
    "payload_bytes", "logical_message_count", "total_elapsed_ms", "safety_failures",
})
CBAA_REQUIRED = frozenset({
    "seed", "git_sha", "robots", "tasks", "method", "score_rule", "communication",
    "p_consensus_loss", "max_iterations", "iterations",
    "full_observer_agreement", "task_agreement_rate",
    "observer_agreed_task_count", "observer_unconfirmed_task_count",
    "local_duplicate_claim_task_count", "local_claim_count",
    "greedy_reference_cost", "payload_bytes", "logical_message_count",
    "elapsed_ms", "delivery_attempts", "delivery_drops", "late_deliveries",
})


def budget_error(
    *,
    function: str, category: str, code: str,
    expected: object, actual: object, details: str = "",
) -> ProtocolError:
    return ProtocolError(Diagnostic(
        owner=OWNER, function=function, category=category, code=code,
        expected=expected, actual=actual, details=details,
    ))


def validate_budget_calibration_config(
    *,
    robots: int, tasks: int, seeds: int, max_rounds: int,
    losses: tuple[float, ...], tolerance: float,
    cbaa_roots: tuple[Path, ...],
) -> None:
    """Require a valid selected paired grid before reading evidence."""
    if (
        type(robots) is not int or type(tasks) is not int
        or type(seeds) is not int or type(max_rounds) is not int
        or not 1 <= tasks <= robots <= 100 or seeds < 1 or max_rounds < tasks
    ):
        raise budget_error(
            function="validate_budget_calibration_config", category="data",
            code="INVALID_BUDGET_CALIBRATION_SHAPE",
            expected="1 <= tasks <= robots <= 100, seeds >= 1, max_rounds >= tasks",
            actual=(robots, tasks, seeds, max_rounds),
        )
    if (
        not losses or losses[0] != 0.0
        or tuple(sorted(set(losses))) != losses
        or any(type(x) not in (int, float) or not math.isfinite(x) or x < 0 or x > 1
               for x in losses)
        or type(tolerance) not in (int, float)
        or not math.isfinite(tolerance) or not 0 <= tolerance < 1
        or not cbaa_roots
        or len({p.resolve() for p in cbaa_roots}) != len(cbaa_roots)
    ):
        raise budget_error(
            function="validate_budget_calibration_config", category="data",
            code="INVALID_BUDGET_CALIBRATION_GRID",
            expected="sorted unique p axis starting at 0; 0<=tolerance<1; unique CBAA roots",
            actual={"losses": losses, "tolerance": tolerance,
                    "cbaa_roots": [str(p) for p in cbaa_roots]},
        )


def locate_budget_source_file(*, root: Path, source: str) -> Path:
    """Read exactly one timestamped source file, not whichever sort comes last."""
    pattern = "retirement_*.csv" if source == "quarter" else "cbaa_*.csv"
    files = sorted((root / "raw").glob(pattern))
    if len(files) != 1:
        raise budget_error(
            function="locate_budget_source_file",
            category="dependency" if not files else "contract",
            code="MISSING_BUDGET_SOURCE_CSV" if not files else "AMBIGUOUS_BUDGET_SOURCE_CSV",
            expected=f"exactly one raw/{pattern} per source directory",
            actual=[str(path) for path in files],
            details=f"source={source}; root={root}",
        )
    return files[0]


def validate_budget_source_row(
    *,
    row: dict[str, str], source: str,
    robots: int, tasks: int, max_rounds: int,
) -> tuple[int, float, int | None]:
    """Reject first malformed physical accounting or false algorithm identity."""
    func = "validate_budget_source_row"
    try:
        seed = int(row["seed"])
        r, t = int(row["robots"]), int(row["tasks"])
        sha = row["git_sha"].strip()
        bytes_sent = int(row["payload_bytes"])
        messages = int(row["logical_message_count"])
        cost = float(row["greedy_reference_cost"])
        if source == "quarter":
            p = float(row["p_cost_loss"])
            p_vote = float(row["p_vote_loss"])
            rounds = int(row["max_rounds"])
            full = int(row["full_assignment_success"])
            committed = int(row["committed_tasks"])
            task_rate = float(row["task_commit_rate"])
            accuracy = float(row["greedy_correct_executor_rate"])
            elapsed = float(row["total_elapsed_ms"])
            safety = int(row["safety_failures"])
            repetition = int(row.get("vote_repetitions") or "1")
            coherent = (
                row["method"] == E2_METHOD
                and row["vote_decision_rule"] == "quarter_plurality"
                and rounds == max_rounds and repetition == 1
                and abs(p - p_vote) < 1e-9
                and full in (0, 1) and 0 <= committed <= tasks
                and full == int(committed == tasks)
                and math.isfinite(task_rate)
                and math.isclose(task_rate, committed / tasks, abs_tol=1e-9)
                and math.isfinite(accuracy) and 0 <= accuracy <= 1
                and safety == 0 and math.isfinite(elapsed) and elapsed >= 0
            )
            iterations = None
        else:
            p = float(row["p_consensus_loss"])
            iterations = int(row["max_iterations"])
            actual_iterations = int(row["iterations"])
            full = int(row["full_observer_agreement"])
            agreed = int(row["observer_agreed_task_count"])
            unconfirmed = int(row["observer_unconfirmed_task_count"])
            conflict = int(row["local_duplicate_claim_task_count"])
            claims = int(row["local_claim_count"])
            task_rate = float(row["task_agreement_rate"])
            elapsed = float(row["elapsed_ms"])
            attempts = int(row["delivery_attempts"])
            drops = int(row["delivery_drops"])
            late = int(row["late_deliveries"])
            expected_messages = r * iterations
            expected_bytes = expected_messages * (16 + t * (8 + 4))
            coherent = (
                row["method"] == CBAA_METHOD
                and row["score_rule"] == "1/(1+nonnegative_cost)"
                and row["communication"] == "synchronous_complete_graph_broadcast"
                and iterations >= 1 and actual_iterations == iterations
                and full in (0, 1) and 0 <= agreed <= t
                and 0 <= unconfirmed <= t
                and agreed + unconfirmed == t
                and 0 <= conflict <= unconfirmed
                and 0 <= claims <= r
                and full == int(unconfirmed == 0 and conflict == 0)
                and math.isfinite(task_rate)
                and math.isclose(task_rate, agreed / t, abs_tol=1e-9)
                and math.isfinite(elapsed) and elapsed >= 0
                and messages == expected_messages and bytes_sent == expected_bytes
                and attempts == messages * (r - 1)
                and 0 <= drops <= attempts and 0 <= late <= attempts - drops
            )
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        raise budget_error(
            function=func, category="data", code="INVALID_BUDGET_SOURCE_VALUE",
            expected="parseable source raw row and measured physical send counters",
            actual=str(exc), details=f"source={source}; seed={row.get('seed')}",
        ) from exc
    if (
        not coherent or r != robots or t != tasks
        or seed < 0 or not sha or not math.isfinite(p) or not 0 <= p <= 1
        or bytes_sent < 0 or messages < 0
        or not math.isfinite(cost) or cost <= 0
    ):
        raise budget_error(
            function=func, category="contract", code="BUDGET_SOURCE_CONTRACT_MISMATCH",
            expected={"source": source, "robots": robots, "tasks": tasks,
                      "nonnegative_physical_send_bytes": True,
                      "loss_in_0_1": True, "valid_algorithm_method": True},
            actual={"source": source, "seed": seed, "p": p, "robots": r,
                    "tasks": t, "bytes": bytes_sent, "messages": messages,
                    "coherent": bool(coherent), "sha": sha},
        )
    return seed, round(p, 10), iterations


def read_budget_source(
    *,
    path: Path, source: str, robots: int, tasks: int,
    seeds: int, max_rounds: int, losses: tuple[float, ...],
) -> tuple[dict[tuple[int, float], dict[str, str]], str, int | None]:
    """A selected seed subset of an IMMUTABLE 100-seed historical source.

    Require exact requested (seed, loss) coverage, one source SHA and one
    CBAA iteration count per input root. Remaining historical seeds/losses
    are left unmodified; selecting them later requires a new analysis root.
    """
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = GREEDY_REQUIRED if source == "quarter" else CBAA_REQUIRED
        missing = sorted(required - set(reader.fieldnames or ()))
        if missing:
            raise budget_error(
                function="read_budget_source", category="dependency",
                code="MISSING_BUDGET_SOURCE_COLUMNS",
                expected=sorted(required), actual=missing, details=str(path),
            )
        selected: dict[tuple[int, float], dict[str, str]] = {}
        revisions: set[str] = set()
        budgets: set[int] = set()
        for row in reader:
            seed, p, iterations = validate_budget_source_row(
                row=row, source=source, robots=robots, tasks=tasks, max_rounds=max_rounds,
            )
            revisions.add(row["git_sha"].strip())
            if iterations is not None:
                budgets.add(iterations)
            if seed >= seeds or p not in losses:
                continue
            key = seed, p
            if key in selected:
                raise budget_error(
                    function="read_budget_source", category="contract",
                    code="DUPLICATE_BUDGET_SEED_LOSS",
                    expected="one source row per selected seed and loss",
                    actual=key, details=str(path),
                )
            selected[key] = row
    expected = {(seed, p) for seed in range(seeds) for p in losses}
    if selected.keys() != expected or len(revisions) != 1 or (
        source == "cbaa" and len(budgets) != 1
    ):
        raise budget_error(
            function="read_budget_source", category="contract",
            code="BUDGET_SOURCE_COVERAGE_MISMATCH",
            expected={"selected_seed_loss": len(expected), "source_sha_count": 1,
                      "CBAA_iteration_count": 1 if source == "cbaa" else None},
            actual={"selected_seed_loss": len(selected),
                    "missing": sorted(expected - selected.keys())[:10],
                    "source_revisions": sorted(revisions),
                    "iteration_values": sorted(budgets)}, details=str(path),
        )
    return selected, next(iter(revisions)), next(iter(budgets)) if budgets else None


def validate_paired_budget_scenes(
    *,
    quarter: dict[tuple[int, float], dict[str, str]],
    cbaa_by_iteration: dict[int, dict[tuple[int, float], dict[str, str]]],
    seeds: int, losses: tuple[float, ...],
) -> None:
    """Verify identical geometry Greedy reference, never impute missing data."""
    for seed in range(seeds):
        ref = float(quarter[seed, 0.0]["greedy_reference_cost"])
        for p in losses:
            source_ref = float(quarter[seed, p]["greedy_reference_cost"])
            if not math.isclose(ref, source_ref, rel_tol=1e-10, abs_tol=1e-8):
                raise budget_error(
                    function="validate_paired_budget_scenes", category="contract",
                    code="BUDGET_PAIRED_SCENARIO_MISMATCH",
                    expected=ref, actual=source_ref,
                    details=f"quarter seed={seed}, loss={p}",
                )
            if p == 0.0 and (
                int(quarter[seed, p]["full_assignment_success"]) != 1
                or not math.isclose(
                    float(quarter[seed, p]["greedy_correct_executor_rate"]),
                    1.0, abs_tol=1e-9
                )
            ):
                raise budget_error(
                    function="validate_paired_budget_scenes", category="contract",
                    code="BUDGET_ZERO_LOSS_GREEDY_FAILURE",
                    expected="full 50-task Greedy match in quarter protocol at p=0",
                    actual=quarter[seed, p]["greedy_correct_executor_rate"],
                    details=f"seed={seed}",
                )
            for iterations, rows in cbaa_by_iteration.items():
                candidate_ref = float(rows[seed, p]["greedy_reference_cost"])
                if not math.isclose(ref, candidate_ref, rel_tol=1e-10, abs_tol=1e-8):
                    raise budget_error(
                        function="validate_paired_budget_scenes", category="contract",
                        code="BUDGET_PAIRED_SCENARIO_MISMATCH",
                        expected=ref, actual=candidate_ref,
                        details=f"cbaa_iterations={iterations}, seed={seed}, loss={p}",
                    )


def calibrate_cbaa_send_budget(
    *,
    quarter: dict[tuple[int, float], dict[str, str]],
    cbaa_by_iteration: dict[int, dict[tuple[int, float], dict[str, str]]],
    seeds: int, tolerance: float,
) -> tuple[list[dict[str, object]], int]:
    """Choose closest CBAA iteration budget using ONLY zero-loss SEND bytes.

    No loss-specific success, task rate or later p is consulted for selection;
    an unqualified configuration is still reported, never silently promoted
    to a match or a "best-performing CBAA".
    """
    baseline_bytes = statistics.fmean(
        int(quarter[seed, 0.0]["payload_bytes"]) for seed in range(seeds)
    )
    if baseline_bytes <= 0:
        raise budget_error(
            function="calibrate_cbaa_send_budget", category="contract",
            code="BUDGET_ZERO_TRANSMISSION_REFERENCE",
            expected="positive Greedy p=0 sent payload bytes",
            actual=baseline_bytes,
        )
    options: list[dict[str, object]] = []
    for iterations, rows in sorted(cbaa_by_iteration.items()):
        cbaa_bytes = statistics.fmean(
            int(rows[seed, 0.0]["payload_bytes"]) for seed in range(seeds)
        )
        relative_gap = (cbaa_bytes - baseline_bytes) / baseline_bytes
        options.append({
            "iterations": iterations,
            "greedy_zero_loss_mean_sent_bytes": baseline_bytes,
            "cbaa_zero_loss_mean_sent_bytes": cbaa_bytes,
            "cbaa_minus_greedy_zero_loss_fraction": relative_gap,
            "abs_relative_gap": abs(relative_gap),
            "within_zero_loss_calibration_tolerance": int(abs(relative_gap) <= tolerance),
        })
    selected = min(options, key=lambda x: (x["abs_relative_gap"], x["iterations"]))
    for item in options:
        item["selected_by_zero_loss_bytes_only"] = int(item is selected)
    return options, int(selected["iterations"])


def build_budget_observation_rows(
    *,
    quarter: dict[tuple[int, float], dict[str, str]],
    cbaa_by_iteration: dict[int, dict[tuple[int, float], dict[str, str]]],
    seeds: int, losses: tuple[float, ...],
    tolerance: float, selected_iterations: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Report full/partial success alongside physical sending cost on SAME seeds."""
    per_seed: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    for iterations, cbaa in sorted(cbaa_by_iteration.items()):
        for p in losses:
            selected_rows = []
            for seed in range(seeds):
                g, c = quarter[seed, p], cbaa[seed, p]
                g_bytes, c_bytes = int(g["payload_bytes"]), int(c["payload_bytes"])
                ratio = c_bytes / g_bytes if g_bytes else float("nan")
                row = {
                    "robots": int(g["robots"]),
                    "tasks": int(g["tasks"]),
                    "seed": seed,
                    "p_loss": p,
                    "cbaa_iterations": iterations,
                    "selected_by_zero_loss_bytes_only": int(iterations == selected_iterations),
                    "greedy_full_task_commit": int(g["full_assignment_success"]),
                    "cbaa_full_observer_agreement": int(c["full_observer_agreement"]),
                    "greedy_committed_tasks": int(g["committed_tasks"]),
                    "cbaa_observer_agreed_tasks": int(c["observer_agreed_task_count"]),
                    "cbaa_local_duplicate_claim_tasks": int(c["local_duplicate_claim_task_count"]),
                    "cbaa_observer_unconfirmed_tasks": int(c["observer_unconfirmed_task_count"]),
                    "greedy_sent_bytes": g_bytes,
                    "cbaa_sent_bytes": c_bytes,
                    "cbaa_to_greedy_sent_bytes_ratio": ratio,
                    "observed_bytes_within_tolerance": int(
                        math.isfinite(ratio) and abs(ratio - 1) <= tolerance
                    ),
                    "greedy_logical_messages": int(g["logical_message_count"]),
                    "cbaa_logical_messages": int(c["logical_message_count"]),
                    "greedy_elapsed_ms": float(g["total_elapsed_ms"]),
                    "cbaa_elapsed_ms": float(c["elapsed_ms"]),
                    "cbaa_receive_opportunities": int(c["delivery_attempts"]),
                    "cbaa_receive_drops": int(c["delivery_drops"]),
                }
                per_seed.append(row)
                selected_rows.append(row)
            mean = lambda key: statistics.fmean(float(r[key]) for r in selected_rows)
            ratio = mean("cbaa_sent_bytes") / mean("greedy_sent_bytes")
            summaries.append({
                "robots": selected_rows[0]["robots"],
                "tasks": selected_rows[0]["tasks"],
                "seeds": seeds,
                "p_loss": p,
                "cbaa_iterations": iterations,
                "selected_by_zero_loss_bytes_only": int(iterations == selected_iterations),
                "greedy_full_assignment_success_rate": mean("greedy_full_task_commit"),
                "cbaa_full_observer_agreement_rate": mean("cbaa_full_observer_agreement"),
                "greedy_mean_committed_task_rate": (
                    mean("greedy_committed_tasks") / selected_rows[0]["tasks"]
                ),
                "cbaa_mean_observer_agreed_task_rate": (
                    mean("cbaa_observer_agreed_tasks") / selected_rows[0]["tasks"]
                ),
                "cbaa_mean_duplicate_claim_tasks": mean("cbaa_local_duplicate_claim_tasks"),
                "greedy_mean_sent_bytes": mean("greedy_sent_bytes"),
                "cbaa_mean_sent_bytes": mean("cbaa_sent_bytes"),
                "cbaa_to_greedy_mean_bytes_ratio": ratio,
                "mean_bytes_close_within_tolerance": int(abs(ratio - 1) <= tolerance),
                "paired_seeds_bytes_close_count": sum(
                    int(r["observed_bytes_within_tolerance"]) for r in selected_rows
                ),
                "greedy_mean_messages": mean("greedy_logical_messages"),
                "cbaa_mean_messages": mean("cbaa_logical_messages"),
                "greedy_mean_elapsed_ms": mean("greedy_elapsed_ms"),
                "cbaa_mean_elapsed_ms": mean("cbaa_elapsed_ms"),
                "cbaa_mean_receive_opportunities": mean("cbaa_receive_opportunities"),
                "cbaa_mean_receive_drops": mean("cbaa_receive_drops"),
            })
    return per_seed, summaries


def write_budget_calibration(
    *,
    output_root: Path, source_files: dict[str, Path],
    source_revisions: dict[str, str], options: list[dict[str, object]],
    per_seed: list[dict[str, object]], curves: list[dict[str, object]],
    seeds: int, losses: tuple[float, ...], tolerance: float,
    selected_iterations: int,
) -> None:
    """Write new, immutable read-only derived data; never rewrite source CSV."""
    root = output_root.resolve()
    originals = [p.parent.parent.resolve() for p in source_files.values()]
    if any(
        root == src or root in src.parents or src in root.parents
        for src in originals
    ):
        raise budget_error(
            function="write_budget_calibration", category="state",
            code="BUDGET_REPORT_SOURCE_COLLISION",
            expected="new output tree separate from all source roots",
            actual=str(output_root),
        )
    if output_root.exists() and (
        not output_root.is_dir()
        or any(p.name != "README.md" for p in output_root.iterdir())
    ):
        raise budget_error(
            function="write_budget_calibration", category="state",
            code="BUDGET_REPORT_ALREADY_EXISTS",
            expected="new or README-only output directory, no previous reports",
            actual=str(output_root),
        )
    output_root.mkdir(parents=True, exist_ok=True)
    write_csv(output_root / "budget_options.csv", options)
    write_csv(output_root / "budget_per_seed.csv", per_seed)
    write_csv(output_root / "budget_curve.csv", curves)
    manifest = {
        "format_version": 1,
        "study": "E9A read-only sent-payload byte-budget calibration; NOT hard capped",
        "analysis_git_sha": read_retirement_revision(),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "seeds": seeds, "loss_probabilities": list(losses),
        "tolerance_fraction": tolerance,
        "selected_cbaa_iterations_by_zero_loss_bytes_only": selected_iterations,
        "calibrated_with": "p=0 Greedy 25% mean physical SEND payload bytes; independent of successes",
        "resource_unit": "sender-accounted application payload Bytes (one wireless broadcast counted once)",
        "source_files": {
            name: {
                "file": str(path),
                "git_sha": source_revisions[name],
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for name, path in sorted(source_files.items())
        },
        "not_claimed": [
            "No method is interrupted when it exceeds an absolute byte budget",
            "Not a hard cap and not an equal-budget causal success-rate comparison",
            "Unicast/broadcast recipient airtime, MAC collisions and radio bit rate not modeled",
            "CBAA single-stage lossy bid vectors differ from Greedy lossy Cost+Vote",
            "Greedy 25% score and Commit are reliable; CBAA has no reliable Commit",
            "Greedy full task Commit vs CBAA unanimous post-hoc observer agreement differ",
            "CBAA has fixed iterations, not a distributed early stopping protocol",
            "No cherry-picking iteration count from packet-loss success outcomes",
        ],
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def compare_cbaa_communication_budget(
    *,
    quarter_root: Path = DEFAULT_QUARTER,
    cbaa_roots: tuple[Path, ...] = DEFAULT_CBAA,
    output_root: Path = DEFAULT_OUTPUT,
    robots: int = 100, tasks: int = 50, seeds: int = 3,
    max_rounds: int = 100, losses: tuple[float, ...] = DEFAULT_LOSSES,
    tolerance: float = 0.10,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Only observe independent historical experiments; never run simulations."""
    validate_budget_calibration_config(
        robots=robots, tasks=tasks, seeds=seeds, max_rounds=max_rounds,
        losses=losses, tolerance=tolerance, cbaa_roots=cbaa_roots,
    )
    source_files = {"quarter": locate_budget_source_file(
        root=quarter_root, source="quarter"
    )}
    quarter, quarter_sha, _ = read_budget_source(
        path=source_files["quarter"], source="quarter",
        robots=robots, tasks=tasks, seeds=seeds,
        max_rounds=max_rounds, losses=losses,
    )
    revisions = {"quarter": quarter_sha}
    cbaa_by_iteration = {}
    for root in cbaa_roots:
        file = locate_budget_source_file(root=root, source="cbaa")
        data, sha, iterations = read_budget_source(
            path=file, source="cbaa",
            robots=robots, tasks=tasks, seeds=seeds,
            max_rounds=max_rounds, losses=losses,
        )
        if iterations in cbaa_by_iteration:
            raise budget_error(
                function="compare_cbaa_communication_budget", category="contract",
                code="DUPLICATE_CBAA_BUDGET_CONFIGURATION",
                expected="one raw source for each CBAA iteration count",
                actual={"iterations": iterations, "extra": str(file)},
            )
        cbaa_by_iteration[iterations] = data
        label = f"cbaa_iterations_{iterations:03d}"
        source_files[label] = file
        revisions[label] = sha

    validate_paired_budget_scenes(
        quarter=quarter, cbaa_by_iteration=cbaa_by_iteration,
        seeds=seeds, losses=losses,
    )
    options, selected = calibrate_cbaa_send_budget(
        quarter=quarter, cbaa_by_iteration=cbaa_by_iteration,
        seeds=seeds, tolerance=tolerance,
    )
    per_seed, curves = build_budget_observation_rows(
        quarter=quarter, cbaa_by_iteration=cbaa_by_iteration,
        seeds=seeds, losses=losses,
        tolerance=tolerance, selected_iterations=selected,
    )
    write_budget_calibration(
        output_root=output_root, source_files=source_files,
        source_revisions=revisions, options=options, per_seed=per_seed,
        curves=curves, seeds=seeds, losses=losses, tolerance=tolerance,
        selected_iterations=selected,
    )
    calibrated = next(item for item in options if item["selected_by_zero_loss_bytes_only"])
    print(
        "E9_BUDGET_CALIBRATION "
        f"seeds={seeds} losses={len(losses)} cbaa_options={len(options)} "
        f"selected_iterations={selected} "
        f"quarter_p0_mean_bytes={calibrated['greedy_zero_loss_mean_sent_bytes']:.0f} "
        f"cbaa_p0_mean_bytes={calibrated['cbaa_zero_loss_mean_sent_bytes']:.0f} "
        f"within_tolerance={calibrated['within_zero_loss_calibration_tolerance']} "
        f"tolerance={tolerance:.2f}"
    )
    for row in curves:
        if row["selected_by_zero_loss_bytes_only"]:
            print(
                "E9_BUDGET_OBSERVATION "
                f"loss={row['p_loss']:.2f} iterations={selected} "
                f"greedy_full={row['greedy_full_assignment_success_rate']:.4f} "
                f"cbaa_full_observer={row['cbaa_full_observer_agreement_rate']:.4f} "
                f"mean_bytes_ratio={row['cbaa_to_greedy_mean_bytes_ratio']:.3f} "
                f"close_seed_pairs={row['paired_seeds_bytes_close_count']}/{seeds}"
            )
    print(f"E9_BUDGET_OUTPUT_ROOT={output_root}")
    print("E9_BUDGET_INTERPRETATION=OBSERVED_SEND_BYTE_CALIBRATION_ONLY_NOT_HARD_CAPPED")
    return options, curves


def main() -> None:
    parser = argparse.ArgumentParser(
        description="E9A read-only observed send-Bytes budget calibration of CBAA vs Greedy25%"
    )
    parser.add_argument("--quarter-root", type=Path, default=DEFAULT_QUARTER)
    parser.add_argument("--cbaa-roots", nargs="+", type=Path, default=DEFAULT_CBAA)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--robots", type=int, default=100)
    parser.add_argument("--tasks", type=int, default=50)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--max-rounds", type=int, default=100)
    parser.add_argument("--loss-probabilities", type=parse_probabilities,
                        default=DEFAULT_LOSSES)
    parser.add_argument("--tolerance", type=float, default=0.10)
    args = parser.parse_args()
    compare_cbaa_communication_budget(
        quarter_root=args.quarter_root, cbaa_roots=tuple(args.cbaa_roots),
        output_root=args.output_root, robots=args.robots, tasks=args.tasks,
        seeds=args.seeds, max_rounds=args.max_rounds,
        losses=args.loss_probabilities, tolerance=args.tolerance,
    )


if __name__ == "__main__":
    main()
