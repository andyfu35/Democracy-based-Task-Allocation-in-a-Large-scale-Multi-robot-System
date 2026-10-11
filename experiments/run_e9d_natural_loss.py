"""E9D-2: paired original Democracy/CBAA actual sender Bytes versus rising loss.

NO manual CBAA K selection. Original CBAA auction and consensus run in their
single original owner with opt-in per-receiver local evidence certification.
The safety-round limit is an explicit computational censor, NOT convergence.

Complete TASK announcement is a GUARANTEED/PAID common source broadcast;
its receiver loss is zero by design in this first loss sweep. Only
Democracy Cost + Vote and CBAA consensus packets independently drop at p.
Original Democracy Score/Commit retain their existing reliable stages.
CBAA's all-local-ready outer scheduler is a documented optimistic halt
(not a distributed ACK/stop/Commit protocol).
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics

from democracy_mrta.cbaa import simulate_cbaa
from democracy_mrta.coordination import simulate_democracy_hungarian_retirement
from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler, RADY_SOURCE_BLOB_SHA, RADY_SOURCE_COMMIT,
    validate_packet_loss_probability,
)
from experiments.run_e2 import parse_probabilities
from experiments.run_e2_retirement import read_retirement_revision
from experiments.run_e9c_100seed_comms import (
    capture_seed_information, create_seed_sampler, select_network_sampler,
)
from experiments.run_e9c_real_information import summarize_greedy_wire_phases

OWNER = "experiments.run_e9d_natural_loss"
DEFAULT_GRID = (0.0, 0.10, 0.20, 0.30, 0.40, 0.50,
                0.60, 0.70, 0.80, 0.90, 0.95)
DEFAULT_ROOT = Path("results/e9d_natural_loss")
EXPECTED_METHODS = ("democracy_cost_vote", "cbaa_original_local_certified")


def validate_e9d_natural_loss_axes(
    *,
    robots: int, tasks: int, seeds: int, first_seed: int,
    losses: tuple[float, ...],
    cbaa_safety_round_limit: int, democracy_safety_round_limit: int,
    latency_mode: str,
) -> None:
    """One data/time/experiment scope gate before physical SENDs."""
    axes = (robots, tasks, seeds, first_seed,
            cbaa_safety_round_limit, democracy_safety_round_limit)
    if (any(type(x) is not int for x in axes)
        or not 1 <= tasks <= robots <= 100
        or not 1 <= seeds <= 10000 or first_seed < 0
        or cbaa_safety_round_limit < 1 or democracy_safety_round_limit < 1):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_e9d_natural_loss_axes",
            category="data", code="E9D_INVALID_SCENARIO_OR_GUARD",
            expected="1<=T<=R<=100; 1<=seeds<=10000; first_seed>=0; guards>=1",
            actual=axes,
        ))
    if (type(losses) is not tuple or not losses
        or any(type(p) not in (int, float) for p in losses)
        or tuple(sorted(set(losses))) != losses):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_e9d_natural_loss_axes",
            category="data", code="E9D_INVALID_LOSS_GRID",
            expected="ascending unique nonempty tuple of numeric p",
            actual=losses,
        ))
    for p in losses:
        validate_packet_loss_probability(p)
    if latency_mode not in ("constant", "rady"):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_e9d_natural_loss_axes",
            category="planning", code="E9D_UNKNOWN_LATENCY_MODE",
            expected="constant or rady", actual=latency_mode,
        ))


def prepare_e9d_output_root(root: Path) -> None:
    """Dedicated immutable root: NEVER overwrite E2/E8/E9B/E9C or prior E9D."""
    resolved, results = root.resolve(), Path("results").resolve()
    if (resolved == results or resolved in results.parents
        or (resolved.is_relative_to(results)
            and not resolved.relative_to(results).parts[0].startswith("e9d_"))):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="prepare_e9d_output_root",
            category="state", code="E9D_PROTECTED_OUTPUT_ROOT",
            expected="fresh results/e9d_* or distinct external experiment path",
            actual=str(root),
        ))
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="prepare_e9d_output_root",
            category="state", code="E9D_OUTPUT_ALREADY_EXISTS",
            expected="empty/new output root; old raw is immutable", actual=str(root),
        ))


def run_e9d_democracy_loss_case(
    *,
    cost_rows, task_bytes: int, task_packets: int,
    robots: int, tasks: int, seed: int, p_loss: float,
    profile, timeout_ms: float, round_guard: int,
) -> dict[str, object]:
    """Call ONLY original Greedy one-Cost-broadcast + Vote/Score/Commit owner."""
    result = simulate_democracy_hungarian_retirement(
        cost_matrix=cost_rows,
        sampler=create_seed_sampler(profile=profile, seed=seed),
        loss_sampler=BernoulliLossSampler(seed=seed),
        p_loss=p_loss, p_vote_loss=p_loss,
        phase_timeout_ms=timeout_ms, max_rounds=round_guard,
        voting_strategy="greedy_task",
        vote_decision_rule="quarter_plurality", vote_repetitions=1,
    )
    phases = summarize_greedy_wire_phases(result)
    return {
        "seed": seed, "loss_probability": p_loss, "robots": robots,
        "tasks": tasks, "method": EXPECTED_METHODS[0],
        "task_packet_count": task_packets,
        "task_sender_bytes": task_bytes,
        "cost_sender_bytes": phases["cost"],
        "vote_sender_bytes": phases["vote"],
        "score_sender_bytes": phases["vote_score_announcement"],
        "commit_sender_bytes": phases["commit"],
        "cbaa_bid_sender_bytes": 0,
        "coordination_sender_bytes": result.payload_bytes,
        "total_sender_bytes": task_bytes + result.payload_bytes,
        "coordination_send_count": result.logical_message_count,
        "coordination_delivery_attempts": result.lossy_delivered + result.lossy_dropped,
        "coordination_delivered": result.lossy_delivered,
        "coordination_dropped": result.lossy_dropped,
        "rounds_executed": len(result.rounds),
        "elapsed_ms": result.global_agreement_ms,
        "tasks_confirmed": result.committed_tasks,
        "full_commit": int(result.full_assignment_success),
        "full_observer_agreement": "",
        "all_locally_certified": "",
        "locally_certified_count": "",
        "stop_reason": (
            "completed_actual_commit" if result.full_assignment_success
            else "democracy_round_guard"
        ),
        "safety_guard_hit": int(
            not result.full_assignment_success and len(result.rounds) >= round_guard
        ),
        "success_semantics": "actual_reliable_commit",
    }


def run_e9d_original_cbaa_loss_case(
    *,
    cost_rows, task_bytes: int, task_packets: int,
    robots: int, tasks: int, seed: int, p_loss: float,
    profile, timeout_ms: float, round_guard: int,
) -> dict[str, object]:
    """Original single-assignment CBAA, original SEND, peer-local evidence stop."""
    result = simulate_cbaa(
        cost_matrix=cost_rows,
        sampler=create_seed_sampler(profile=profile, seed=seed),
        loss_sampler=BernoulliLossSampler(seed=seed),
        loss_probability=p_loss,
        phase_timeout_ms=timeout_ms,
        max_iterations=round_guard,
        stop_mode="local_certification",
        capture_audit=False,
    )
    return {
        "seed": seed, "loss_probability": p_loss, "robots": robots,
        "tasks": tasks, "method": EXPECTED_METHODS[1],
        "task_packet_count": task_packets, "task_sender_bytes": task_bytes,
        "cost_sender_bytes": 0, "vote_sender_bytes": 0,
        "score_sender_bytes": 0, "commit_sender_bytes": 0,
        "cbaa_bid_sender_bytes": result.payload_bytes,
        "coordination_sender_bytes": result.payload_bytes,
        "total_sender_bytes": task_bytes + result.payload_bytes,
        "coordination_send_count": result.logical_message_count,
        "coordination_delivery_attempts": result.delivery_attempts,
        "coordination_delivered": result.delivery_attempts-result.delivery_drops,
        "coordination_dropped": result.delivery_drops,
        "rounds_executed": result.iterations,
        "elapsed_ms": result.elapsed_ms,
        "tasks_confirmed": len(result.observer_agreed_pairs),
        "full_commit": "",
        "full_observer_agreement": int(result.full_observer_agreement),
        "all_locally_certified": int(result.stop_reason == "all_local_evidence_certified"),
        "locally_certified_count": result.locally_certified_count,
        "stop_reason": result.stop_reason,
        "safety_guard_hit": int(result.stop_reason == "iteration_safety_guard"),
        "success_semantics": (
            "all_peer_local_evidence_and_posthoc_observer; "
            "optimistic_simulator_halt_not_distributed_commit"
        ),
    }


def validate_e9d_physical_accounting(rows: tuple[dict[str, object], ...]) -> None:
    """Check original methods, common task bytes, exact stage sums, pair shape."""
    if (len(rows) != 2
        or tuple(x["method"] for x in rows) != EXPECTED_METHODS
        or any(x["seed"] != rows[0]["seed"]
               or x["loss_probability"] != rows[0]["loss_probability"]
               or x["task_sender_bytes"] != rows[0]["task_sender_bytes"]
               for x in rows)):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_e9d_physical_accounting",
            category="contract", code="E9D_PAIRED_METHOD_MISMATCH",
            expected=EXPECTED_METHODS, actual=[r["method"] for r in rows],
        ))
    for row in rows:
        derived = sum(int(row[key]) for key in (
            "cost_sender_bytes", "vote_sender_bytes",
            "score_sender_bytes", "commit_sender_bytes",
            "cbaa_bid_sender_bytes",
        ))
        total = int(row["task_sender_bytes"]) + derived
        if (derived != int(row["coordination_sender_bytes"])
            or total != int(row["total_sender_bytes"])
            or int(row["coordination_delivered"])+int(row["coordination_dropped"])
                != int(row["coordination_delivery_attempts"])):
            raise ProtocolError(Diagnostic(
                owner=OWNER, function="validate_e9d_physical_accounting",
                category="contract", code="E9D_SENDER_BYTES_OR_DELIVERIES_MISMATCH",
                expected={"bytes": total, "coordination_bytes": derived},
                actual={"bytes": row["total_sender_bytes"],
                        "coordination_bytes": row["coordination_sender_bytes"]},
                details=f"seed={row['seed']} p={row['loss_probability']} method={row['method']}",
            ))


def summarize_e9d_loss_results(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """All seeds in denominator; guard and observer success never censored."""
    groups: dict[tuple[float, str], list[dict[str, object]]] = {}
    for row in rows:
        groups.setdefault((float(row["loss_probability"]), str(row["method"])), []).append(row)
    summary = []
    for (p_loss, method), subset in sorted(groups.items()):
        n=len(subset)
        fully=[int(r["full_commit"]) if method == EXPECTED_METHODS[0]
               else int(r["all_locally_certified"]) for r in subset]
        byte_values=[int(r["total_sender_bytes"]) for r in subset]
        summary.append({
            "loss_probability": p_loss,
            "method": method,
            "seeds": n,
            "full_protocol_result_count": sum(fully),
            "full_protocol_result_rate": sum(fully)/n,
            "mean_tasks_confirmed": statistics.mean(int(r["tasks_confirmed"]) for r in subset),
            "mean_total_sender_bytes": statistics.mean(byte_values),
            "min_total_sender_bytes": min(byte_values),
            "max_total_sender_bytes": max(byte_values),
            "mean_rounds_executed": statistics.mean(int(r["rounds_executed"]) for r in subset),
            "guard_hit_count": sum(int(r["safety_guard_hit"]) for r in subset),
            "cbaa_full_observer_agreement_count": (
                sum(int(r["full_observer_agreement"]) for r in subset)
                if method == EXPECTED_METHODS[1] else ""),
            "cbaa_all_locally_certified_count": (
                sum(int(r["all_locally_certified"]) for r in subset)
                if method == EXPECTED_METHODS[1] else ""),
            "primary_semantics": subset[0]["success_semantics"],
        })
    return summary


def calculate_e9d_empirical_limits(summary: list[dict[str, object]]) -> dict[str, object]:
    """Sampled success frontier ONLY, never infer asymptotic theoretical limit."""
    result: dict[str, object] = {}
    for method in EXPECTED_METHODS:
        series=[r for r in summary if r["method"] == method]
        fully=[r["loss_probability"] for r in series
               if r["full_protocol_result_count"] == r["seeds"]]
        partly=[r["loss_probability"] for r in series
                if r["full_protocol_result_count"] > 0]
        first_decline=next((r["loss_probability"] for r in series
                            if r["full_protocol_result_count"] < r["seeds"]),None)
        result[method]={
            "highest_tested_loss_with_all_seed_success": max(fully) if fully else None,
            "highest_tested_loss_with_any_success": max(partly) if partly else None,
            "first_tested_loss_with_less_than_full_seed_success": first_decline,
            "has_censored_guard_cases": any(r["guard_hit_count"]>0 for r in series),
            "sampled_statistical_not_theoretical_boundary": True,
        }
    return result


def write_e9d_final_evidence(
    *, root: Path, partial_raw: Path, rows: list[dict[str, object]],
    robots: int, tasks: int, seeds: int, first_seed: int,
    losses: tuple[float, ...], cbaa_guard: int, democracy_guard: int,
    latency_mode: str, latency_detail: str, source_sha: str,
) -> tuple[Path, Path, Path]:
    """Exactly two rows per seed/loss; archive raw/summary with SHA256 provenance."""
    raw=root/"per_seed_loss_method.csv"
    os.replace(partial_raw,raw)
    summary=root/"summary_by_loss.csv"
    manifest=root/"manifest.json"
    summary_rows=summarize_e9d_loss_results(rows)
    with summary.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=list(summary_rows[0]))
        writer.writeheader()
        writer.writerows(summary_rows)
    meta={
        "experiment": "E9D-2 original Democracy and original CBAA natural local-evidence stop, rising loss",
        "source_git_sha": source_sha,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "robots": robots, "tasks": tasks,
        "seeds": seeds, "first_seed": first_seed,
        "loss_probabilities": list(losses),
        "cbaa_iteration_safety_guard_not_manual_K": cbaa_guard,
        "democracy_round_safety_guard": democracy_guard,
        "latency_mode": latency_mode, "latency_details": latency_detail,
        "rady_source_commit": RADY_SOURCE_COMMIT if latency_mode == "rady" else None,
        "rady_source_blob_sha": RADY_SOURCE_BLOB_SHA if latency_mode == "rady" else None,
        "common_task_announced_reliably_with_loss_zero": True,
        "task_binary_source_is_not_central_allocator": True,
        "task_sender_payload_bytes_counted_once_per_physical_broadcast": True,
        "democracy_loss_stages": ["cost_broadcast", "vote_unicast"],
        "democracy_control_stages_reliably_modeled": ["score_announcement","commit"],
        "cbaa_loss_stages": ["original_winning_bid_and_winner_origin_broadcast"],
        "cbaa_original_auction_and_consensus_unchanged": True,
        "no_extra_peer_robot_pose_communication": True,
        "cbaa_no_distributed_stop_ack_or_actual_commit": True,
        "cbaa_local_certificate_requires_recent_physically_received_peer_states": True,
        "cbaa_all_ready_scheduler_is_optimistic_no_paid_global_halt_protocol": True,
        "guard_reached_is_not_proof_of_theoretical_failure": True,
        "democracy_commit_not_semantically_equal_cbaa_observer_agreement": True,
        "cost_vote_score_commit_cbaa_bid_sizes_from_original_send_events": True,
        "task_announcement_uses_actual_binary_packed_records": True,
        "not_mac_phy_ip_ack_wire_airtime": True,
        "source_filename": str(raw), "summary_filename": str(summary),
        "raw_rows": len(rows), "expected_rows": seeds*len(losses)*2,
        "empirical_sampled_loss_limits": calculate_e9d_empirical_limits(summary_rows),
        "sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (raw,summary)
        },
    }
    manifest.write_text(json.dumps(meta,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return raw,summary,manifest


def run_e9d_natural_loss(
    *, robots: int=100, tasks: int=50, seeds: int=100, first_seed: int=0,
    loss_probabilities: tuple[float, ...]=DEFAULT_GRID,
    cbaa_safety_round_limit: int=160, democracy_safety_round_limit: int=300,
    latency_mode: str="constant",
    dataset_path: Path=Path("data/external/rady/perama_range_testing.json"),
    allow_download: bool=True,
    output_root: Path=DEFAULT_ROOT,
) -> list[dict[str, object]]:
    """Actual independent 2-method paired cells, raw streamed after each cell."""
    validate_e9d_natural_loss_axes(
        robots=robots,tasks=tasks,seeds=seeds,first_seed=first_seed,
        losses=loss_probabilities,cbaa_safety_round_limit=cbaa_safety_round_limit,
        democracy_safety_round_limit=democracy_safety_round_limit,
        latency_mode=latency_mode,
    )
    prepare_e9d_output_root(output_root)
    profile,timeout_ms,latency_detail=select_network_sampler(
        latency_mode=latency_mode,dataset=dataset_path,allow_download=allow_download,
    )
    output_root.mkdir(parents=True,exist_ok=True)
    partial=output_root/"per_seed_loss_method.partial.csv"
    rows: list[dict[str,object]]=[]
    source_sha=read_retirement_revision()
    with partial.open("w",newline="",encoding="utf-8") as handle:
        writer=None
        for index in range(seeds):
            seed=first_seed+index
            cost_rows,task_trace=capture_seed_information(
                seed=seed,robots=robots,tasks=tasks,profile=profile,
                timeout_ms=timeout_ms,
            )
            for p_loss in loss_probabilities:
                current=(
                    run_e9d_democracy_loss_case(
                        cost_rows=cost_rows,task_bytes=task_trace.sender_bytes,
                        task_packets=len(task_trace.events),robots=robots,tasks=tasks,
                        seed=seed,p_loss=p_loss,profile=profile,
                        timeout_ms=timeout_ms,round_guard=democracy_safety_round_limit,
                    ),
                    run_e9d_original_cbaa_loss_case(
                        cost_rows=cost_rows,task_bytes=task_trace.sender_bytes,
                        task_packets=len(task_trace.events),robots=robots,tasks=tasks,
                        seed=seed,p_loss=p_loss,profile=profile,
                        timeout_ms=timeout_ms,round_guard=cbaa_safety_round_limit,
                    ),
                )
                validate_e9d_physical_accounting(current)
                if writer is None:
                    writer=csv.DictWriter(handle,fieldnames=list(current[0]))
                    writer.writeheader()
                for row in current:
                    writer.writerow(row)
                    rows.append(row)
                handle.flush()
            if (index+1)%5==0 or (index+1)==seeds:
                print("E9D_PROGRESS seeds={}/{} cells={} sha={}".format(
                    index+1,seeds,len(rows)//2,source_sha
                ),flush=True)
    raw,summary,manifest=write_e9d_final_evidence(
        root=output_root,partial_raw=partial,rows=rows,
        robots=robots,tasks=tasks,seeds=seeds,first_seed=first_seed,
        losses=loss_probabilities,cbaa_guard=cbaa_safety_round_limit,
        democracy_guard=democracy_safety_round_limit,
        latency_mode=latency_mode,latency_detail=latency_detail,
        source_sha=source_sha,
    )
    for item in summarize_e9d_loss_results(rows):
        print("E9D_RESULT loss={:.2f} method={} full={}/{} mean_tasks={:.3f} "
              "mean_bytes={:.1f} mean_rounds={:.2f} guard_hit={}".format(
                  item["loss_probability"],item["method"],
                  item["full_protocol_result_count"],item["seeds"],
                  item["mean_tasks_confirmed"],item["mean_total_sender_bytes"],
                  item["mean_rounds_executed"],item["guard_hit_count"],
              ),flush=True)
    limits=calculate_e9d_empirical_limits(summarize_e9d_loss_results(rows))
    print("E9D_EMPIRICAL_LIMITS="+json.dumps(limits,sort_keys=True),flush=True)
    print("E9D_SOURCE_SHA={}\nE9D_RAW={}\nE9D_SUMMARY={}\nE9D_MANIFEST={}".format(
        source_sha,raw,summary,manifest
    ),flush=True)
    print("E9D_WARNING=CBAA_LOCAL_CERTIFICATION_IS_OPTIMISTIC_SHARED_SIMULATOR_HALT;"
          "TASK_ANNOUNCEMENT_RELIABLE;NO_DISTRIBUTED_TERMINATION_ACK;"
          "GUARD_REACHED_IS_CENSORED_NOT_PROVEN_PACKET_LOSS_LIMIT",flush=True)
    return rows


def main() -> None:
    parser=argparse.ArgumentParser(description=(
        "E9D: original Democracy/CBAA messages vs rising loss. "
        "CBAA uses received-peer local evidence, no chosen K grid."
    ))
    parser.add_argument("--robots",type=int,default=100)
    parser.add_argument("--tasks",type=int,default=50)
    parser.add_argument("--seeds",type=int,default=100)
    parser.add_argument("--first-seed",type=int,default=0)
    parser.add_argument("--loss-probabilities",type=parse_probabilities,
                        default=DEFAULT_GRID)
    parser.add_argument("--cbaa-safety-round-limit",type=int,default=160)
    parser.add_argument("--democracy-safety-round-limit",type=int,default=300)
    parser.add_argument("--latency-mode",choices=("constant","rady"),default="constant")
    parser.add_argument("--dataset",type=Path,
                        default=Path("data/external/rady/perama_range_testing.json"))
    parser.add_argument("--no-download",action="store_true")
    parser.add_argument("--output-root",type=Path,default=DEFAULT_ROOT)
    args=parser.parse_args()
    run_e9d_natural_loss(
        robots=args.robots,tasks=args.tasks,seeds=args.seeds,
        first_seed=args.first_seed,loss_probabilities=args.loss_probabilities,
        cbaa_safety_round_limit=args.cbaa_safety_round_limit,
        democracy_safety_round_limit=args.democracy_safety_round_limit,
        latency_mode=args.latency_mode,dataset_path=args.dataset,
        allow_download=not args.no_download,output_root=args.output_root,
    )


if __name__=="__main__":
    main()
