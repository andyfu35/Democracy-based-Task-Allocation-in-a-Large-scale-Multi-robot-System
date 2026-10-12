"""E9F-2: Cost-row redundancy vs original CBAA, increasing packet loss.

E9F changes ONLY the true original Democracy Cost source (E9F-1). This
experiment invokes original Democracy Greedy votes/Score/reliable Commit and
unchanged original CBAA auction/max-consensus, never a copied state machine.

All sender Cost copies, Vote/Score/Commit and CBAA Bid/Winner packets are
charged at the original physically emitted CommunicationEvent payload lengths.
TASK is the original paid, binary source announcement with p_task=0.

CBAA simulator-wide ready aggregation is optimistic; no distributed stop
ACK/Commit packets are sent. Guard-limited cases are censored, not failures
of the mathematical protocol.
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

from democracy_mrta.coordination import (
    cost_row_payload_bytes,
    simulate_democracy_hungarian_retirement,
    validate_cost_repetitions,
)
from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import BernoulliLossSampler
from experiments.run_e2 import parse_probabilities
from experiments.run_e2_retirement import read_retirement_revision
from experiments.run_e9c_real_information import summarize_greedy_wire_phases
from experiments.run_e9c_100seed_comms import (
    capture_seed_information, create_seed_sampler, select_network_sampler,
)
from experiments.run_e9d_natural_loss import (
    run_e9d_original_cbaa_loss_case,
    validate_e9d_natural_loss_axes,
)

OWNER = "experiments.run_e9f_cost_redundancy"
DEFAULT_COST_COPIES = (1, 2, 3, 5)
DEFAULT_LOSSES = tuple(
    percent / 100 for percent in (0, 30, 40, 45, 48, *range(50, 66), 70, 80, 90)
)
DEFAULT_ROOT = Path("results/e9f_cost_redundancy")
CBAA_ID = "cbaa_original_local_certified"


def parse_e9f_cost_copy_grid(value: str) -> tuple[int, ...]:
    """The only Cost-copy grid string parser; no forgiving silent choices."""
    try:
        copies = tuple(int(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="parse_e9f_cost_copy_grid",
            category="data", code="E9F_INVALID_COST_GRID",
            expected="unique ascending comma-separated integer copies including 1",
            actual=value,
        )) from exc
    validate_e9f_cost_grid(copies)
    return copies


def validate_e9f_cost_grid(cost_copies: tuple[int, ...]) -> None:
    """Cost repetition profile data boundary; keep original one-copy control."""
    if (type(cost_copies) is not tuple or not cost_copies or
        tuple(sorted(set(cost_copies))) != cost_copies or
        cost_copies[0] != 1):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_e9f_cost_grid",
            category="data", code="E9F_INVALID_COST_GRID",
            expected="unique ascending tuple in [1,5] beginning with 1",
            actual=cost_copies,
        ))
    for copies in cost_copies:
        validate_cost_repetitions(copies)


def validate_e9f_sweep_axes(
    *,
    robots: int, tasks: int, seeds: int, first_seed: int,
    losses: tuple[float, ...], cost_copies: tuple[int, ...],
    cbaa_guard: int, democracy_guard: int, latency_mode: str,
) -> None:
    """Preserve original scenario/loss validation; validate E9F-only scope."""
    validate_e9d_natural_loss_axes(
        robots=robots, tasks=tasks, seeds=seeds, first_seed=first_seed,
        losses=losses, cbaa_safety_round_limit=cbaa_guard,
        democracy_safety_round_limit=democracy_guard,
        latency_mode=latency_mode,
    )
    validate_e9f_cost_grid(cost_copies)
    if robots < 2:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_e9f_sweep_axes",
            category="data", code="E9F_ROBOTS_REQUIRE_PEER_RECEIPTS",
            expected="robots >= 2 for actual cost peer-receipt measurement",
            actual=robots,
        ))


def prepare_e9f_output_root(root: Path) -> None:
    """Protect all previous experiments; refuse overwriting E9F evidence."""
    resolved = root.resolve()
    results = Path("results").resolve()
    if (
        resolved == results or resolved in results.parents
        or (
            resolved.is_relative_to(results) and
            not resolved.relative_to(results).parts[0].startswith("e9f_")
        )
    ):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="prepare_e9f_output_root",
            category="state", code="E9F_PROTECTED_OUTPUT_ROOT",
            expected="new results/e9f_* directory or a distinct external directory",
            actual=str(root),
        ))
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="prepare_e9f_output_root",
            category="state", code="E9F_OUTPUT_EXISTS",
            expected="unused output directory; raw evidence is immutable",
            actual=str(root),
        ))


def run_e9f_democracy_cost_case(
    *,
    cost_rows, task_bytes: int, task_packets: int,
    robots: int, tasks: int, seed: int, p_loss: float,
    copies: int, profile, timeout_ms: float, democracy_guard: int,
) -> dict[str, object]:
    """Original Greedy+Score/Commit with explicitly paid initial Cost copies."""
    result = simulate_democracy_hungarian_retirement(
        cost_matrix=cost_rows,
        sampler=create_seed_sampler(profile=profile, seed=seed),
        loss_sampler=BernoulliLossSampler(seed=seed),
        p_loss=p_loss, p_vote_loss=p_loss,
        phase_timeout_ms=timeout_ms, max_rounds=democracy_guard,
        voting_strategy="greedy_task",
        vote_decision_rule="quarter_plurality", vote_repetitions=1,
        cost_repetitions=copies,
    )
    phase_bytes = summarize_greedy_wire_phases(result)
    cost_events = [
        event for epoch in result.rounds
        for event in epoch.coordination.events if event.phase == "cost"
    ]
    cost_deliveries = [
        obs for epoch in result.rounds
        for obs in epoch.coordination.deliveries if obs.phase == "cost"
    ]
    unique_peer_receipts = {
        (obs.sender_id, obs.receiver_id)
        for obs in cost_deliveries if obs.delivered
    }
    actual_initial_visible = (
        result.rounds[0].coordination.mean_visible_robot_rows if result.rounds else 0.0
    )
    expected_initial_visible = 1 + len(unique_peer_receipts) / robots
    if abs(actual_initial_visible - expected_initial_visible) > 1e-9:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="run_e9f_democracy_cost_case",
            category="contract", code="E9F_VISIBLE_COST_SOURCE_MISMATCH",
            expected=expected_initial_visible, actual=actual_initial_visible,
            details=f"seed={seed} p={p_loss} copies={copies}",
        ))
    return {
        "seed": seed, "loss_probability": p_loss,
        "robots": robots, "tasks": tasks,
        "method": f"democracy_cost_copies_{copies}", "cost_copies": copies,
        "task_packet_count": task_packets, "task_sender_bytes": task_bytes,
        "cost_packet_count": len(cost_events),
        "cost_peer_delivery_attempts": len(cost_deliveries),
        "cost_peer_delivered_packets": sum(int(obs.delivered) for obs in cost_deliveries),
        "cost_distinct_peer_receipts": len(unique_peer_receipts),
        "initial_cost_peer_reach_fraction": len(unique_peer_receipts)/(robots*(robots-1)),
        "initial_mean_visible_cost_rows": actual_initial_visible,
        "cost_sender_bytes": phase_bytes["cost"],
        "vote_sender_bytes": phase_bytes["vote"],
        "score_sender_bytes": phase_bytes["vote_score_announcement"],
        "commit_sender_bytes": phase_bytes["commit"],
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
        "stop_reason": (
            "completed_actual_commit" if result.full_assignment_success
            else "democracy_round_guard"
        ),
        "safety_guard_hit": int(
            not result.full_assignment_success and
            len(result.rounds) >= democracy_guard
        ),
        "success_semantics": "real_reliable_all_task_commit",
    }


def run_e9f_cbaa_reference_case(
    *,
    cost_rows, task_bytes: int, task_packets: int,
    robots: int, tasks: int, seed: int, p_loss: float,
    profile, timeout_ms: float, cbaa_guard: int,
) -> dict[str, object]:
    """No new auction: exact original E9D source CBAA actor, once per cell."""
    original = run_e9d_original_cbaa_loss_case(
        cost_rows=cost_rows, task_bytes=task_bytes, task_packets=task_packets,
        robots=robots, tasks=tasks, seed=seed, p_loss=p_loss,
        profile=profile, timeout_ms=timeout_ms, round_guard=cbaa_guard,
    )
    original.update({
        "cost_copies": 0, "cost_packet_count": 0,
        "cost_peer_delivery_attempts": 0, "cost_peer_delivered_packets": 0,
        "cost_distinct_peer_receipts": 0,
        "initial_cost_peer_reach_fraction": "",
        "initial_mean_visible_cost_rows": "",
    })
    original.pop("locally_certified_count", None)
    return original


def require_e9f_paired_sender_contract(
    *, rows: tuple[dict[str, object], ...],
    cost_copies: tuple[int, ...],
    robots: int, tasks: int, seed: int, loss_probability: float,
    task_bytes: int,
) -> None:
    """Strict evidence: exactly original Greedy variants plus ORIGINAL CBAA."""
    expected = tuple(f"democracy_cost_copies_{m}" for m in cost_copies) + (CBAA_ID,)
    observed = tuple(str(r["method"]) for r in rows)
    if observed != expected or any(
        row["seed"] != seed or row["loss_probability"] != loss_probability
        or row["task_sender_bytes"] != task_bytes for row in rows
    ):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="require_e9f_paired_sender_contract",
            category="contract", code="E9F_METHOD_PAIRING_MISMATCH",
            expected={"methods": expected, "seed": seed, "loss": loss_probability},
            actual={"methods": observed, "seeds": [r["seed"] for r in rows]},
        ))
    for row in rows:
        parts = ("cost_sender_bytes", "vote_sender_bytes",
                 "score_sender_bytes", "commit_sender_bytes",
                 "cbaa_bid_sender_bytes")
        derived = sum(int(row[k]) for k in parts)
        reported = int(row["coordination_sender_bytes"])
        total = int(row["total_sender_bytes"])
        sent = int(row["coordination_delivered"]) + int(row["coordination_dropped"])
        opportunities = int(row["coordination_delivery_attempts"])
        if (reported != derived or total != task_bytes + derived
            or sent != opportunities):
            raise ProtocolError(Diagnostic(
                owner=OWNER, function="require_e9f_paired_sender_contract",
                category="contract", code="E9F_PHYSICAL_SENDER_BYTES_MISMATCH",
                expected={"coordination_bytes": derived,
                          "total_bytes": task_bytes+derived,
                          "delivery_attempts": opportunities},
                actual={"coordination_bytes": reported, "total_bytes": total,
                        "delivered_plus_dropped": sent},
                details=f"seed={seed} p={loss_probability} method={row['method']}",
            ))
        if row["method"] == CBAA_ID:
            if row["cost_packet_count"] != 0 or row["cost_sender_bytes"] != 0:
                raise ProtocolError(Diagnostic(
                    owner=OWNER,function="require_e9f_paired_sender_contract",
                    category="contract",code="E9F_FAKE_CBAA_COST",
                    expected="original own Bid/Winner only; no foreign Cost or peer pose",
                    actual=(row["cost_packet_count"],row["cost_sender_bytes"]),
                ))
        else:
            m = int(row["cost_copies"])
            packets = robots*m
            amount = packets*cost_row_payload_bytes(tasks)
            expected_delivery_attempts = packets*(robots-1)
            if (row["cost_packet_count"] != packets
                or row["cost_sender_bytes"] != amount
                or row["cost_peer_delivery_attempts"] != expected_delivery_attempts
                or not 0 <= row["initial_cost_peer_reach_fraction"] <= 1):
                raise ProtocolError(Diagnostic(
                    owner=OWNER, function="require_e9f_paired_sender_contract",
                    category="contract", code="E9F_COST_RETRANSMISSION_LEDGER",
                    expected={"packets": packets, "bytes": amount,
                              "peer_receipt_attempts": expected_delivery_attempts},
                    actual={"packets": row["cost_packet_count"],
                            "bytes": row["cost_sender_bytes"],
                            "peer_receipt_attempts": row["cost_peer_delivery_attempts"]},
                    details=f"seed={seed} p={loss_probability} copies={m}",
                ))


def summarize_e9f_cost_study(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Never censor failed runs or equate CBAA local stop with actual Commit."""
    buckets: dict[tuple[float,str],list[dict[str,object]]] = {}
    for row in rows:
        buckets.setdefault(
            (float(row["loss_probability"]),str(row["method"])),[]
        ).append(row)
    output = []
    for (p, method), subset in sorted(buckets.items()):
        is_cbaa = method == CBAA_ID
        n = len(subset)
        full_count = sum(
            int(x["all_locally_certified"] if is_cbaa else x["full_commit"])
            for x in subset
        )
        sender_bytes = [int(x["total_sender_bytes"]) for x in subset]
        output.append({
            "loss_probability": p, "method": method, "seeds": n,
            "cost_copies": int(subset[0]["cost_copies"]),
            "full_outcome_count": full_count,
            "full_outcome_rate": full_count / n,
            "complete_outcome_semantics": (
                "CBAA_local_receipt_certificate_optimistic_halt" if is_cbaa
                else "Democracy_actual_reliable_Commit"
            ),
            "mean_sender_application_bytes": statistics.mean(sender_bytes),
            "min_sender_application_bytes": min(sender_bytes),
            "max_sender_application_bytes": max(sender_bytes),
            "mean_cost_sender_bytes": statistics.mean(
                int(x["cost_sender_bytes"]) for x in subset
            ),
            "mean_initial_cost_peer_reach_fraction": (
                "" if is_cbaa else statistics.mean(
                    float(x["initial_cost_peer_reach_fraction"]) for x in subset
                )
            ),
            "mean_confirmed_or_observer_tasks": statistics.mean(
                int(x["tasks_confirmed"]) for x in subset
            ),
            "mean_rounds": statistics.mean(
                int(x["rounds_executed"]) for x in subset
            ),
            "guard_hit_count": sum(int(x["safety_guard_hit"]) for x in subset),
            "cbaa_external_full_agreement_count": (
                sum(int(x["full_observer_agreement"]) for x in subset)
                if is_cbaa else ""
            ),
            "completed_only_mean_sender_bytes": (
                statistics.mean(
                    int(x["total_sender_bytes"]) for x in subset
                    if int(x["all_locally_certified"] if is_cbaa else x["full_commit"])
                ) if full_count else ""
            ),
        })
    return output


