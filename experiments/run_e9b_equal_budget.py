"""E9B-4: paired original Democracy25/CBAA under equal sender-byte hard caps.

Application payload sender Bytes are NOT radio airtime. Greedy Commit and
CBAA observer agreement are never equated or used as a shared decision.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics

from democracy_mrta.cbaa import simulate_cbaa
from democracy_mrta.coordination import simulate_democracy_hungarian_retirement
from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler, EmpiricalLatencySampler, SenderPayloadBudget,
    RADY_SOURCE_COMMIT, RADY_SOURCE_BLOB_SHA, ensure_rady_dataset,
    load_rady_latency_profile, summarize_latency_profile,
    validate_packet_loss_probability, validate_sender_payload_budget,
)
from democracy_mrta.optimizer import solve_sequential_greedy_reference
from democracy_mrta.scenario import generate_e0_scenario
from experiments.run_e2 import parse_probabilities, write_csv
from experiments.run_e2_retirement import read_retirement_revision


OWNER = "experiments.run_e9b_equal_budget"
DEFAULT_LOSSES = (0.0, 0.30, 0.50)
DEFAULT_BUDGETS = (100000, 163800, 184800, 250000, 500000, 1000000)
DEFAULT_ROOT = Path("results/e9b_equal_sender_budget_pilot")


def parse_sender_budgets(value: str) -> tuple[int, ...]:
    """Parse exact integer application-payload sender cap Bytes."""
    try:
        return tuple(int(token.strip()) for token in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("budget bytes must be comma-separated integers") from exc


def validate_equal_budget_config(
    *, robots: int, tasks: int, seeds: int, loss_probabilities: tuple[float, ...],
    budget_bytes: tuple[int, ...], max_rounds: int, max_iterations: int,
) -> None:
    """Validate paired experiment axes without inspecting algorithm success."""
    shape = (robots, tasks, seeds, max_rounds, max_iterations)
    if (any(type(x) is not int for x in shape)
        or not 1 <= tasks <= robots <= 100 or seeds < 1
        or max_rounds < 1 or max_iterations < 1):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_equal_budget_config", category="data",
            code="E9B_INVALID_DIMENSIONS",
            expected="integers 1<=T<=R<=100, seeds/max_rounds/max_iterations>=1",
            actual=shape,
        ))
    if (type(loss_probabilities) is not tuple or not loss_probabilities
        or any(type(x) not in (int, float) for x in loss_probabilities)
        or tuple(sorted(set(loss_probabilities))) != loss_probabilities):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_equal_budget_config", category="data",
            code="E9B_INVALID_LOSS_GRID",
            expected="nonempty ascending unique tuple of numeric p in [0,1]",
            actual=loss_probabilities,
        ))
    for p in loss_probabilities:
        validate_packet_loss_probability(p)
    if (type(budget_bytes) is not tuple or not budget_bytes
        or any(type(x) is not int for x in budget_bytes)
        or tuple(sorted(set(budget_bytes))) != budget_bytes):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_equal_budget_config", category="data",
            code="E9B_INVALID_BUDGET_GRID",
            expected="nonempty ascending unique tuple of exact integer cap Bytes >= 0",
            actual=budget_bytes,
        ))
    for cap in budget_bytes:
        validate_sender_payload_budget(cap)


def prepare_equal_budget_output(output_root: Path) -> None:
    """Never overwrite original E2/E3/E4/E8/E9A or previous E9B evidence."""
    root = output_root.resolve()
    results = Path("results").resolve()
    if root == results or root in results.parents:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="prepare_equal_budget_output", category="state",
            code="E9B_OUTPUT_SOURCE_COLLISION",
            expected="dedicated new E9B subdirectory, never results or its ancestor",
            actual=str(output_root),
        ))
    if root.is_relative_to(results):
        head = root.relative_to(results).parts[0]
        if head.startswith(("e2_", "e3_", "e4_", "e8_", "e9_cbaa_")):
            raise ProtocolError(Diagnostic(
                owner=OWNER, function="prepare_equal_budget_output", category="state",
                code="E9B_OUTPUT_SOURCE_COLLISION",
                expected="outside immutable E2/E3/E4/E8/E9A roots",
                actual=str(output_root),
            ))
    if output_root.exists() and (
        not output_root.is_dir()
        or any(p.name != "README.md" for p in output_root.iterdir())
    ):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="prepare_equal_budget_output", category="state",
            code="E9B_OUTPUT_ALREADY_EXISTS",
            expected="fresh or README-only output directory", actual=str(output_root),
        ))


def run_budgeted_greedy_trial(
    *, cost_matrix, seed: int, p: float, cap: int,
    phase_timeout_ms: float, max_rounds: int, profile,
):
    """Use existing pure25 retirement owner with a fresh independent ledger."""
    budget = SenderPayloadBudget(cap)
    result = simulate_democracy_hungarian_retirement(
        cost_matrix=cost_matrix, sampler=EmpiricalLatencySampler(profile, seed=seed),
        loss_sampler=BernoulliLossSampler(seed=seed),
        p_loss=p, p_vote_loss=p, phase_timeout_ms=phase_timeout_ms,
        max_rounds=max_rounds, voting_strategy="greedy_task",
        vote_decision_rule="quarter_plurality", vote_repetitions=1,
        send_budget=budget,
    )
    return result, budget


def run_budgeted_cbaa_trial(
    *, cost_matrix, seed: int, p: float, cap: int,
    phase_timeout_ms: float, max_iterations: int, profile,
):
    """Use existing single-assignment CBAA without observer feedback to agents."""
    budget = SenderPayloadBudget(cap)
    result = simulate_cbaa(
        cost_matrix=cost_matrix, sampler=EmpiricalLatencySampler(profile, seed=seed),
        loss_sampler=BernoulliLossSampler(seed=seed),
        loss_probability=p, phase_timeout_ms=phase_timeout_ms,
        max_iterations=max_iterations, capture_audit=False, send_budget=budget,
    )
    return result, budget


def validate_paired_sender_accounting(*, cap: int, greedy, gb, cbaa, cb) -> None:
    """Independent evidence boundary for exactly paired cap/actual SEND counts."""
    expected = {
        "greedy": (greedy.logical_message_count, greedy.payload_bytes),
        "cbaa": (cbaa.logical_message_count, cbaa.payload_bytes),
    }
    actual = {
        "greedy": (gb.sent_messages, gb.sent_bytes),
        "cbaa": (cb.sent_messages, cb.sent_bytes),
    }
    if (expected != actual or gb.limit_bytes != cap or cb.limit_bytes != cap
        or gb.sent_bytes > cap or cb.sent_bytes > cap):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_paired_sender_accounting",
            category="contract", code="E9B_PAIRED_SENDER_ACCOUNTING_MISMATCH",
            expected={"cap": cap, "events": expected},
            actual={"caps": (gb.limit_bytes, cb.limit_bytes), "ledgers": actual},
        ))
    if (greedy.committed_tasks + len(greedy.remaining_task_ids) != greedy.total_tasks
        or len(cbaa.observer_agreed_pairs) + len(cbaa.unconfirmed_task_ids)
           != len(cbaa.states[0].winning_bids)):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_paired_sender_accounting",
            category="contract", code="E9B_INCOMPLETE_OUTCOME_ACCOUNTING",
            expected="Greedy committed+pending=T; CBAA observer agreed+unconfirmed=T",
            actual={
                "greedy": (greedy.committed_tasks, len(greedy.remaining_task_ids)),
                "cbaa": (len(cbaa.observer_agreed_pairs), len(cbaa.unconfirmed_task_ids)),
            },
        ))


def budget_stop_fields(prefix: str, exhausted: bool, phase, diagnostic) -> dict[str, object]:
    """Expose original first-failing network owner/function/category/code unchanged."""
    return {
        prefix + "budget_exhausted": int(exhausted),
        prefix + "budget_stop_phase": phase or "",
        prefix + "stop_owner": diagnostic.owner if diagnostic else "",
        prefix + "stop_function": diagnostic.function if diagnostic else "",
        prefix + "stop_category": diagnostic.category if diagnostic else "",
        prefix + "stop_code": diagnostic.code if diagnostic else "",
        prefix + "stop_expected": repr(diagnostic.expected) if diagnostic else "",
        prefix + "stop_actual": repr(diagnostic.actual) if diagnostic else "",
        prefix + "stop_details": diagnostic.details if diagnostic else "",
    }


def build_equal_budget_pair_row(
    *, seed: int, scenario_sha256: str, timestamp: str, git_sha: str,
    robots: int, tasks: int, p: float, cap: int,
    max_rounds: int, max_iterations: int, reference,
    cost_matrix, greedy, gb, cbaa, cb,
) -> dict[str, object]:
    """One paired CSV row: keep all failures and NaN incomplete full-set cost."""
    validate_paired_sender_accounting(cap=cap, greedy=greedy, gb=gb, cbaa=cbaa, cb=cb)
    baseline = float(reference.total_cost)
    if not math.isfinite(baseline) or baseline <= 0.0:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="build_equal_budget_pair_row",
            category="contract", code="E9B_INVALID_GREEDY_REFERENCE_COST",
            expected="positive finite full-information Sequential Greedy cost",
            actual=baseline,
        ))
    reference_pairs = set(reference.assigned_pairs)
    gf, cf = greedy.full_assignment_success, cbaa.full_observer_agreement
    gcost = greedy.total_cost if gf else float("nan")
    ccost = (
        float(sum(cost_matrix[r][t] for r, t in cbaa.observer_agreed_pairs))
        if cf else float("nan")
    )
    return {
        "timestamp_utc": timestamp, "git_sha": git_sha,
        "seed": seed, "scenario_sha256": scenario_sha256,
        "robots": robots, "tasks": tasks,
        "p_cost_loss": p, "p_vote_loss": p, "p_consensus_loss": p,
        "hard_cap_sender_payload_bytes": cap,
        "max_greedy_rounds": max_rounds, "max_cbaa_iterations": max_iterations,
        "fullinfo_greedy_reference_cost": baseline,
        "greedy_method": greedy.method,
        "greedy_committed_tasks": greedy.committed_tasks,
        "greedy_commit_rate": greedy.task_commit_rate,
        "greedy_full_commit_success": int(gf),
        "greedy_reference_matching_commits": len(reference_pairs & set(greedy.assigned_pairs)),
        "greedy_assigned_pairs": repr(greedy.assigned_pairs),
        "greedy_remaining_task_ids": repr(greedy.remaining_task_ids),
        "greedy_full_batch_cost_complete_only": gcost,
        "greedy_cost_change_vs_reference_pct_complete_only": (
            100.0 * (gcost / baseline - 1.0) if gf else float("nan")
        ),
        "greedy_rounds_executed": len(greedy.rounds),
        "greedy_elapsed_ms": greedy.global_agreement_ms,
        "greedy_sender_messages": greedy.logical_message_count,
        "greedy_sender_bytes": gb.sent_bytes,
        "greedy_sender_remaining_bytes": gb.remaining_bytes,
        "greedy_denied_packets": gb.denied_messages,
        "greedy_lossy_delivered": greedy.lossy_delivered,
        "greedy_lossy_dropped": greedy.lossy_dropped,
        **budget_stop_fields(
            "greedy_", greedy.budget_exhausted, greedy.budget_stop_phase,
            greedy.budget_stop_diagnostic,
        ),
        "cbaa_method": cbaa.method,
        "cbaa_local_claim_count": len(cbaa.local_claims),
        "cbaa_agreed_tasks_observer": len(cbaa.observer_agreed_pairs),
        "cbaa_task_agreement_rate_observer": cbaa.task_agreement_rate,
        "cbaa_full_observer_agreement": int(cf),
        "cbaa_conflicting_tasks": len(cbaa.conflicting_task_ids),
        "cbaa_unconfirmed_tasks": len(cbaa.unconfirmed_task_ids),
        "cbaa_reference_matching_agreements": len(reference_pairs & set(cbaa.observer_agreed_pairs)),
        "cbaa_local_claims": repr(cbaa.local_claims),
        "cbaa_observer_agreed_pairs": repr(cbaa.observer_agreed_pairs),
        "cbaa_conflicting_task_ids": repr(cbaa.conflicting_task_ids),
        "cbaa_unconfirmed_task_ids": repr(cbaa.unconfirmed_task_ids),
        "cbaa_full_batch_cost_complete_only": ccost,
        "cbaa_cost_change_vs_reference_pct_complete_only": (
            100.0 * (ccost / baseline - 1.0) if cf else float("nan")
        ),
        "cbaa_iterations_executed": cbaa.iterations,
        "cbaa_elapsed_ms": cbaa.elapsed_ms,
        "cbaa_sender_messages": cbaa.logical_message_count,
        "cbaa_sender_bytes": cb.sent_bytes,
        "cbaa_sender_remaining_bytes": cb.remaining_bytes,
        "cbaa_denied_packets": cb.denied_messages,
        "cbaa_delivery_attempts": cbaa.delivery_attempts,
        "cbaa_delivery_drops": cbaa.delivery_drops,
        "cbaa_late_deliveries": cbaa.late_deliveries,
        **budget_stop_fields(
            "cbaa_", cbaa.budget_exhausted, cbaa.budget_stop_phase,
            cbaa.budget_stop_diagnostic,
        ),
        "actual_sent_byte_ratio_cbaa_over_greedy": (
            cb.sent_bytes / gb.sent_bytes if gb.sent_bytes else float("nan")
        ),
    }


def summarize_equal_budget_conditions(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Full-sample outcome means; costs condition on fully completed task sets."""
    output: list[dict[str, object]] = []
    for cap in sorted({int(r["hard_cap_sender_payload_bytes"]) for r in rows}):
        for p in sorted({float(r["p_cost_loss"]) for r in rows}):
            selected = [
                r for r in rows
                if int(r["hard_cap_sender_payload_bytes"]) == cap
                and float(r["p_cost_loss"]) == p
            ]
            if not selected:
                continue
            gf = [r for r in selected if int(r["greedy_full_commit_success"])]
            cf = [r for r in selected if int(r["cbaa_full_observer_agreement"])]
            mean = lambda key: statistics.fmean(float(r[key]) for r in selected)
            gb, cb = mean("greedy_sender_bytes"), mean("cbaa_sender_bytes")
            output.append({
                "robots": selected[0]["robots"], "tasks": selected[0]["tasks"],
                "hard_cap_sender_payload_bytes": cap, "p_loss": p,
                "seeds": len(selected),
                "greedy_full_commit_count": len(gf),
                "greedy_full_commit_rate": len(gf) / len(selected),
                "cbaa_full_observer_count": len(cf),
                "cbaa_full_observer_rate": len(cf) / len(selected),
                "both_full_observed_count": sum(
                    int(r["greedy_full_commit_success"]) *
                    int(r["cbaa_full_observer_agreement"]) for r in selected
                ),
                "greedy_mean_commit_rate": mean("greedy_commit_rate"),
                "cbaa_mean_observer_task_agreement": mean("cbaa_task_agreement_rate_observer"),
                "cbaa_mean_conflicting_tasks": mean("cbaa_conflicting_tasks"),
                "cbaa_mean_unconfirmed_tasks": mean("cbaa_unconfirmed_tasks"),
                "greedy_mean_sent_bytes": gb,
                "cbaa_mean_sent_bytes": cb,
                "actual_cbaa_over_greedy_mean_sent_byte_ratio": (
                    cb / gb if gb else float("nan")
                ),
                "greedy_mean_elapsed_ms": mean("greedy_elapsed_ms"),
                "cbaa_mean_elapsed_ms": mean("cbaa_elapsed_ms"),
                "greedy_budget_exhaustion_rate": mean("greedy_budget_exhausted"),
                "cbaa_budget_exhaustion_rate": mean("cbaa_budget_exhausted"),
                "greedy_complete_only_cost_count": len(gf),
                "cbaa_complete_only_cost_count": len(cf),
                "greedy_mean_full_cost_complete_only": (
                    statistics.fmean(float(r["greedy_full_batch_cost_complete_only"]) for r in gf)
                    if gf else float("nan")
                ),
                "cbaa_mean_full_cost_complete_only": (
                    statistics.fmean(float(r["cbaa_full_batch_cost_complete_only"]) for r in cf)
                    if cf else float("nan")
                ),
            })
    return output


