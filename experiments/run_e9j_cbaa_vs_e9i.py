"""E9J: original CBAA under shared-radio timing, pinned E9I Voting baseline.

Never reimplement CBAA or Voting. Uses the original two-phase CBAA owner.
CBAA local-evidence certification is an optimistic halt, NOT reliable Commit.
Actual 802.11ax/nS-3/real AP contention is NOT measured in this study.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import subprocess
import zipfile
from datetime import datetime, timezone

from democracy_mrta.cbaa import simulate_cbaa
from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler, WifiCausalTimingSampler,
    ensure_rady_dataset, load_rady_latency_profile, percentile,
    estimate_e9j_cbaa_consensus_window_ms,
    RADY_SOURCE_COMMIT, RADY_SOURCE_BLOB_SHA,
)
from democracy_mrta.optimizer import solve_hungarian_assignment
from democracy_mrta.scenario import generate_e0_scenario
from democracy_mrta.task_information import (
    broadcast_task_information, reconstruct_local_cost_rows,
)
from experiments.run_e9c_real_information import require_local_source_consistency
from experiments.run_e9g_wifi_scaling import create_e9g_sampler, parse_e9g_sizes

OWNER = "experiments.run_e9j_cbaa_vs_e9i"
BASE_ZIP_SHA = "5d275bebd8d6f985e8eef1bbba9a0947991cd71660c1cc49817619e6bc276ee5"
BASE_GIT_SHA = "408ff70a31e8c2957602cae3f09ad8f239cd3224"
BASE_CSV_SHA = "1249661d6efeee70c377e76b04176f0923a8051fd983e4aeef3571918041d3f7"
BASE_ARM_NAMES = ("adaptive_guarded_k1_received", "fixed_received")
BASE_VOTE_LOSSES = (0.0, 0.30)
CBAA_BID_LOSS = 0.30
DESIGN_RATE = 144.0
MAX_NATURAL_ITERATIONS = 160


def validate_e9j_axes(*, sizes, seeds, first_seed, guard,
                      baseline_zip, allow_unpaired_smoke) -> None:
    """Require a pinned 100-seed reference for publication, unlike smoke."""
    if (not sizes or type(seeds) is not int or not 1 <= seeds <= 100
        or type(first_seed) is not int or first_seed < 0
        or first_seed+seeds > 100 or type(guard) is not int
        or guard < 1 or guard > MAX_NATURAL_ITERATIONS):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_e9j_axes", category="data",
            code="E9J_INVALID_SCALING_AXES",
            expected="sizes 5..100; 1..100 seeds 0..99; guard 1..160",
            actual={"sizes":sizes,"seeds":seeds,"first_seed":first_seed,
                    "guard":guard},
        ))
    for n in sizes:
        if type(n) is not int or n not in tuple(range(5,101,5)):
            raise ProtocolError(Diagnostic(
                owner=OWNER, function="validate_e9j_axes",category="data",
                code="E9J_INVALID_SCALING_AXES",
                expected="N in 5,10,...,100",actual=n,
            ))
    if baseline_zip is None and (
        not allow_unpaired_smoke or seeds > 3 or max(sizes) > 20
    ):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="validate_e9j_axes",category="contract",
            code="E9J_BASELINE_REQUIRED_FOR_FORMAL_COMPARISON",
            expected="exact pinned E9I baseline archive, or explicit <=3seed <=20N unpaired smoke",
            actual={"baseline_zip":str(baseline_zip),"smoke":allow_unpaired_smoke},
        ))
    if baseline_zip is not None and allow_unpaired_smoke:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="validate_e9j_axes",category="contract",
            code="E9J_PAIRED_AND_SMOKE_MODES_MIXED",
            expected="choose exactly one baseline or unpaired smoke",
            actual="both",
        ))


def load_e9j_pinned_e9i_baseline(*, archive: Path, sizes, seeds,
                                first_seed) -> dict[tuple[int,int,float,str],dict]:
    """Strict raw original archival proof; no replanned baseline runs."""
    if not archive.is_file():
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="load_e9j_pinned_e9i_baseline",
            category="dependency",code="E9J_E9I_ORIGINAL_ARCHIVE_MISSING",
            expected="user-run original e9i_cost30_formal_100seed.zip",
            actual=str(archive),
        ))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != BASE_ZIP_SHA:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="load_e9j_pinned_e9i_baseline",
            category="contract",code="E9J_BASELINE_ARCHIVE_SHA_MISMATCH",
            expected=BASE_ZIP_SHA,actual=digest,
        ))
    try:
        with zipfile.ZipFile(archive) as z:
            manifest=json.loads(z.read("manifest.json"))
            raw=z.read("per_seed_e9i_cost30.csv")
            source_hash=hashlib.sha256(raw).hexdigest()
            rows=list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    except (OSError,zipfile.BadZipFile,KeyError,UnicodeError,
            ValueError,json.JSONDecodeError) as exc:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="load_e9j_pinned_e9i_baseline",
            category="data",code="E9J_INVALID_BASELINE_SOURCE",
            expected="original manifest.json + complete original CSV",
            actual=str(exc),
        )) from exc
    good=(
        manifest.get("source_git_sha")==BASE_GIT_SHA
        and manifest.get("cost_loss_probability_fixed")==CBAA_BID_LOSS
        and manifest.get("vote_loss_probabilities_paired")==[0.0,0.3]
        and manifest.get("phy_rate_mbps_assumed_not_measured")==DESIGN_RATE
        and manifest.get("source_files_sha256",{}).get("per_seed_e9i_cost30.csv")
              ==BASE_CSV_SHA==source_hash
        and manifest.get("raw_cases")==16000 and len(rows)==16000
    )
    if not good:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="load_e9j_pinned_e9i_baseline",
            category="contract",code="E9J_BASELINE_SOURCE_CONTRACT",
            expected={"git_sha":BASE_GIT_SHA,"Cost_p":.3,"rate":144,
                      "raw_sha":BASE_CSV_SHA,"rows":16000},
            actual={"git_sha":manifest.get("source_git_sha"),
                    "Cost_p":manifest.get("cost_loss_probability_fixed"),
                    "rate":manifest.get("phy_rate_mbps_assumed_not_measured"),
                    "raw_sha":source_hash,"rows":len(rows)},
        ))
    requested={(n,seed,vote,arm)
               for n in sizes for seed in range(first_seed,first_seed+seeds)
               for vote in BASE_VOTE_LOSSES for arm in BASE_ARM_NAMES}
    found={}
    for row in rows:
        try:
            key=(int(row["robots"]),int(row["seed"]),
                 float(row["vote_loss_probability"]),str(row["arm"]))
        except (ValueError,TypeError,KeyError) as exc:
            raise ProtocolError(Diagnostic(
                owner=OWNER,function="load_e9j_pinned_e9i_baseline",
                category="data",code="E9J_INVALID_BASELINE_ROW",
                expected="N,seed,Vote_loss,arm",actual=str(exc),
            )) from exc
        if key in requested:
            if key in found or row["model"]!="e9g_shared_medium_backoff_proxy":
                raise ProtocolError(Diagnostic(
                    owner=OWNER,function="load_e9j_pinned_e9i_baseline",
                    category="contract",code="E9J_DUPLICATE_BASELINE_KEY",
                    expected="one original source row per matched scene",actual=key,
                ))
            found[key]=row
    if set(found)!=requested:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="load_e9j_pinned_e9i_baseline",
            category="contract",code="E9J_INCOMPLETE_BASELINE_PAIRING",
            expected=len(requested),actual=len(found),
            details=f"missing first={list(sorted(requested-set(found)))[:3]}",
        ))
    return found


def prepare_e9j_root(root:Path) -> None:
    """A prior formal or partial run cannot be accidentally overwritten."""
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="prepare_e9j_root",category="state",
            code="E9J_OUTPUT_EXISTS",expected="new or empty evidence root",
            actual=str(root),
        ))
    root.mkdir(parents=True,exist_ok=True)


def run_e9j_original_cbaa_case(*,scenario,profile,seed,n,
                               guard,phase_deadline_ms,oracle_cost)->dict:
    """Call existing paper CBAA state machine; charge actual original SENDs."""
    task_sampler=create_e9g_sampler(profile=profile,seed=seed,phy_rate_mbps=DESIGN_RATE)
    loss_sampler=BernoulliLossSampler(seed=seed)
    announced=broadcast_task_information(
        task_positions=scenario.task_positions,num_robots=n,
        sampler=task_sampler,loss_sampler=loss_sampler,p_loss=0.0,
        phase_timeout_ms=1.0e9,
    )
    costs=reconstruct_local_cost_rows(
        local_robot_positions=scenario.robot_positions,
        announced_tasks_by_robot=announced.per_robot_tasks,
    )
    require_local_source_consistency(reconstructed=costs,expected=scenario.cost_matrix)
    task_time=max((event.arrival_time_ms for event in announced.events),default=0.0)
    channel=create_e9g_sampler(profile=profile,seed=seed,phy_rate_mbps=DESIGN_RATE)
    cbaa=simulate_cbaa(
        cost_matrix=costs,sampler=channel,loss_sampler=loss_sampler,
        loss_probability=CBAA_BID_LOSS,phase_timeout_ms=phase_deadline_ms,
        max_iterations=guard,stop_mode="local_certification",
        capture_audit=False,
    )
    radio=channel.summarize_network()
    task_radio=task_sampler.summarize_network()
    expected_packet_count=len(announced.events)+cbaa.logical_message_count
    expected_bytes=announced.sender_bytes+cbaa.payload_bytes
    actual_packet_count=task_radio["packet_count"]+radio["packet_count"]
    actual_bytes=task_radio["application_sender_bytes"]+radio["application_sender_bytes"]
    expected_bid_packet_bytes=16+12*n
    correct=(
        (expected_packet_count,expected_bytes)==
        (actual_packet_count,actual_bytes)
        and cbaa.logical_message_count==n*cbaa.iterations
        and cbaa.payload_bytes==cbaa.logical_message_count*expected_bid_packet_bytes
        and cbaa.delivery_attempts==cbaa.logical_message_count*(n-1)
    )
    if not correct:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="run_e9j_original_cbaa_case",
            category="contract",code="E9J_CBAA_PHYSICAL_LEDGER_MISMATCH",
            expected={"packets":expected_packet_count,"bytes":expected_bytes,
                      "CBAA_vector_B":expected_bid_packet_bytes,
                      "broadcast_receivers_per_SEND":n-1},
            actual={"packets":actual_packet_count,"bytes":actual_bytes,
                    "CBAA_only_SENDs":cbaa.logical_message_count,
                    "CBAA_receiver_opportunities":cbaa.delivery_attempts},
            details=f"N={n} seed={seed}",
        ))
    certified=cbaa.stop_reason=="all_local_evidence_certified"
    full_observer=cbaa.full_observer_agreement
    completed=bool(certified and full_observer)
    cost=sum(costs[robot][task] for robot,task in cbaa.observer_agreed_pairs)
    task_total=task_time+cbaa.elapsed_ms
    if len(cbaa.observer_agreed_pairs)>n:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="run_e9j_original_cbaa_case",
            category="safety",code="E9J_CBAA_OVERSUBSCRIBED_TASKS",
            expected=f"<= {n}",actual=len(cbaa.observer_agreed_pairs),
        ))
    return {
        "seed":seed,"robots":n,"tasks":n,
        "method":"cbaa_original_local_bid_winner",
        "Bid_receiver_loss_probability":CBAA_BID_LOSS,
        "phy_mbps_ASSUMED":DESIGN_RATE,
        "cbaa_iteration_timeout_ms":phase_deadline_ms,
        "cbaa_iterations":cbaa.iterations,
        "cbaa_stop_reason":cbaa.stop_reason,
        "cbaa_locally_certified":int(certified),
        "cbaa_observer_full_agreement":int(full_observer),
        "cbaa_certified_and_observer_full":int(completed),
        "cbaa_observer_confirmed_tasks":len(cbaa.observer_agreed_pairs),
        "cbaa_local_claims":len(cbaa.local_claims),
        "cbaa_conflicting_tasks":len(cbaa.conflicting_task_ids),
        "cbaa_unconfirmed_tasks":len(cbaa.unconfirmed_task_ids),
        "cbaa_guard_hit":int(not certified),
        "task_sender_bytes":announced.sender_bytes,
        "cbaa_bid_sender_bytes":cbaa.payload_bytes,
        "total_original_sender_bytes":expected_bytes,
        "total_original_SENDs":expected_packet_count,
        "cbaa_receiver_delivery_attempts":cbaa.delivery_attempts,
        "cbaa_receiver_packet_drops":cbaa.delivery_drops,
        "cbaa_late_receiver_packets":cbaa.late_deliveries,
        "task_announcement_ms":task_time,
        "cbaa_coordination_or_stop_ms":cbaa.elapsed_ms,
        "allocation_or_stop_ms":task_total,
        "successful_local_certificate_ms":task_total if completed else "",
        "external_Hungarian_optimal_cost":oracle_cost,
        "cbaa_agreed_assignment_cost":cost if full_observer else "",
        "external_cost_over_Hungarian":cost/oracle_cost if full_observer else "",
        "modeled_radio_hops":task_radio["radio_hop_count"]+radio["radio_hop_count"],
        "modeled_airtime_ms":task_radio["total_airtime_ms"]+radio["total_airtime_ms"],
        "modeled_backoff_ms":task_radio["total_backoff_ms"]+radio["total_backoff_ms"],
        "modeled_queue_ms":task_radio["total_queue_ms"]+radio["total_queue_ms"],
        "success_semantics":"local_certification + posthoc observer; optimistic FREE shared STOP; NO paid Commit",
    }


def pair_e9j_against_e9i(*,rows,baseline)->list[dict]:
    """Read-only comparison: CBAA is never run again for two Vote-loss arms."""
    out=[]
    for row in rows:
        n,seed=int(row["robots"]),int(row["seed"])
        for vote_p in BASE_VOTE_LOSSES:
            for arm in BASE_ARM_NAMES:
                original=baseline[(n,seed,vote_p,arm)]
                voting_full=int(original["full_commit"])
                cbaa_ready=bool(row["cbaa_certified_and_observer_full"])
                both=bool(voting_full and cbaa_ready)
                vtime=float(original["successful_allocation_ms"]) if voting_full else None
                ctime=float(row["successful_local_certificate_ms"]) if cbaa_ready else None
                out.append({
                    "robots":n,"tasks":n,"seed":seed,"Cost_loss_Voting":.30,
                    "Bid_loss_CBAA":.30,"Vote_loss_Voting":vote_p,
                    "Voting_baseline_arm":arm,
                    "Voting_full_commit":voting_full,
                    "CBAA_all_locally_certified":row["cbaa_locally_certified"],
                    "CBAA_full_observer_agreement":row["cbaa_observer_full_agreement"],
                    "CBAA_native_stop_reason":row["cbaa_stop_reason"],
                    "CBAA_task_observer_confirmed":row["cbaa_observer_confirmed_tasks"],
                    "Voting_original_sender_bytes":int(original["total_sender_application_bytes"]),
                    "CBAA_original_sender_bytes":row["total_original_sender_bytes"],
                    "Voting_sender_SENDs":int(original["total_original_send_count"]),
                    "CBAA_sender_SENDs":row["total_original_SENDs"],
                    "Voting_radio_airtime_ms":float(original["total_airtime_ms"]),
                    "CBAA_radio_airtime_ms":row["modeled_airtime_ms"],
                    "Voting_success_time_ms":vtime if voting_full else "",
                    "CBAA_success_time_ms":ctime if cbaa_ready else "",
                    "Voting_all_seed_stop_ms":float(original["allocation_or_stop_ms"]),
                    "CBAA_all_seed_stop_ms":row["allocation_or_stop_ms"],
                    "matched_completed_time_CBAA_over_Voting":(
                        ctime/vtime if both and vtime>0 else ""
                    ),
                    "CBAA_over_Voting_sender_bytes":(
                        row["total_original_sender_bytes"]/
                        int(original["total_sender_application_bytes"])
                    ),
                    "Voting_cost_over_external_Hungarian":(
                        original["total_cost_over_hungarian_ratio"] if voting_full else ""
                    ),
                    "CBAA_cost_over_external_Hungarian":(
                        row["external_cost_over_Hungarian"]
                        if row["cbaa_observer_full_agreement"] else ""
                    ),
                    "not_equivalent_success_protocols":True,
                })
    return out


def summarize_e9j_comparison(rows:list[dict])->list[dict]:
    """Separately report all-seed stop time and conditional full-success time."""
    cells={}
    for r in rows:
        key=(r["robots"],r["Vote_loss_Voting"],r["Voting_baseline_arm"])
        cells.setdefault(key,[]).append(r)
    ans=[]
    for (n,vote_p,arm),group in sorted(cells.items()):
        full_v=[x for x in group if x["Voting_full_commit"]]
        full_c=[x for x in group if x["CBAA_all_locally_certified"] and x["CBAA_full_observer_agreement"]]
        paired=[x for x in group if x["matched_completed_time_CBAA_over_Voting"]!=""]
        ans.append({
            "N":n,"vote_loss_Voting":vote_p,"baseline_arm":arm,"seeds":len(group),
            "Voting_full_commit_count":len(full_v),
            "CBAA_certified_and_observer_full_count":len(full_c),
            "CBAA_full_observer_agreement_count":sum(int(x["CBAA_full_observer_agreement"]) for x in group),
            "CBAA_guard_or_unverified_count":len(group)-len(full_c),
            "Voting_mean_success_ms":statistics.mean(float(x["Voting_success_time_ms"]) for x in full_v) if full_v else "",
            "CBAA_mean_certified_ms":statistics.mean(float(x["CBAA_success_time_ms"]) for x in full_c) if full_c else "",
            "Voting_mean_all_seed_stop_ms":statistics.mean(float(x["Voting_all_seed_stop_ms"]) for x in group),
            "CBAA_mean_all_seed_stop_ms":statistics.mean(float(x["CBAA_all_seed_stop_ms"]) for x in group),
            "Voting_mean_sender_bytes":statistics.mean(int(x["Voting_original_sender_bytes"]) for x in group),
            "CBAA_mean_sender_bytes":statistics.mean(int(x["CBAA_original_sender_bytes"]) for x in group),
            "Voting_mean_SENDs":statistics.mean(int(x["Voting_sender_SENDs"]) for x in group),
            "CBAA_mean_SENDs":statistics.mean(int(x["CBAA_sender_SENDs"]) for x in group),
            "mean_CBAA_over_Voting_sender_bytes":statistics.mean(float(x["CBAA_over_Voting_sender_bytes"]) for x in group),
            "both_success_count":len(paired),
            "mean_paired_completed_time_ratio_if_both":statistics.mean(float(x["matched_completed_time_CBAA_over_Voting"]) for x in paired) if paired else "",
            "CBAA_source_halt_is_optimistic_unpaid":True,
        })
    return ans


def write_e9j_evidence(*,root,raw,paired,summary,sha,profile,
                       sizes,seeds,first_seed,guard,baseline_zip)->None:
    """Do not publish a formal reference until original hashed CSV is attested."""
    hashes={}
    files=[("per_seed_original_cbaa.csv",raw)]
    if baseline_zip is not None:
        files += [("paired_e9j_original.csv",paired),("summary_e9j.csv",summary)]
    for filename,rows in files:
        if not rows:
            raise ProtocolError(Diagnostic(
                owner=OWNER,function="write_e9j_evidence",
                category="contract",code="E9J_EMPTY_EVIDENCE",
                expected="nonempty original records",actual=filename,
            ))
        path=root/filename
        with path.open("w",encoding="utf-8",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]))
            writer.writeheader();writer.writerows(rows)
        hashes[filename]=hashlib.sha256(path.read_bytes()).hexdigest()
    manifest={
        "study":"E9J original CBAA vs immutable E9I original Voting",
        "evidence_type":"SIMULATED shared 144Mbps, not measured Wi-Fi 6E or ns3",
        "result_status":"PAIRED" if baseline_zip else "UNPAIRED_SMOKE_ONLY",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "source_git_sha":sha,"baseline_original_zip_sha256":BASE_ZIP_SHA if baseline_zip else "",
        "baseline_original_code_git_sha":BASE_GIT_SHA if baseline_zip else "",
        "base_Rady_commit":RADY_SOURCE_COMMIT,"base_Rady_blob":RADY_SOURCE_BLOB_SHA,
        "N_equals_T_sizes":list(sizes),"seed_start":first_seed,
        "seeds_per_cell":seeds,"cbaa_native_guard":guard,
        "cbaa_consensus_packet_sender_B":"16+12*N full Bid/Winner vector",
        "CBAA_bid_receiver_Bernoulli_p":.30,
        "Voting_Cost_receiver_Bernoulli_p":.30,
        "Voting_Vote_receiver_Bernoulli_p":[0,.30],
        "TASK_announcements_original_reliable":True,
        "CBAA_stop_mode":"local_certification (optimistic all local flags; no distributed stop packets)",
        "CBAA_reliable_final_commit":False,
        "Voting_reliable_final_commit":True,
        "CBAA_agreement_not_equivalent_to_Voting_commit":True,
        "original_CBAA_local_auction_consensus_only":True,
        "shared_network_PHY_rate_mbps_HYPOTHESIS":DESIGN_RATE,
        "cbaa_original_cases":len(raw),
        "paired_comparison_cases":len(paired),
        "sha256_source_files":hashes,
    }
    (root/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")


def run_e9j_cbaa_vs_e9i(*,sizes,seeds,first_seed,guard,dataset,output_root,
                       baseline_zip=None,allow_unpaired_smoke=False,
                       allow_download=True)->list[dict]:
    """Execute native CBAA once per size/seed; read original E9I source only."""
    validate_e9j_axes(sizes=sizes,seeds=seeds,first_seed=first_seed,
                      guard=guard,baseline_zip=baseline_zip,
                      allow_unpaired_smoke=allow_unpaired_smoke)
    baseline=(load_e9j_pinned_e9i_baseline(
        archive=baseline_zip,sizes=sizes,seeds=seeds,first_seed=first_seed
    ) if baseline_zip is not None else None)
    profile=load_rady_latency_profile(ensure_rady_dataset(dataset,allow_download=allow_download))
    sha=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    if len(sha)!=40 or any(c not in "0123456789abcdef" for c in sha):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="run_e9j_cbaa_vs_e9i",
            category="dependency",code="E9J_INVALID_EXECUTABLE_SHA",
            expected="git HEAD 40 lowercase hex",actual=sha,
        ))
    prepare_e9j_root(output_root)
    raw=[]
    partial=output_root/"per_seed_original_cbaa.partial.csv"
    with partial.open("w",newline="",encoding="utf-8") as f:
        writer=None
        for n in sizes:
            window=estimate_e9j_cbaa_consensus_window_ms(
                profile=profile,robots=n,tasks=n,reference_phy_mbps=DESIGN_RATE,
            )
            for seed in range(first_seed,first_seed+seeds):
                scenario=generate_e0_scenario(seed,n,n)
                oracle=solve_hungarian_assignment(scenario.cost_matrix).total_cost
                row=run_e9j_original_cbaa_case(
                    scenario=scenario,profile=profile,seed=seed,n=n,
                    guard=guard,phase_deadline_ms=window,oracle_cost=oracle,
                )
                raw.append(row)
                if writer is None:
                    writer=csv.DictWriter(f,fieldnames=list(row))
                    writer.writeheader()
                writer.writerow(row)
            f.flush()
            success=sum(int(x["cbaa_certified_and_observer_full"])
                        for x in raw if x["robots"]==n)
            print(f"E9J_DONE N={n} CBAA_certified={success}/{seeds} raw={len(raw)}",flush=True)
    expected=len(sizes)*seeds
    if len(raw)!=expected:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="run_e9j_cbaa_vs_e9i",
            category="contract",code="E9J_INCOMPLETE_CBAA_GRID",
            expected=expected,actual=len(raw),
        ))
    paired=pair_e9j_against_e9i(rows=raw,baseline=baseline) if baseline is not None else []
    summary=summarize_e9j_comparison(paired) if paired else []
    write_e9j_evidence(root=output_root,raw=raw,paired=paired,summary=summary,
                       sha=sha,profile=profile,sizes=sizes,seeds=seeds,
                       first_seed=first_seed,guard=guard,baseline_zip=baseline_zip)
    partial.unlink()
    print(f"E9J_COMPLETE CBAA_original_cases={len(raw)} paired={len(paired)} root={output_root}",flush=True)
    return raw


def main()->None:
    p=argparse.ArgumentParser(
        description="E9J original CBAA native consensus vs SHA-pinned E9I Voting Cost30 baseline"
    )
    p.add_argument("--sizes",type=parse_e9g_sizes,
                   default=tuple(range(5,101,5)))
    p.add_argument("--seeds",type=int,default=100)
    p.add_argument("--first-seed",type=int,default=0)
    p.add_argument("--cbaa-safety-rounds",type=int,default=MAX_NATURAL_ITERATIONS)
    p.add_argument("--baseline-zip",type=Path)
    p.add_argument("--allow-unpaired-smoke",action="store_true")
    p.add_argument("--dataset",type=Path,default=Path("data/external/rady/perama_range_testing.json"))
    p.add_argument("--no-download",action="store_true")
    p.add_argument("--output-root",type=Path,default=Path("results/e9j_cbaa_vs_voting"))
    a=p.parse_args()
    run_e9j_cbaa_vs_e9i(
        sizes=a.sizes,seeds=a.seeds,first_seed=a.first_seed,
        guard=a.cbaa_safety_rounds,dataset=a.dataset,output_root=a.output_root,
        baseline_zip=a.baseline_zip,allow_unpaired_smoke=a.allow_unpaired_smoke,
        allow_download=not a.no_download,
    )


if __name__=="__main__":
    main()