def calculate_e9f_empirical_frontier(
    summary: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    """Finite-sample successful p range; guard stops are NOT theoretical limits."""
    result={}
    for method in sorted({r["method"] for r in summary}):
        group=sorted(
            (r for r in summary if r["method"] == method),
            key=lambda x: x["loss_probability"],
        )
        all_pass=[r["loss_probability"] for r in group
                  if r["full_outcome_count"] == r["seeds"]]
        any_pass=[r["loss_probability"] for r in group
                  if r["full_outcome_count"] > 0]
        first_below_all=next((r["loss_probability"] for r in group
                              if r["full_outcome_count"] < r["seeds"]),None)
        result[method]={
            "highest_tested_loss_all_seed_outcomes": max(all_pass) if all_pass else None,
            "highest_tested_loss_any_full_outcome": max(any_pass) if any_pass else None,
            "first_sampled_loss_below_100pct": first_below_all,
            "has_safety_guard_censoring": any(r["guard_hit_count"] for r in group),
            "measured_finite_sample_not_proven_packet_loss_limit": True,
        }
    return result


def write_e9f_cost_evidence(
    *,
    output_root: Path, partial_csv: Path,
    rows: list[dict[str, object]],
    robots: int, tasks: int, seeds: int, first_seed: int,
    losses: tuple[float, ...], cost_copies: tuple[int, ...],
    cbaa_guard: int, democracy_guard: int,
    latency_mode: str, latency_detail: str, source_sha: str,
) -> tuple[Path,Path,Path]:
    """Immutable full original-method raw/summary with complete SHA provenance."""
    raw=output_root/"per_seed_cost_copy_method.csv"
    os.replace(partial_csv,raw)
    summary=output_root/"summary_cost_copies_by_loss.csv"
    manifest=output_root/"manifest.json"
    by_method=summarize_e9f_cost_study(rows)
    with summary.open("w",newline="",encoding="utf-8") as fd:
        writer=csv.DictWriter(fd,fieldnames=list(by_method[0]))
        writer.writeheader()
        writer.writerows(by_method)
    meta={
        "experiment": "E9F Cost-repetition original Greedy versus original CBAA",
        "source_git_sha": source_sha,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "robots":robots, "tasks":tasks,"seeds":seeds,"first_seed":first_seed,
        "loss_probabilities":list(losses),"cost_copies":list(cost_copies),
        "methods": [*(f"democracy_cost_copies_{m}" for m in cost_copies),CBAA_ID],
        "expected_raw_rows": seeds*len(losses)*(len(cost_copies)+1),
        "actual_raw_rows":len(rows),
        "cbaa_natural_stop_not_fixed_K":True,
        "cbaa_safety_round_guard_not_manual_K":cbaa_guard,
        "democracy_safety_round_guard":democracy_guard,
        "cost_copy_mode": "fixed_open_loop_no_ack",
        "each_cost_copy_has_unique_sender_and_receiver_loss_keys":True,
        "each_copy_physically_charged_even_if_receiver_drops":True,
        "cost_once_per_run_not_each_retry":True,
        "no_extra_peer_poses_given_to_cbaa":True,
        "task_announcement_guaranteed_p_loss_zero_and_charged":True,
        "score_commit_original_reliable":True,
        "cbaa_completion_is_optimistic_local_certificate_without_paid_stop_ack":True,
        "cbaa_observer_agreement_not_original_actual_commit":True,
        "not_wifi_MAC_PHY_ACK_or_real_radio_airtime":True,
        "latency_mode":latency_mode, "latency_details":latency_detail,
        "physical_cost_row_packet_bytes":cost_row_payload_bytes(tasks),
        "empirical_frontier":calculate_e9f_empirical_frontier(by_method),
        "sha256":{
            path.name:hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (raw,summary)
        },
    }
    manifest.write_text(json.dumps(meta,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return raw,summary,manifest


def run_e9f_cost_redundancy(
    *,
    robots: int=100,tasks: int=50,
    seeds: int=100,first_seed: int=0,
    loss_probabilities: tuple[float,...]=DEFAULT_LOSSES,
    cost_copies: tuple[int,...]=DEFAULT_COST_COPIES,
    cbaa_safety_round_limit: int=160,
    democracy_safety_round_limit: int=300,
    latency_mode: str="constant",
    dataset_path: Path=Path("data/external/rady/perama_range_testing.json"),
    allow_download: bool=True,
    output_root: Path=DEFAULT_ROOT,
) -> list[dict[str, object]]:
    """ONE paired seed/p orchestrator; stream actual evidence, never overwrite."""
    validate_e9f_sweep_axes(
        robots=robots,tasks=tasks,seeds=seeds,first_seed=first_seed,
        losses=loss_probabilities,cost_copies=cost_copies,
        cbaa_guard=cbaa_safety_round_limit,
        democracy_guard=democracy_safety_round_limit,
        latency_mode=latency_mode,
    )
    prepare_e9f_output_root(output_root)
    profile,timeout_ms,latency_detail=select_network_sampler(
        latency_mode=latency_mode,
        dataset=dataset_path,allow_download=allow_download,
    )
    output_root.mkdir(parents=True,exist_ok=True)
    partial=output_root/"per_seed_cost_copy_method.partial.csv"
    rows=[]
    source_sha=read_retirement_revision()
    with partial.open("w",encoding="utf-8",newline="") as fd:
        writer=None
        for index in range(seeds):
            seed=first_seed+index
            cost_rows,task_trace=capture_seed_information(
                seed=seed,robots=robots,tasks=tasks,
                profile=profile,timeout_ms=timeout_ms,
            )
            task_bytes=task_trace.sender_bytes
            task_packets=len(task_trace.events)
            for p_loss in loss_probabilities:
                cell=tuple(run_e9f_democracy_cost_case(
                    cost_rows=cost_rows,task_bytes=task_bytes,
                    task_packets=task_packets,robots=robots,tasks=tasks,
                    seed=seed,p_loss=p_loss,copies=copies,
                    profile=profile,timeout_ms=timeout_ms,
                    democracy_guard=democracy_safety_round_limit,
                ) for copies in cost_copies)
                cbaa=run_e9f_cbaa_reference_case(
                    cost_rows=cost_rows,task_bytes=task_bytes,
                    task_packets=task_packets,robots=robots,tasks=tasks,
                    seed=seed,p_loss=p_loss,profile=profile,
                    timeout_ms=timeout_ms,cbaa_guard=cbaa_safety_round_limit,
                )
                cell=(*cell,cbaa)
                require_e9f_paired_sender_contract(
                    rows=cell,cost_copies=cost_copies,robots=robots,tasks=tasks,
                    seed=seed,loss_probability=p_loss,task_bytes=task_bytes,
                )
                if writer is None:
                    writer=csv.DictWriter(fd,fieldnames=list(cell[0]))
                    writer.writeheader()
                for row in cell:
                    writer.writerow(row)
                    rows.append(row)
                fd.flush()
            if (index+1)%5==0 or index+1==seeds:
                print("E9F_PROGRESS seeds={}/{} cells={} rows={} sha={}".format(
                    index+1,seeds,(index+1)*len(loss_probabilities),
                    len(rows),source_sha,
                ),flush=True)
    raw,summary,manifest=write_e9f_cost_evidence(
        output_root=output_root,partial_csv=partial,rows=rows,
        robots=robots,tasks=tasks,seeds=seeds,first_seed=first_seed,
        losses=loss_probabilities,cost_copies=cost_copies,
        cbaa_guard=cbaa_safety_round_limit,
        democracy_guard=democracy_safety_round_limit,
        latency_mode=latency_mode,latency_detail=latency_detail,
        source_sha=source_sha,
    )
    derived=summarize_e9f_cost_study(rows)
    for item in derived:
        print(
            "E9F_RESULT loss={:.2f} method={} full={}/{} "
            "mean_bytes={:.1f} mean_tasks={:.3f} mean_cost_peer_reach={} "
            "mean_rounds={:.2f} guard_hit={}".format(
                item["loss_probability"],item["method"],
                item["full_outcome_count"],item["seeds"],
                item["mean_sender_application_bytes"],
                item["mean_confirmed_or_observer_tasks"],
                item["mean_initial_cost_peer_reach_fraction"],
                item["mean_rounds"],item["guard_hit_count"],
            ),flush=True,
        )
    print("E9F_FRONTIER="+json.dumps(
        calculate_e9f_empirical_frontier(derived),sort_keys=True,
    ),flush=True)
    print(f"E9F_SOURCE_SHA={source_sha}\nE9F_RAW={raw}\n"
          f"E9F_SUMMARY={summary}\nE9F_MANIFEST={manifest}",flush=True)
    print("E9F_WARNING=Cost copy repeats are sender-paid open-loop, not ACK ARQ; "
          "CBAA local stop is optimistic; no full distributed CBAA Commit; "
          "guard-censored runs are not mathematical packet-loss limits",flush=True)
    return rows


def main() -> None:
    parser=argparse.ArgumentParser(
        description="Original Democracy paid Cost copies versus original CBAA loss sweep"
    )
    parser.add_argument("--robots",type=int,default=100)
    parser.add_argument("--tasks",type=int,default=50)
    parser.add_argument("--seeds",type=int,default=100)
    parser.add_argument("--first-seed",type=int,default=0)
    parser.add_argument("--loss-probabilities",type=parse_probabilities,
                        default=DEFAULT_LOSSES)
    parser.add_argument("--cost-copies",type=parse_e9f_cost_copy_grid,
                        default=DEFAULT_COST_COPIES)
    parser.add_argument("--cbaa-safety-round-limit",type=int,default=160)
    parser.add_argument("--democracy-safety-round-limit",type=int,default=300)
    parser.add_argument("--latency-mode",choices=("constant","rady"),
                        default="constant")
    parser.add_argument("--dataset",type=Path,
                        default=Path("data/external/rady/perama_range_testing.json"))
    parser.add_argument("--no-download",action="store_true")
    parser.add_argument("--output-root",type=Path,default=DEFAULT_ROOT)
    args=parser.parse_args()
    run_e9f_cost_redundancy(
        robots=args.robots,tasks=args.tasks,
        seeds=args.seeds,first_seed=args.first_seed,
        loss_probabilities=args.loss_probabilities,
        cost_copies=args.cost_copies,
        cbaa_safety_round_limit=args.cbaa_safety_round_limit,
        democracy_safety_round_limit=args.democracy_safety_round_limit,
        latency_mode=args.latency_mode,
        dataset_path=args.dataset,allow_download=not args.no_download,
        output_root=args.output_root,
    )


if __name__=="__main__":
    main()
