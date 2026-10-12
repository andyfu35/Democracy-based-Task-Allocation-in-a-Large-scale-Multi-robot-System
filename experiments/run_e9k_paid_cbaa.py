"""E9K: original CBAA + optional *paid* two-phase distributed finalization.

Original E9J CBAA and E9I Voting are immutable SHA-pinned baselines.
E9K changes only the opt-in paid READY/COMMIT extension inside the true CBAA
owner. Native Auction/Max-Consensus messages are NOT rewritten.
Time is a causal 144Mbps shared-medium PROXY with Rady application samples,
not measured real Wi-Fi, ns-3, DCF collision, ARQ, or a common-knowledge proof.
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
import subprocess

from democracy_mrta.cbaa import simulate_cbaa
from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler, ensure_rady_dataset, load_rady_latency_profile,
    estimate_e9j_cbaa_consensus_window_ms,
)
from democracy_mrta.optimizer import solve_hungarian_assignment
from democracy_mrta.scenario import generate_e0_scenario
from democracy_mrta.task_information import (
    broadcast_task_information, reconstruct_local_cost_rows,
)
from experiments.cbaa_baseline_registry import (
    E9J_ZIP_SHA256, E9J_SOURCE_SHA,
    load_pinned_e9j_cbaa_baseline,
)
from experiments.voting_baseline_registry import (
    BASE_ZIP_SHA, load_pinned_e9i_voting_baseline,
)
from experiments.run_e9c_real_information import require_local_source_consistency
from experiments.run_e9g_wifi_scaling import create_e9g_sampler, parse_e9g_sizes

OWNER = "experiments.run_e9k_paid_cbaa"
RATE_MBPS = 144.0
BID_LOSS = READY_LOSS = COMMIT_LOSS = .30
MAX_ROUNDS = 160


def validate_e9k_axes(*, sizes, seeds, first_seed, guard,
                      e9i_zip, e9j_zip, allow_unpaired_smoke) -> None:
    """Guard publication status before any potentially long simulation."""
    allowed=tuple(range(5,101,5))
    if (not sizes or any(type(n) is not int or n not in allowed for n in sizes)
        or type(seeds) is not int or not 1<=seeds<=100
        or type(first_seed) is not int or first_seed<0
        or first_seed+seeds>100 or type(guard) is not int
        or not 1<=guard<=MAX_ROUNDS
        or len(set(sizes))!=len(sizes)):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="validate_e9k_axes",category="data",
            code="E9K_INVALID_AXES",expected="unique N=5..100 step5, seed0..99, guard1..160",
            actual={"sizes":sizes,"seeds":seeds,"first_seed":first_seed,"guard":guard},
        ))
    both=e9i_zip is not None and e9j_zip is not None
    if allow_unpaired_smoke:
        if both or e9i_zip is not None or e9j_zip is not None or seeds>3 or max(sizes)>20:
            raise ProtocolError(Diagnostic(
                owner=OWNER,function="validate_e9k_axes",category="contract",
                code="E9K_SMOKE_WITH_BASELINE_OR_FORMAL_SIZE",
                expected="unpaired <=3seed <=20N smoke with no baseline archives",
                actual={"seeds":seeds,"sizes":sizes,"e9i":str(e9i_zip),
                        "e9j":str(e9j_zip)},
            ))
    elif not both:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="validate_e9k_axes",category="contract",
            code="E9K_BOTH_PINNED_BASELINES_REQUIRED",
            expected="original SHA-pinned E9I ZIP AND original E9J ZIP",
            actual={"e9i":str(e9i_zip),"e9j":str(e9j_zip)},
        ))


def prepare_e9k_output(root: Path) -> None:
    """Never overwrite original or partial experimental evidence."""
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="prepare_e9k_output",category="state",
            code="E9K_OUTPUT_EXISTS",expected="new empty output directory",
            actual=str(root),
        ))
    root.mkdir(parents=True,exist_ok=True)


def validate_e9k_original_scene(*, old, n, seed, deadline, task_sender_bytes,
                                task_time_ms, oracle_cost) -> None:
    """Source scene/radio identity; an old row is NEVER synthesized as fallback."""
    if old is None:
        return
    same=(
        int(old["robots"])==n and int(old["tasks"])==n
        and int(old["seed"])==seed
        and math.isclose(float(old["cbaa_iteration_timeout_ms"]),deadline,
                         rel_tol=1e-10,abs_tol=1e-7)
        and int(old["task_sender_bytes"])==task_sender_bytes
        and math.isclose(float(old["task_announcement_ms"]),task_time_ms,
                         rel_tol=1e-10,abs_tol=1e-7)
        and math.isclose(float(old["external_Hungarian_optimal_cost"]),oracle_cost,
                         rel_tol=1e-12,abs_tol=1e-8)
    )
    if not same:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="validate_e9k_original_scene",
            category="contract",code="E9K_E9J_SCENE_OR_RADIO_MISMATCH",
            expected="same N, seed, Rady deadline, TASK source bytes/time, Hungarian oracle",
            actual={"n":n,"seed":seed,"deadline":deadline,
                    "task_bytes":task_sender_bytes,"task_ms":task_time_ms,
                    "oracle":oracle_cost},
            details="Pinned E9J baseline must have the identical external scenario",
        ))


def run_e9k_paid_case(*, scenario, profile, seed, n, guard,
                      old_e9j=None, old_voting=None) -> dict:
    """One native CBAA execution with *paid* local FINAL receipts."""
    task_sampler=create_e9g_sampler(
        profile=profile,seed=seed,phy_rate_mbps=RATE_MBPS,
    )
    loss_sampler=BernoulliLossSampler(seed=seed)
    announced=broadcast_task_information(
        task_positions=scenario.task_positions, num_robots=n,
        sampler=task_sampler, loss_sampler=loss_sampler,p_loss=0.0,
        phase_timeout_ms=1.0e9,
    )
    cost_rows=reconstruct_local_cost_rows(
        local_robot_positions=scenario.robot_positions,
        announced_tasks_by_robot=announced.per_robot_tasks,
    )
    require_local_source_consistency(
        reconstructed=cost_rows,expected=scenario.cost_matrix,
    )
    task_ms=max((e.arrival_time_ms for e in announced.events),default=0.0)
    oracle=solve_hungarian_assignment(scenario.cost_matrix).total_cost
    deadline=estimate_e9j_cbaa_consensus_window_ms(
        profile=profile,robots=n,tasks=n,reference_phy_mbps=RATE_MBPS,
    )
    validate_e9k_original_scene(
        old=old_e9j,n=n,seed=seed,deadline=deadline,
        task_sender_bytes=announced.sender_bytes,task_time_ms=task_ms,
        oracle_cost=oracle,
    )
    channel=create_e9g_sampler(
        profile=profile,seed=seed,phy_rate_mbps=RATE_MBPS,
    )
    cbaa=simulate_cbaa(
        cost_matrix=cost_rows,sampler=channel,loss_sampler=loss_sampler,
        loss_probability=BID_LOSS,phase_timeout_ms=deadline,
        control_timeout_ms=deadline,ready_loss_probability=READY_LOSS,
        commit_loss_probability=COMMIT_LOSS,
        max_iterations=guard,stop_mode="paid_termination",
        capture_audit=False,
    )
    native_send_count=cbaa.logical_message_count
    paid_send_count=cbaa.paid_ready_sends+cbaa.paid_commit_sends
    if (native_send_count!=n*cbaa.iterations
        or cbaa.payload_bytes!=native_send_count*(16+12*n)
        or cbaa.delivery_attempts!=native_send_count*(n-1)
        or cbaa.paid_sender_bytes!=paid_send_count*48
        or cbaa.paid_receiver_attempts!=paid_send_count*(n-1)):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="run_e9k_paid_case",category="contract",
            code="E9K_NATIVE_VS_PAID_PACKET_LEDGER_MISMATCH",
            expected="native N*(16+12N) vector SENDs + 48B control SENDs",
            actual={"native_SENDs":native_send_count,
                    "native_B":cbaa.payload_bytes,
                    "paid_SENDs":paid_send_count,
                    "paid_B":cbaa.paid_sender_bytes},
        ))
    net=channel.summarize_network()
    task_net=task_sampler.summarize_network()
    expected_total_count=native_send_count+paid_send_count
    expected_total_bytes=cbaa.payload_bytes+cbaa.paid_sender_bytes
    if (net["packet_count"]!=expected_total_count
        or net["application_sender_bytes"]!=expected_total_bytes
        or task_net["application_sender_bytes"]!=announced.sender_bytes):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="run_e9k_paid_case",category="contract",
            code="E9K_PHYSICAL_RADIO_LEDGER_MISMATCH",
            expected=(expected_total_count,expected_total_bytes,
                      announced.sender_bytes),
            actual=(net["packet_count"],net["application_sender_bytes"],
                    task_net["application_sender_bytes"]),
        ))
    paid_success=(
        cbaa.paid_termination_complete and cbaa.full_observer_agreement
        and len(cbaa.observer_agreed_pairs)==n
        and cbaa.stop_reason=="all_paid_commit_proofs_received"
    )
    cost=sum(cost_rows[r][j] for r,j in cbaa.observer_agreed_pairs)
    total_bytes=announced.sender_bytes+expected_total_bytes
    total_sends=len(announced.events)+expected_total_count
    paid_stop_ms=task_ms+cbaa.elapsed_ms
    old_time=float(old_e9j["allocation_or_stop_ms"]) if old_e9j is not None else None
    old_bytes=int(old_e9j["total_original_sender_bytes"]) if old_e9j is not None else None
    voting_full=int(old_voting["full_commit"]) if old_voting is not None else None
    voting_time=(
        float(old_voting["successful_allocation_ms"])
        if voting_full else None
    )
    return {
        "robots":n,"tasks":n,"seed":seed,
        "method":"cbaa_original_auction_plus_paid_ready_commit",
        "bid_receiver_loss":BID_LOSS,"ready_receiver_loss":READY_LOSS,
        "commit_receiver_loss":COMMIT_LOSS,
        "assumed_phy_mbps":RATE_MBPS,
        "original_cbaa_synchronization_deadline_ms":deadline,
        "paid_control_phase_deadline_ms":deadline,
        "iterations_including_paid_finalization":cbaa.iterations,
        "stop_reason":cbaa.stop_reason,
        "paid_complete":int(paid_success),
        "paid_locally_confirmed_robots":cbaa.paid_confirmed_robots,
        "native_locally_certified_count_at_stop":cbaa.locally_certified_count,
        "observer_full_agreement":int(cbaa.full_observer_agreement),
        "observer_confirmed_tasks":len(cbaa.observer_agreed_pairs),
        "native_bid_sender_SENDs":native_send_count,
        "native_bid_sender_bytes":cbaa.payload_bytes,
        "paid_ready_sender_SENDs":cbaa.paid_ready_sends,
        "paid_commit_sender_SENDs":cbaa.paid_commit_sends,
        "paid_control_sender_bytes":cbaa.paid_sender_bytes,
        "paid_control_receiver_attempts":cbaa.paid_receiver_attempts,
        "paid_control_receiver_drops":cbaa.paid_receiver_drops,
        "paid_control_late_receipts":cbaa.paid_late_receipts,
        "original_TASK_sender_bytes":announced.sender_bytes,
        "full_physical_sender_SENDs":total_sends,
        "full_physical_sender_bytes":total_bytes,
        "task_announcement_ms":task_ms,
        "native_bid_budget_ms":cbaa.iterations*deadline,
        "paid_control_budget_ms":cbaa.paid_control_elapsed_ms,
        "all_seed_paid_stop_ms":paid_stop_ms,
        "paid_success_time_ms":paid_stop_ms if paid_success else "",
        "E9J_old_free_stop_ms":old_time if old_time is not None else "",
        "E9J_old_sender_bytes":old_bytes if old_bytes is not None else "",
        "extra_stop_ms_vs_E9J":paid_stop_ms-old_time if old_time is not None else "",
        "extra_bytes_vs_E9J":total_bytes-old_bytes if old_bytes is not None else "",
        "Voting_original_full_commit":voting_full if voting_full is not None else "",
        "Voting_original_success_ms":voting_time if voting_time is not None else "",
        "Voting_original_sender_bytes":(
            int(old_voting["total_sender_application_bytes"])
            if old_voting is not None else ""
        ),
        "external_hungarian_cost":oracle,
        "paid_assignment_cost":cost if paid_success else "",
        "paid_cost_over_hungarian":cost/oracle if paid_success else "",
        "modeled_radio_airtime_ms":(
            net["total_airtime_ms"]+task_net["total_airtime_ms"]
        ),
        "model":"assumed 144Mbps Rady shared medium; unpaid AP/PHY features absent",
        "success_semantics":"all participants individually received full READY and COMMIT receipts; not Byzantine safe or infinite common knowledge",
    }


def summarize_e9k_cases(rows:list[dict])->list[dict]:
    """Keep all-seed censored stopping times separate from successful times."""
    groups={}
    for row in rows:
        groups.setdefault(int(row["robots"]),[]).append(row)
    out=[]
    for n,group in sorted(groups.items()):
        successes=[r for r in group if r["paid_complete"]]
        old=[r for r in group if r["E9J_old_free_stop_ms"]!=""]
        paired=[r for r in group
                if r["paid_complete"] and r["E9J_old_free_stop_ms"]!=""
                and r["Voting_original_full_commit"]==1]
        out.append({
            "N":n,"seeds":len(group),
            "paid_complete_count":len(successes),
            "paid_incomplete_or_guard_count":len(group)-len(successes),
            "mean_all_seed_stop_ms":statistics.mean(
                r["all_seed_paid_stop_ms"] for r in group),
            "mean_completed_paid_ms":(
                statistics.mean(r["paid_success_time_ms"] for r in successes)
                if successes else ""
            ),
            "mean_total_sender_bytes":statistics.mean(
                r["full_physical_sender_bytes"] for r in group),
            "mean_paid_control_sender_bytes":statistics.mean(
                r["paid_control_sender_bytes"] for r in group),
            "mean_paid_control_drops":statistics.mean(
                r["paid_control_receiver_drops"] for r in group),
            "mean_original_E9J_free_stop_ms":(
                statistics.mean(r["E9J_old_free_stop_ms"] for r in old)
                if old else ""
            ),
            "mean_paired_paid_minus_free_stop_ms_if_all_success":(
                statistics.mean(r["extra_stop_ms_vs_E9J"] for r in paired)
                if paired else ""
            ),
            "mean_paired_paid_minus_voting_ms_if_all_success":(
                statistics.mean(
                    r["paid_success_time_ms"]-r["Voting_original_success_ms"]
                    for r in paired)
                if paired else ""
            ),
            "paired_three_way_complete_count":len(paired),
            "result_not_equal_to_a_Voting_reliable_commit":True,
        })
    return out


def write_e9k_artifacts(*, root, raw_path, summary, sizes, seeds,
                        first_seed, guard, source_sha, e9i_zip, e9j_zip)->None:
    """Hash only actual user-run source; no copied/recreated E9I/E9J rows."""
    summary_path=root/"summary_e9k.csv"
    with summary_path.open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    manifest={
        "experiment":"E9K native CBAA + paid per-node READY/COMMIT finalization",
        "status":"FORMAL_PAIRED_SIMULATED" if e9i_zip else "UNPAIRED_SMOKE_ONLY",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "executed_git_sha":source_sha,
        "immutable_e9i_voting_zip_SHA256":BASE_ZIP_SHA if e9i_zip else "",
        "immutable_e9j_cbaa_zip_SHA256":E9J_ZIP_SHA256 if e9j_zip else "",
        "immutable_e9j_source_git_sha":E9J_SOURCE_SHA if e9j_zip else "",
        "sizes":list(sizes),"seeds_per_size":seeds,
        "first_seed":first_seed,"guard":guard,
        "bid_loss":BID_LOSS,"ready_loss":READY_LOSS,
        "commit_loss":COMMIT_LOSS,
        "paid_CONTROL_sender_packet_B":48,
        "control_window":"same conservative E9J full-vector phase window; separate paid READY and COMMIT wave",
        "CBAA_native_Auction_MaxConsensus_changed":False,
        "E9I_Voting_rerun":False,
        "fully_distributed_terminal_COMMON_KNOWLEDGE_proven":False,
        "80211ax_ns3_or_field_RF_test":False,
        "user_original_files_sha256":{
            raw_path.name:hashlib.sha256(raw_path.read_bytes()).hexdigest(),
            summary_path.name:hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        },
    }
    (root/"manifest.json").write_text(
        json.dumps(manifest,indent=2)+"\n",encoding="utf-8",
    )


def run_e9k(*, sizes, seeds, first_seed, guard, dataset, root,
            e9i_zip=None, e9j_zip=None, allow_unpaired_smoke=False,
            allow_download=True)->list[dict]:
    """Run one E9K CBAA execution per N/seed; do not rerun original controls."""
    validate_e9k_axes(
        sizes=sizes,seeds=seeds,first_seed=first_seed,guard=guard,
        e9i_zip=e9i_zip,e9j_zip=e9j_zip,
        allow_unpaired_smoke=allow_unpaired_smoke,
    )
    baselines=(
        load_pinned_e9j_cbaa_baseline(
            archive=e9j_zip,sizes=tuple(sizes),
            seeds=seeds,first_seed=first_seed,
        ) if e9j_zip is not None else None
    )
    voting=(
        load_pinned_e9i_voting_baseline(
            archive=e9i_zip,sizes=tuple(sizes),
            seeds=seeds,first_seed=first_seed,
        ) if e9i_zip is not None else None
    )
    profile=load_rady_latency_profile(
        ensure_rady_dataset(dataset,allow_download=allow_download)
    )
    sha=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    if len(sha)!=40 or any(x not in "0123456789abcdef" for x in sha):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="run_e9k",category="dependency",
            code="E9K_INVALID_GIT_SHA",
            expected="Git SHA40 lowercase",actual=sha,
        ))
    prepare_e9k_output(root)
    rows=[]
    partial=root/"per_seed_e9k.partial.csv"
    with partial.open("w",newline="",encoding="utf-8") as f:
        writer=None
        for n in sizes:
            for seed in range(first_seed,first_seed+seeds):
                scene=generate_e0_scenario(seed,n,n)
                row=run_e9k_paid_case(
                    scenario=scene,profile=profile,seed=seed,n=n,
                    guard=guard,
                    old_e9j=baselines[(n,seed)] if baselines else None,
                    old_voting=(
                        voting[(n,seed,.30,"adaptive_guarded_k1_received")]
                        if voting else None
                    ),
                )
                rows.append(row)
                if writer is None:
                    writer=csv.DictWriter(f,fieldnames=list(row))
                    writer.writeheader()
                writer.writerow(row)
            f.flush()
            count=sum(int(r["paid_complete"]) for r in rows
                      if r["robots"]==n)
            print(f"E9K_DONE N={n} PAID={count}/{seeds} ROWS={len(rows)}",flush=True)
    expected=len(sizes)*seeds
    if len(rows)!=expected:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="run_e9k",category="contract",
            code="E9K_INCOMPLETE_GRID",expected=expected,actual=len(rows),
        ))
    original=root/"per_seed_e9k.csv"
    partial.rename(original)
    write_e9k_artifacts(
        root=root,raw_path=original,summary=summarize_e9k_cases(rows),
        sizes=sizes,seeds=seeds,first_seed=first_seed,guard=guard,
        source_sha=sha,e9i_zip=e9i_zip,e9j_zip=e9j_zip,
    )
    print(f"E9K_COMPLETE cases={len(rows)} root={root}",flush=True)
    return rows


def main()->None:
    p=argparse.ArgumentParser(
        description="E9K opt-in native-CBAA PAID finalization, 30% all message classes"
    )
    p.add_argument("--sizes",type=parse_e9g_sizes,
                   default=tuple(range(5,101,5)))
    p.add_argument("--seeds",type=int,default=100)
    p.add_argument("--first-seed",type=int,default=0)
    p.add_argument("--cbaa-safety-rounds",type=int,default=160)
    p.add_argument("--e9i-zip",type=Path)
    p.add_argument("--e9j-zip",type=Path)
    p.add_argument("--allow-unpaired-smoke",action="store_true")
    p.add_argument("--dataset",type=Path,
                   default=Path("data/external/rady/perama_range_testing.json"))
    p.add_argument("--no-download",action="store_true")
    p.add_argument("--output-root",type=Path,
                   default=Path("results/e9k_paid_cbaa"))
    a=p.parse_args()
    run_e9k(
        sizes=a.sizes,seeds=a.seeds,first_seed=a.first_seed,
        guard=a.cbaa_safety_rounds,dataset=a.dataset,
        root=a.output_root,e9i_zip=a.e9i_zip,e9j_zip=a.e9j_zip,
        allow_unpaired_smoke=a.allow_unpaired_smoke,
        allow_download=not a.no_download,
    )


if __name__=="__main__":
    main()
