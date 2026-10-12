"""E9L loss-aware distributed epsilon price auction; E9I/J/K frozen controls.

The Bertsekas price increment is used in a new task-home packet implementation.
This is not CBBA and has optimistic all-local termination, not Voting Commit.
It uses the same task announcements, native sender counters and Rady + assumed
144Mbps model, but its 28B BID/AWARD waves have their own size-aware window.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess

from democracy_mrta.diagnostics import Diagnostic,ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler,ensure_rady_dataset,load_rady_latency_profile,
    estimate_e9l_price_auction_stage_ms,
)
from democracy_mrta.price_auction import PACKET,simulate_price_auction
from democracy_mrta.optimizer import solve_hungarian_assignment
from democracy_mrta.scenario import generate_e0_scenario
from democracy_mrta.task_information import (
    broadcast_task_information,reconstruct_local_cost_rows,
)
from experiments.cbaa_baseline_registry import (
    E9J_ZIP_SHA256,load_pinned_e9j_cbaa_baseline,
    E9K_ZIP_SHA,load_pinned_e9k_paid_baseline,
)
from experiments.voting_baseline_registry import (
    BASE_ZIP_SHA,load_pinned_e9i_voting_baseline,
)
from experiments.run_e9c_real_information import require_local_source_consistency
from experiments.run_e9g_wifi_scaling import create_e9g_sampler,parse_e9g_sizes

OWNER="experiments.run_e9l_price_auction"
PHY_RATE=144.0
BID_LOSS=AWARD_LOSS=.30
EPSILON_METERS=10.0  # Frozen 10-meter additive epsilon price bid; not tuned per seed.
ROUND_SAFETY_GUARD=160


def validate_e9l_axes(*,sizes,seeds,first_seed,guard,e9i_zip,e9j_zip,e9k_zip,
                       allow_unpaired_smoke):
    """Data/contract owner. Original complete archives required for formal."""
    valid=(sizes and all(type(n) is int and n in range(5,101,5) for n in sizes)
           and len(set(sizes))==len(sizes)
           and type(seeds) is int and 1<=seeds<=100
           and type(first_seed) is int and 0<=first_seed<100
           and first_seed+seeds<=100
           and type(guard) is int and 1<=guard<=2000)
    if not valid:
        raise ProtocolError(Diagnostic(owner=OWNER,function="validate_e9l_axes",
            category="data",code="E9L_INVALID_GRID",
            expected="unique N=T=5..100 step5; 1..100 seeds in [0,99]; guard1..2000",
            actual={"sizes":sizes,"seeds":seeds,"first_seed":first_seed,"guard":guard}))
    original=(e9i_zip,e9j_zip,e9k_zip)
    if allow_unpaired_smoke:
        if any(v is not None for v in original) or max(sizes)>20 or seeds>3:
            raise ProtocolError(Diagnostic(owner=OWNER,function="validate_e9l_axes",
                category="contract",code="E9L_SMOKE_REQUIRES_SMALL_UNPAIRED",
                expected="N<=20, seeds<=3, no archives",actual=(sizes,seeds,original)))
    elif any(v is None for v in original):
        raise ProtocolError(Diagnostic(owner=OWNER,function="validate_e9l_axes",
            category="contract",code="E9L_THREE_FROZEN_ARCHIVES_REQUIRED",
            expected="original E9I/E9J/E9K SHA-pinned ZIPs",actual=tuple(map(str,original))))


def prepare_e9l_root(root:Path) -> None:
    """State owner; no existing formal or partial evidence can be replaced."""
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ProtocolError(Diagnostic(owner=OWNER,function="prepare_e9l_root",
            category="state",code="E9L_OUTPUT_EXISTS",expected="new empty output root",actual=str(root)))
    root.mkdir(parents=True,exist_ok=True)


def validate_e9l_paired_scene(*,e9i,e9j,e9k,n,seed,task_bytes,task_ms,oracle):
    """Contract owner: original hashes are checked by the three registries."""
    if e9i is None:
        if e9j is not None or e9k is not None:
            raise ProtocolError(Diagnostic(owner=OWNER,function="validate_e9l_paired_scene",
                category="contract",code="E9L_PARTIAL_PAIR_INVALID",
                expected="all old baseline rows or none",actual=(e9i,e9j,e9k)))
        return
    valid=(
        int(e9j["seed"])==seed and int(e9j["robots"])==n
        and int(e9j["tasks"])==n
        and int(e9k["seed"])==seed and int(e9k["robots"])==n
        and int(e9k["tasks"])==n
        and int(e9j["task_sender_bytes"])==task_bytes
        and int(e9k["original_TASK_sender_bytes"])==task_bytes
        and math.isclose(float(e9j["task_announcement_ms"]),task_ms,rel_tol=1e-10,abs_tol=1e-7)
        and math.isclose(float(e9k["task_announcement_ms"]),task_ms,rel_tol=1e-10,abs_tol=1e-7)
        and math.isclose(float(e9j["external_Hungarian_optimal_cost"]),oracle,rel_tol=1e-12,abs_tol=1e-8)
        and math.isclose(float(e9k["external_hungarian_cost"]),oracle,rel_tol=1e-12,abs_tol=1e-8)
        and math.isclose(float(e9j["allocation_or_stop_ms"]),float(e9k["E9J_old_free_stop_ms"]),rel_tol=1e-12,abs_tol=1e-7)
        and int(e9j["total_original_sender_bytes"])==int(e9k["E9J_old_sender_bytes"])
        and math.isclose(float(e9i["successful_allocation_ms"]),float(e9k["Voting_original_success_ms"]),rel_tol=1e-10,abs_tol=1e-7)
        and int(e9i["total_sender_application_bytes"])==int(e9k["Voting_original_sender_bytes"])
    )
    if not valid:
        raise ProtocolError(Diagnostic(owner=OWNER,function="validate_e9l_paired_scene",
            category="contract",code="E9L_E9I_E9J_E9K_SCENE_OR_PAIR_MISMATCH",
            expected="exact same original scene/task/seed/verified original times and bytes",
            actual={"n":n,"seed":seed,"bytes":task_bytes,"task_time_ms":task_ms,
                    "oracle":oracle}))


def run_e9l_case(*,scenario,profile,seed,n,guard,e9i=None,e9j=None,e9k=None)->dict:
    """Native 28B BID/AWARD method, no global agent-price or cost oracle."""
    task_channel=create_e9g_sampler(profile=profile,seed=seed,phy_rate_mbps=PHY_RATE)
    loss=BernoulliLossSampler(seed=seed)
    announcement=broadcast_task_information(
        task_positions=scenario.task_positions,num_robots=n,
        sampler=task_channel,loss_sampler=loss,p_loss=0.0,
        phase_timeout_ms=1.0e9,
    )
    costs=reconstruct_local_cost_rows(
        local_robot_positions=scenario.robot_positions,
        announced_tasks_by_robot=announcement.per_robot_tasks,
    )
    require_local_source_consistency(reconstructed=costs,expected=scenario.cost_matrix)
    task_ms=max((event.arrival_time_ms for event in announcement.events),default=0.0)
    oracle=solve_hungarian_assignment(scenario.cost_matrix).total_cost
    validate_e9l_paired_scene(e9i=e9i,e9j=e9j,e9k=e9k,n=n,seed=seed,
        task_bytes=announcement.sender_bytes,task_ms=task_ms,oracle=oracle)
    window=estimate_e9l_price_auction_stage_ms(
        profile=profile,robots=n,packet_bytes=PACKET.size,reference_phy_mbps=PHY_RATE)
    auction_channel=create_e9g_sampler(profile=profile,seed=seed,phy_rate_mbps=PHY_RATE)
    result=simulate_price_auction(
        cost_matrix=costs,sampler=auction_channel,loss_sampler=loss,
        bid_loss=BID_LOSS,award_loss=AWARD_LOSS,epsilon=EPSILON_METERS,
        stage_window_ms=window,safety_rounds=guard,capture_audit=False)
    network=auction_channel.summarize_network()
    task_network=task_channel.summarize_network()
    n_packets=result.bid_sends+result.award_sends
    if (network["packet_count"]!=n_packets
        or network["application_sender_bytes"]!=result.sender_bytes
        or result.sender_bytes!=PACKET.size*n_packets
        or result.delivery_attempts!=result.bid_sends+(n-1)*result.award_sends
        or task_network["application_sender_bytes"]!=announcement.sender_bytes
        or task_network["packet_count"]!=len(announcement.events)):
        raise ProtocolError(Diagnostic(owner=OWNER,function="run_e9l_case",
            category="contract",code="E9L_NATIVE_PACKET_LEDGER_MISMATCH",
            expected={"packet_B":PACKET.size,"sends":n_packets,
                      "attempts":result.bid_sends+(n-1)*result.award_sends},
            actual={"packet_count":network["packet_count"],
                    "sender_bytes":network["application_sender_bytes"],
                    "receivers":result.delivery_attempts},
            details=f"N={n} seed={seed}"))
    total_bytes=result.sender_bytes+announcement.sender_bytes
    total_sends=n_packets+len(announcement.events)
    certified=(result.optimistic_local_stop and result.observer_full
               and len(result.assignment)==n)
    cost=sum(costs[robot][task] for robot,task in result.assignment)
    old_voting_time=float(e9i["successful_allocation_ms"]) if e9i is not None else None
    old_e9j_time=float(e9j["allocation_or_stop_ms"]) if e9j is not None else None
    old_e9k_time=float(e9k["all_seed_paid_stop_ms"]) if e9k is not None else None
    return {
        "N":n,"robots":n,"tasks":n,"seed":seed,
        "method":result.method,"bid_loss":BID_LOSS,"award_loss":AWARD_LOSS,
        "epsilon_cost_units":EPSILON_METERS,"modeled_phy_mbps":PHY_RATE,
        "native_bid_packet_bytes":PACKET.size,"native_award_packet_bytes":PACKET.size,
        "bid_and_award_stage_window_ms":window,"round_safety_guard":guard,
        "round_count":result.round_count,"stop_reason":result.stop_reason,
        "auction_optimistic_local_certified":int(result.optimistic_local_stop),
        "auction_local_certified_robot_count":result.local_certified_count,
        "auction_observer_full_assignment":int(result.observer_full),
        "auction_complete_both":int(certified),
        "auction_pending_bidder_count":result.pending_bidder_count,
        "auction_agreed_task_count":len(result.assignment),
        "bid_sender_SENDs":result.bid_sends,"award_sender_SENDs":result.award_sends,
        "auction_sender_application_bytes":result.sender_bytes,
        "native_receiver_opportunities":result.delivery_attempts,
        "native_receiver_drops":result.delivery_drops,
        "native_late_deliveries":result.late_deliveries,
        "original_TASK_sender_bytes":announcement.sender_bytes,
        "original_TASK_sender_SENDs":len(announcement.events),
        "total_original_sender_SENDs":total_sends,
        "total_original_sender_bytes":total_bytes,
        "task_announcement_ms":task_ms,
        "auction_all_seed_stop_ms":result.elapsed_ms+task_ms,
        "auction_successful_allocation_ms":result.elapsed_ms+task_ms if certified else "",
        "external_hungarian_optimal_cost":oracle,
        "auction_observer_cost":cost if result.observer_full else "",
        "auction_cost_over_hungarian_if_full":cost/oracle if result.observer_full else "",
        "modeled_radio_airtime_ms":network["total_airtime_ms"]+task_network["total_airtime_ms"],
        "Voting_original_full_commit":int(e9i["full_commit"]) if e9i is not None else "",
        "Voting_original_completed_ms":old_voting_time if old_voting_time is not None else "",
        "Voting_original_sender_bytes":int(e9i["total_sender_application_bytes"]) if e9i is not None else "",
        "Voting_original_cost_ratio":float(e9i["total_cost_over_hungarian_ratio"]) if e9i is not None else "",
        "E9J_original_CBAA_local_certified":int(e9j["cbaa_certified_and_observer_full"]) if e9j is not None else "",
        "E9J_original_CBAA_free_stop_ms":old_e9j_time if old_e9j_time is not None else "",
        "E9J_original_CBAA_sender_bytes":int(e9j["total_original_sender_bytes"]) if e9j is not None else "",
        "E9J_original_CBAA_cost_ratio":float(e9j["external_cost_over_Hungarian"]) if e9j is not None else "",
        "E9K_original_CBAA_paid_complete":int(e9k["paid_complete"]) if e9k is not None else "",
        "E9K_original_CBAA_paid_ms":old_e9k_time if old_e9k_time is not None else "",
        "E9K_original_CBAA_paid_sender_bytes":int(e9k["full_physical_sender_bytes"]) if e9k is not None else "",
        "E9K_original_CBAA_paid_cost_ratio":float(e9k["paid_cost_over_hungarian"]) if e9k is not None else "",
        "endpoint_note":"auction simulator optimistic all-local AWARD certificate; original Voting reliable Commit; paid CBAA local two-wave receipts",
    }


def summarize_e9l(rows:list[dict])->list[dict]:
    """All-seed means separate from successful-allocation means."""
    groups={}
    for r in rows:groups.setdefault(r["N"],[]).append(r)
    summary=[]
    for n,group in sorted(groups.items()):
        successes=[r for r in group if r["auction_complete_both"]]
        paired=[r for r in successes if r["Voting_original_full_commit"]==1
                and r["E9J_original_CBAA_local_certified"]==1
                and r["E9K_original_CBAA_paid_complete"]==1]
        summary.append({
            "N":n,"seeds":len(group),"new_auction_complete":len(successes),
            "new_auction_guard_or_unconfirmed":len(group)-len(successes),
            "mean_all_seed_auction_stop_ms":statistics.mean(r["auction_all_seed_stop_ms"] for r in group),
            "mean_successful_auction_ms":statistics.mean(r["auction_successful_allocation_ms"] for r in successes) if successes else "",
            "mean_auction_sender_B":statistics.mean(r["total_original_sender_bytes"] for r in group),
            "mean_auction_SENDs":statistics.mean(r["total_original_sender_SENDs"] for r in group),
            "mean_auction_accepted_cost_over_hungarian":statistics.mean(r["auction_cost_over_hungarian_if_full"] for r in successes) if successes else "",
            "three_way_complete_paired_count":len(paired),
            "mean_Voting_original_completed_ms":statistics.mean(r["Voting_original_completed_ms"] for r in group) if group[0]["Voting_original_completed_ms"]!="" else "",
            "mean_E9J_CBAA_original_ms":statistics.mean(r["E9J_original_CBAA_free_stop_ms"] for r in group) if group[0]["E9J_original_CBAA_free_stop_ms"]!="" else "",
            "mean_E9K_CBAA_paid_ms":statistics.mean(r["E9K_original_CBAA_paid_ms"] for r in group) if group[0]["E9K_original_CBAA_paid_ms"]!="" else "",
            "comparison_requires_same_endpoint":True,
        })
    return summary


def write_e9l_evidence(*,root,raw_path,summary,sha,sizes,seeds,first_seed,guard,
                       e9i_zip,e9j_zip,e9k_zip)->None:
    """Formal raw SHA and original source SHA are separate immutable evidence."""
    if not summary:
        raise ProtocolError(Diagnostic(owner=OWNER,function="write_e9l_evidence",
            category="contract",code="E9L_EMPTY_SUMMARY",expected="nonempty original rows",actual=0))
    summary_path=root/"summary_e9l.csv"
    with summary_path.open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=list(summary[0]));writer.writeheader();writer.writerows(summary)
    manifest={
        "study":"E9L Bertsekas-style lossy per-task-home distributed price auction",
        "status":"FORMAL_SOURCE_PAIRED_SIMULATION" if e9i_zip else "UNPAIRED_SMOKE_ONLY",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "executed_git_sha":sha,
        "original_e9i_zip_SHA256":BASE_ZIP_SHA if e9i_zip else "",
        "original_e9j_zip_SHA256":E9J_ZIP_SHA256 if e9j_zip else "",
        "original_e9k_zip_SHA256":E9K_ZIP_SHA if e9k_zip else "",
        "method":"Bertsekas epsilon price bid; task-home BID/AWARD network adaptation",
        "original_paper_wire_protocol":False,
        "robot_to_task_capacity":1,"N_equals_T_sizes":list(sizes),
        "seed_start":first_seed,"seeds_per_N":seeds,"safety_rounds":guard,
        "epsilon_in_cost_meters":EPSILON_METERS,
        "bid_packet_B":PACKET.size,"award_packet_B":PACKET.size,
        "bid_drop_independent_per_receiver_p":BID_LOSS,
        "award_drop_independent_per_receiver_p":AWARD_LOSS,
        "Task_announcement_reliable_and_paid":True,
        "Wifi_144Mbps_SHARED_MEDIUM_IS_HYPOTHESIS":True,
        "Rady_application_delay_bootstrap":True,
        "auction_final_halt_is_optimistic_all_local_flags":True,
        "auction_paid_distributed_commit":False,
        "ns3_real_80211_verified":False,
        "source_file_sha256":{
            raw_path.name:hashlib.sha256(raw_path.read_bytes()).hexdigest(),
            summary_path.name:hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        },
    }
    (root/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")


def run_e9l(*,sizes,seeds,first_seed,guard,dataset,root,
            e9i_zip=None,e9j_zip=None,e9k_zip=None,
            allow_unpaired_smoke=False,allow_download=True):
    """One new physical method execution per scenario; baselines read-only."""
    validate_e9l_axes(sizes=sizes,seeds=seeds,first_seed=first_seed,guard=guard,
                      e9i_zip=e9i_zip,e9j_zip=e9j_zip,e9k_zip=e9k_zip,
                      allow_unpaired_smoke=allow_unpaired_smoke)
    voting=(load_pinned_e9i_voting_baseline(archive=e9i_zip,sizes=tuple(sizes),
            seeds=seeds,first_seed=first_seed) if e9i_zip else None)
    cbaa=(load_pinned_e9j_cbaa_baseline(archive=e9j_zip,sizes=tuple(sizes),
            seeds=seeds,first_seed=first_seed) if e9j_zip else None)
    paid=(load_pinned_e9k_paid_baseline(archive=e9k_zip,sizes=tuple(sizes),
            seeds=seeds,first_seed=first_seed) if e9k_zip else None)
    profile=load_rady_latency_profile(ensure_rady_dataset(dataset,allow_download=allow_download))
    sha=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    if len(sha)!=40 or any(x not in "0123456789abcdef" for x in sha):
        raise ProtocolError(Diagnostic(owner=OWNER,function="run_e9l",
            category="dependency",code="E9L_INVALID_GIT_SHA",expected="40 lowercase hex",actual=sha))
    prepare_e9l_root(root)
    rows=[]
    partial=root/"per_seed_e9l.partial.csv"
    with partial.open("w",encoding="utf-8",newline="") as f:
        writer=None
        for n in sizes:
            for seed in range(first_seed,first_seed+seeds):
                scene=generate_e0_scenario(seed,n,n)
                key=(n,seed)
                row=run_e9l_case(scenario=scene,profile=profile,seed=seed,n=n,guard=guard,
                    e9i=voting[(n,seed,.30,"adaptive_guarded_k1_received")] if voting else None,
                    e9j=cbaa[key] if cbaa else None,e9k=paid[key] if paid else None)
                rows.append(row)
                if writer is None:
                    writer=csv.DictWriter(f,fieldnames=list(row));writer.writeheader()
                writer.writerow(row)
            f.flush()
            count=sum(r["auction_complete_both"] for r in rows if r["N"]==n)
            print(f"E9L_DONE N={n} auction_certified={count}/{seeds} total={len(rows)}",flush=True)
    if len(rows)!=len(sizes)*seeds:
        raise ProtocolError(Diagnostic(owner=OWNER,function="run_e9l",
            category="contract",code="E9L_INCOMPLETE_RUN_GRID",
            expected=len(sizes)*seeds,actual=len(rows)))
    raw=root/"per_seed_e9l.csv"
    partial.rename(raw)
    write_e9l_evidence(root=root,raw_path=raw,summary=summarize_e9l(rows),
                       sha=sha,sizes=sizes,seeds=seeds,first_seed=first_seed,guard=guard,
                       e9i_zip=e9i_zip,e9j_zip=e9j_zip,e9k_zip=e9k_zip)
    print(f"E9L_COMPLETE cases={len(rows)} root={root}",flush=True)
    return rows


def main():
    p=argparse.ArgumentParser(description="E9L lossy 28-byte task-home Bertsekas-style epsilon price auction")
    p.add_argument("--sizes",type=parse_e9g_sizes,default=tuple(range(5,101,5)))
    p.add_argument("--seeds",type=int,default=100)
    p.add_argument("--first-seed",type=int,default=0)
    p.add_argument("--safety-rounds",type=int,default=ROUND_SAFETY_GUARD)
    p.add_argument("--e9i-zip",type=Path)
    p.add_argument("--e9j-zip",type=Path)
    p.add_argument("--e9k-zip",type=Path)
    p.add_argument("--allow-unpaired-smoke",action="store_true")
    p.add_argument("--dataset",type=Path,default=Path("data/external/rady/perama_range_testing.json"))
    p.add_argument("--no-download",action="store_true")
    p.add_argument("--output-root",type=Path,default=Path("results/e9l_price_auction"))
    a=p.parse_args()
    run_e9l(sizes=a.sizes,seeds=a.seeds,first_seed=a.first_seed,
           guard=a.safety_rounds,dataset=a.dataset,root=a.output_root,
           e9i_zip=a.e9i_zip,e9j_zip=a.e9j_zip,e9k_zip=a.e9k_zip,
           allow_unpaired_smoke=a.allow_unpaired_smoke,
           allow_download=not a.no_download)

if __name__=="__main__":main()
