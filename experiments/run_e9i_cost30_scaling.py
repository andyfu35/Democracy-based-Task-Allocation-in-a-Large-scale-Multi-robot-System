"""E9I: original Voting R=T=N scaling with Cost loss frozen at 30%.

Primary: Cost receiver-level Bernoulli 0.30, Vote Bernoulli 0.00.
Companion: same COST realization, Vote Bernoulli 0.30.
Candidate choice: RECEIVED PLURALITY; matching fixed-quarter is diagnostic control.
Uses unchanged original coordination/Cost/Score/Commit owners via E9H experiment case.
E9G 144Mbps network is a model sensitivity, NOT measured 100-station 802.11ax.
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
    RADY_SOURCE_COMMIT,RADY_SOURCE_BLOB_SHA,
    ensure_rady_dataset,load_rady_latency_profile,percentile,
    estimate_e9h_guarded_initial_cost_ms,
)
from democracy_mrta.optimizer import solve_hungarian_assignment
from democracy_mrta.scenario import generate_e0_scenario
from experiments.run_e9g_wifi_scaling import parse_e9g_sizes,e9g_loglog_exponent
from experiments.run_e9h_adaptive_deadline import (
    DEFAULT_OLD_FIXED_MS,build_e9h_deadline_schedule,iter_e9h_arms,
    parse_e9h_floats,run_e9h_original_voting_case,
    pair_e9h_against_fixed,validate_e9h_experiment,
)

OWNER="experiments.run_e9i_cost30_scaling"
COST_LOSS=0.30
VOTE_GRID=(0.0,0.30)
MAIN_ARMS=(
    "fixed_quarter",
    "fixed_received",
    "adaptive_k1_received",
    "adaptive_guarded_k1_received",
)
DEFAULT_SIZES=tuple(range(5,101,5))


def validate_e9i_cost30_axes(*,sizes,seeds,first_seed,max_rounds,
                            rate_mbps,design_rate_mbps,vote_losses) -> None:
    """Data boundary: strictly frozen cost30 but independently varied Vote."""
    validate_e9h_experiment(
        sizes=sizes,rates=(rate_mbps,),losses=(COST_LOSS,),
        margins=(1.0,),seeds=seeds,first_seed=first_seed,
        max_rounds=max_rounds,design_rate_mbps=design_rate_mbps,
    )
    grid=parse_e9h_floats(",".join(str(v) for v in vote_losses),is_loss=True)
    if grid!=VOTE_GRID:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="validate_e9i_cost30_axes",category="data",
            code="E9I_VOTE_LOSS_PAIR_NOT_FROZEN",
            expected=VOTE_GRID,actual=grid,
            details="To isolate Cost loss, always pair Vote=0 and Vote=.30.",
        ))


def prepare_e9i_output(root:Path) -> None:
    """Never silently overwrite formal evidence or the previous E9H study."""
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="prepare_e9i_output",category="state",
            code="E9I_OUTPUT_EXISTS",expected="new or empty output directory",
            actual=str(root),
        ))
    root.mkdir(parents=True,exist_ok=True)


def selected_e9i_arms() -> tuple[tuple[str,str,float|None,bool],...]:
    """Predeclare four true original Voting controls before seeing any seed."""
    options={arm[0]:arm for arm in iter_e9h_arms((1.0,))}
    if set(MAIN_ARMS)-options.keys():
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="selected_e9i_arms",category="contract",
            code="E9I_ARM_CONTRACT_MISSING",
            expected=MAIN_ARMS,actual=tuple(options),
        ))
    return tuple(options[name] for name in MAIN_ARMS)


def summarize_e9i_scaling(rows:list[dict[str,object]]) -> list[dict[str,object]]:
    """No false successful-time mean from failures or guard-censored runs."""
    groups:dict[tuple[int,str,str,float,str],list[dict[str,object]]]={}
    for row in rows:
        key=(int(row["robots"]),str(row["model"]),
             str(row["modeled_phy_rate_mbps"]),
             float(row["vote_loss_probability"]),str(row["arm"]))
        groups.setdefault(key,[]).append(row)
    out=[]
    for (n,model,rate,p_vote,arm),part in sorted(groups.items()):
        full=[r for r in part if int(r["full_commit"])]
        success_times=[float(r["successful_allocation_ms"]) for r in full]
        stop_times=[float(r["allocation_or_stop_ms"]) for r in part]
        oracle_ratios=[
            float(r["total_cost_over_hungarian_ratio"])
            for r in full if r["total_cost_over_hungarian_ratio"]!=""
        ]
        both_full=[
            r for r in part
            if int(r["full_commit"]) and int(r["matched_fixed_quarter_full"])
        ]
        supports=[float(r["mean_winner_support_share"]) for r in part
                  if r["mean_winner_support_share"]!=""]
        out.append({
            "robots":n,"tasks":n,"cost_loss_probability":COST_LOSS,
            "vote_loss_probability":p_vote,"model":model,
            "modeled_phy_rate_mbps":rate,"arm":arm,
            "seeds":len(part),"full_commit_count":len(full),
            "full_commit_rate":len(full)/len(part),
            "mean_tasks_committed":statistics.mean(
                int(r["tasks_committed"]) for r in part
            ),
            "mean_successful_time_ms":(
                statistics.mean(success_times) if success_times else ""
            ),
            "p95_successful_time_ms":(
                percentile(success_times,.95) if success_times else ""
            ),
            "mean_all_seed_stop_ms":statistics.mean(stop_times),
            "p95_all_seed_stop_ms":percentile(stop_times,.95),
            "mean_sender_bytes":statistics.mean(
                int(r["total_sender_application_bytes"]) for r in part
            ),
            "mean_sender_sends":statistics.mean(
                int(r["total_original_send_count"]) for r in part
            ),
            "mean_cost_peer_reach_fraction":statistics.mean(
                float(r["cost_effective_peer_view_fraction"]) for r in part
            ),
            "mean_cost_receiver_drop_count":statistics.mean(
                int(r["cost_remote_packet_drop_count"]) for r in part
            ),
            "mean_vote_remote_drop_count":statistics.mean(
                int(r["vote_remote_packet_drop_count"]) for r in part
            ),
            "mean_late_cost_receiver_count":statistics.mean(
                int(r["late_cost_delivery_count"]) for r in part
            ),
            "mean_late_vote_receiver_count":statistics.mean(
                int(r["late_remote_vote_delivery_count"]) for r in part
            ),
            "mean_score_announcement_count":statistics.mean(
                int(r["vote_score_send_count"]) for r in part
            ),
            "mean_winner_support_fraction":(
                statistics.mean(supports) if supports else ""
            ),
            "mean_hungarian_cost_ratio_on_full":(
                statistics.mean(oracle_ratios) if oracle_ratios else ""
            ),
            "matched_full_pair_count":len(both_full),
            "mean_paired_successful_time_delta_ms":(
                statistics.mean(float(r["paired_time_delta_ms"]) for r in both_full)
                if both_full else ""
            ),
            "mean_paired_cost_delta_vs_fixed":(
                statistics.mean(float(r["cost_delta_vs_fixed"]) for r in both_full)
                if both_full else ""
            ),
            "mean_rounds_executed":statistics.mean(
                int(r["rounds_executed"]) for r in part
            ),
            "total_safety_guard_hits":sum(int(r["guard_hit"]) for r in part),
        })
    return out


def summarize_e9i_empirical_exponents(summary:list[dict[str,object]]) -> list[dict[str,object]]:
    """Only fully completed cells support a completed-time scaling fit."""
    grouped={}
    for r in summary:
        key=(r["model"],str(r["modeled_phy_rate_mbps"]),
             r["vote_loss_probability"],r["arm"])
        grouped.setdefault(key,[]).append(r)
    out=[]
    for (model,rate,vote,arm),cases in sorted(grouped.items()):
        cases.sort(key=lambda r:r["robots"])
        all_full=all(r["full_commit_count"]==r["seeds"] for r in cases)
        # When any failures exist, report STOP scaling, never successful time.
        field="mean_successful_time_ms" if all_full else "mean_all_seed_stop_ms"
        beta,r2=e9g_loglog_exponent([
            (int(r["robots"]),float(r[field])) for r in cases
        ])
        out.append({
            "model":model,"modeled_phy_rate_mbps":rate,
            "cost_loss_probability":COST_LOSS,
            "vote_loss_probability":vote,"arm":arm,"sizes":len(cases),
            "all_cells_fully_committed":int(all_full),
            "fitted_time_kind":(
                "completed_assignment_time" if all_full else
                "all_seed_stop_time_CENSORED_NOT_SUCCESS"),
            "finite_range_beta_not_big_o":beta,"loglog_r_squared":r2,
        })
    return out


def write_e9i_provenance(*,root,rows,summary,exponents,source_sha,
                        profile,sizes,seeds,first_seed,rate_mbps,include_rady,
                        design_rate_mbps,max_rounds) -> None:
    """Write append-only original raw and checksum evidence, not fake 802.11ax."""
    outputs=[
        ("per_seed_e9i_cost30.csv",rows),
        ("scaling_e9i_cost30.csv",summary),
        ("exponents_e9i_cost30.csv",exponents),
    ]
    hashes={}
    for name,data in outputs:
        if not data:
            raise ProtocolError(Diagnostic(
                owner=OWNER,function="write_e9i_provenance",
                category="contract",code="E9I_EMPTY_OUTPUT",expected="nonempty",
                actual=name,
            ))
        path=root/name
        with path.open("w",encoding="utf-8",newline="") as handle:
            writer=csv.DictWriter(handle,fieldnames=list(data[0]))
            writer.writeheader();writer.writerows(data)
        hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    doc={
        "experiment":"E9I_fixed_cost_loss30_R_equals_T_scaling",
        "evidence_status":"EXECUTED_ORIGINAL_VOTING_PYTHON_MODEL_NOT_NS3",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "source_git_sha":source_sha,
        "models":(
            ["rady_bootstrap_no_shared_channel"] if include_rady else []
        )+["e9g_shared_medium_backoff_proxy"],
        "phy_rate_mbps_assumed_not_measured":rate_mbps,
        "deadline_reference_mbps_assumed":design_rate_mbps,
        "cost_loss_probability_fixed":COST_LOSS,
        "vote_loss_probabilities_paired":list(VOTE_GRID),
        "rady_source_commit":RADY_SOURCE_COMMIT,
        "rady_source_blob_sha":RADY_SOURCE_BLOB_SHA,
        "rady_samples":len(profile.samples_ms),
        "size_grid_robots_equal_tasks":list(sizes),
        "seeds_per_cell":seeds,"first_seed":first_seed,
        "original_voting_arms":list(MAIN_ARMS),
        "guard_max_rounds":max_rounds,
        "initial_TASK_and_SCORE_COMMIT_reliability":"assumed_reliable",
        "loss_unit":"original receiver delivery observation for Cost; one Vote unicast; independent seeded Bernoulli",
        "source_sender_bytes_versus_radio_hops":"application SENDs counted once per physical Cost broadcast",
        "failure_time":"all_seed_stop_ms_is_censored_not_successful_allocation",
        "source_files_sha256":hashes,"raw_cases":len(rows),
        "grouped_cases":len(summary),
        "full_phy_mac_80211ax_ofdma":False,
        "publication_status":"pilot_must_be_independently_verified_before_README_formal_claims",
    }
    (root/"manifest.json").write_text(
        json.dumps(doc,indent=2,ensure_ascii=False)+"\n",encoding="utf-8",
    )


def run_e9i_cost30_scaling(*,sizes=DEFAULT_SIZES,seeds=100,first_seed=0,
                          max_rounds=300,dataset=Path("data/external/rady/perama_range_testing.json"),
                          output_root=Path("results/e9i_cost30_scaling"),
                          rate_mbps=144.0,design_rate_mbps=144.0,
                          include_rady=False,allow_download=True):
    """Perform actual original protocol runs; compare Cost fixed 30% vs Vote effects."""
    validate_e9i_cost30_axes(
        sizes=sizes,seeds=seeds,first_seed=first_seed,max_rounds=max_rounds,
        rate_mbps=rate_mbps,design_rate_mbps=design_rate_mbps,
        vote_losses=VOTE_GRID,
    )
    prepare_e9i_output(output_root)
    profile=load_rady_latency_profile(
        ensure_rady_dataset(dataset,allow_download=allow_download)
    )
    sha=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    if len(sha)!=40 or not all(c in "0123456789abcdef" for c in sha):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="run_e9i_cost30_scaling",
            category="dependency",code="E9I_GIT_SOURCE_SHA_INVALID",
            expected="40 hex Git HEAD",actual=sha,
        ))
    rates=((None,rate_mbps) if include_rady else (rate_mbps,))
    arms=selected_e9i_arms()
    out=[]
    partial=output_root/"per_seed_e9i_cost30.partial.csv"
    with partial.open("w",newline="",encoding="utf-8") as h:
        writer=None
        for n in sizes:
            schedules={1.0:build_e9h_deadline_schedule(
                profile=profile,robots=n,design_rate_mbps=design_rate_mbps,
                margin_factor=1.0,
            )}
            guarded_cost=estimate_e9h_guarded_initial_cost_ms(
                profile=profile,total_robots=n,total_tasks=n,
                reference_phy_mbps=design_rate_mbps,
            )
            for seed in range(first_seed,first_seed+seeds):
                scenario=generate_e0_scenario(seed,n,n)
                oracle=solve_hungarian_assignment(scenario.cost_matrix).total_cost
                for vote_loss in VOTE_GRID:
                    for rate in rates:
                        paired=[]
                        for arm in arms:
                            row=run_e9h_original_voting_case(
                                scenario=scenario,profile=profile,n=n,
                                seed=seed,p_loss=COST_LOSS,p_vote_loss=vote_loss,
                                rate=rate,max_rounds=max_rounds,
                                fixed_timeout_ms=DEFAULT_OLD_FIXED_MS,
                                arm=arm,schedules=schedules,
                                oracle_total_cost=oracle,
                                guarded_cost_ms=guarded_cost,
                            )
                            paired.append(row)
                        pair_e9h_against_fixed(paired)
                        for row in paired:
                            out.append(row)
                            if writer is None:
                                writer=csv.DictWriter(h,fieldnames=list(row))
                                writer.writeheader()
                            writer.writerow(row)
                        h.flush()
            print(f"E9I_DONE N={n} seeds={seeds} original_runs={len(out)}",
                  flush=True)
    expected=len(sizes)*seeds*len(VOTE_GRID)*len(rates)*len(arms)
    if len(out)!=expected:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="run_e9i_cost30_scaling",
            category="contract",code="E9I_GRID_INCOMPLETE",
            expected=expected,actual=len(out),
        ))
    summary=summarize_e9i_scaling(out)
    exponents=summarize_e9i_empirical_exponents(summary)
    write_e9i_provenance(
        root=output_root,rows=out,summary=summary,exponents=exponents,
        source_sha=sha,profile=profile,sizes=sizes,seeds=seeds,
        first_seed=first_seed,rate_mbps=rate_mbps,
        include_rady=include_rady,design_rate_mbps=design_rate_mbps,
        max_rounds=max_rounds,
    )
    partial.unlink()
    print(f"E9I_COMPLETE original_runs={len(out)} root={output_root} source={sha}",
          flush=True)
    return out


def main()->None:
    p=argparse.ArgumentParser(
        description="Original Voting Cost loss fixed 30%; Vote 0% and 30%; R=T scaling"
    )
    p.add_argument("--sizes",type=parse_e9g_sizes,default=DEFAULT_SIZES)
    p.add_argument("--seeds",type=int,default=100)
    p.add_argument("--first-seed",type=int,default=0)
    p.add_argument("--max-rounds",type=int,default=300)
    p.add_argument("--rate-mbps",type=float,default=144.0)
    p.add_argument("--design-rate-mbps",type=float,default=144.0)
    p.add_argument("--include-rady",action="store_true")
    p.add_argument("--dataset",type=Path,
                   default=Path("data/external/rady/perama_range_testing.json"))
    p.add_argument("--no-download",action="store_true")
    p.add_argument("--output-root",type=Path,
                   default=Path("results/e9i_cost30_scaling"))
    args=p.parse_args()
    run_e9i_cost30_scaling(
        sizes=args.sizes,seeds=args.seeds,first_seed=args.first_seed,
        max_rounds=args.max_rounds,dataset=args.dataset,
        output_root=args.output_root,rate_mbps=args.rate_mbps,
        design_rate_mbps=args.design_rate_mbps,
        include_rady=args.include_rady,
        allow_download=not args.no_download,
    )


if __name__=="__main__":
    main()