def write_equal_budget_evidence(
    *, output_root: Path, rows: list[dict[str, object]],
    summary: list[dict[str, object]], timestamp: str, git_sha: str,
    robots: int, tasks: int, seeds: int, loss_probabilities: tuple[float, ...],
    budget_bytes: tuple[int, ...], max_rounds: int, max_iterations: int,
    phase_timeout_ms: float, dataset_path: Path,
) -> tuple[Path, Path, Path]:
    """Persist a new raw + summary + SHA256 manifest; never replace old runs."""
    output_root.mkdir(parents=True, exist_ok=True)
    raw = output_root / "raw" / ("e9b_pairs_" + timestamp + ".csv")
    summary_path = output_root / "summary.csv"
    manifest_path = output_root / "manifest.json"
    write_csv(raw, rows)
    write_csv(summary_path, summary)
    manifest_path.write_text(json.dumps({
        "experiment": "E9B-4 equal physical sender application payload hard cap",
        "timestamp_utc": timestamp, "source_git_sha": git_sha,
        "robots": robots, "tasks": tasks, "seeds": seeds,
        "loss_probabilities": list(loss_probabilities),
        "hard_cap_sender_payload_bytes": list(budget_bytes),
        "max_greedy_rounds": max_rounds, "max_cbaa_iterations": max_iterations,
        "phase_timeout_ms": phase_timeout_ms,
        "scenario": "generate_e0_scenario(seed,robots,tasks)",
        "greedy_method": "democracy_greedy_quarter_plurality_retirement",
        "cbaa_method": "cbaa_sync_single_assignment",
        "greedy_control_reliability": "lossy Cost/Vote; reliable score/Commit",
        "cbaa_control_reliability": "lossy receiver bid vectors; NO Commit",
        "actual_sender_bytes_can_differ_under_same_cap": True,
        "observer_agreement_is_not_distributed_commit": True,
        "different_round_and_iteration_limits": True,
        "full_batch_cost_rule": "NaN unless method has full task set",
        "network_dataset": str(dataset_path),
        "rady_source_commit": RADY_SOURCE_COMMIT,
        "rady_blob_sha": RADY_SOURCE_BLOB_SHA,
        "raw_rows": len(rows), "summary_rows": len(summary),
        "raw_csv": str(raw), "summary_csv": str(summary_path),
        "raw_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
        "summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return raw, summary_path, manifest_path


def run_e9b_equal_budget_experiment(
    *, robots: int, tasks: int, seeds: int,
    loss_probabilities: tuple[float, ...], budget_bytes: tuple[int, ...],
    max_rounds: int, max_iterations: int, dataset_path: Path,
    output_root: Path, allow_download: bool = True,
) -> list[dict[str, object]]:
    """Run each original owner independently on the identical scene/p/cap."""
    validate_equal_budget_config(
        robots=robots, tasks=tasks, seeds=seeds,
        loss_probabilities=loss_probabilities, budget_bytes=budget_bytes,
        max_rounds=max_rounds, max_iterations=max_iterations,
    )
    prepare_equal_budget_output(output_root)
    dataset = ensure_rady_dataset(dataset_path, allow_download=allow_download)
    profile = load_rady_latency_profile(dataset)
    phase_timeout_ms = float(summarize_latency_profile(profile)["max_ms"])
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    git_sha = read_retirement_revision()
    rows: list[dict[str, object]] = []
    for seed in range(seeds):
        scenario = generate_e0_scenario(seed, robots, tasks)
        reference = solve_sequential_greedy_reference(scenario.cost_matrix)
        scene_hash = hashlib.sha256(repr(scenario.cost_matrix).encode("utf-8")).hexdigest()
        for cap in budget_bytes:
            for p in loss_probabilities:
                greedy, gb = run_budgeted_greedy_trial(
                    cost_matrix=scenario.cost_matrix, seed=seed, p=p, cap=cap,
                    phase_timeout_ms=phase_timeout_ms, max_rounds=max_rounds,
                    profile=profile,
                )
                cbaa, cb = run_budgeted_cbaa_trial(
                    cost_matrix=scenario.cost_matrix, seed=seed, p=p, cap=cap,
                    phase_timeout_ms=phase_timeout_ms, max_iterations=max_iterations,
                    profile=profile,
                )
                rows.append(build_equal_budget_pair_row(
                    seed=seed, scenario_sha256=scene_hash, timestamp=timestamp,
                    git_sha=git_sha, robots=robots, tasks=tasks, p=p, cap=cap,
                    max_rounds=max_rounds, max_iterations=max_iterations,
                    reference=reference, cost_matrix=scenario.cost_matrix,
                    greedy=greedy, gb=gb, cbaa=cbaa, cb=cb,
                ))
        if (seed + 1) % 10 == 0 or seed + 1 == seeds:
            print("E9B_PROGRESS seeds={}/{}".format(seed + 1, seeds), flush=True)
    summary = summarize_equal_budget_conditions(rows)
    raw, sum_path, manifest = write_equal_budget_evidence(
        output_root=output_root, rows=rows, summary=summary,
        timestamp=timestamp, git_sha=git_sha,
        robots=robots, tasks=tasks, seeds=seeds,
        loss_probabilities=loss_probabilities, budget_bytes=budget_bytes,
        max_rounds=max_rounds, max_iterations=max_iterations,
        phase_timeout_ms=phase_timeout_ms, dataset_path=dataset,
    )
    print("E9B_HEAD={}".format(git_sha))
    print("E9B_PAIRED_RAW={}".format(raw))
    print("E9B_SUMMARY={}".format(sum_path))
    print("E9B_MANIFEST={}".format(manifest))
    for item in summary:
        print(
            "E9B_RESULT cap={} loss={:.2f} greedy_full_commit={:.4f} "
            "cbaa_full_observer={:.4f} greedy_task_rate={:.4f} "
            "cbaa_agreed_task_rate={:.4f} greedy_bytes={:.0f} cbaa_bytes={:.0f} "
            "greedy_stop={:.3f} cbaa_stop={:.3f}".format(
                item["hard_cap_sender_payload_bytes"], item["p_loss"],
                item["greedy_full_commit_rate"], item["cbaa_full_observer_rate"],
                item["greedy_mean_commit_rate"], item["cbaa_mean_observer_task_agreement"],
                item["greedy_mean_sent_bytes"], item["cbaa_mean_sent_bytes"],
                item["greedy_budget_exhaustion_rate"], item["cbaa_budget_exhaustion_rate"],
            )
        )
    print("E9B_INTERPRETATION=EQUAL_HARD_CAP_NOT_EQUAL_ACTUAL_BYTES_OR_CONTROL_RELIABILITY")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="E9B-4 paired hard sender-byte-cap benchmark")
    parser.add_argument("--robots", type=int, default=100)
    parser.add_argument("--tasks", type=int, default=50)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--loss-probabilities", type=parse_probabilities, default=DEFAULT_LOSSES)
    parser.add_argument("--budget-bytes", type=parse_sender_budgets, default=DEFAULT_BUDGETS)
    parser.add_argument("--max-rounds", type=int, default=100)
    parser.add_argument("--max-iterations", type=int, default=40)
    parser.add_argument("--dataset", type=Path, default=Path(
        "data/external/rady/perama_range_testing.json"
    ))
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    run_e9b_equal_budget_experiment(
        robots=args.robots, tasks=args.tasks, seeds=args.seeds,
        loss_probabilities=args.loss_probabilities,
        budget_bytes=args.budget_bytes, max_rounds=args.max_rounds,
        max_iterations=args.max_iterations, dataset_path=args.dataset,
        output_root=args.output_root, allow_download=not args.no_download,
    )


if __name__ == "__main__":
    main()
