"""P2J-v3 paired one-shot Greedy, positive-Score global v2 and zero-vote completion v3.

Original native Global Greedy single-batch is the paired control. A new
probabilistic_batch voter draws exactly 100 tickets locally (one uniform
task choice, then temperature-weighted visible Cost choice per ticket).
Vote DATA broadcasts once per voter, Score self-cost is paid/reliable,
winner resolution is one Score-global maximum-cardinality matching,
then signed vote-gap/support/candidate-own-Cost preferences.
This experiment does NOT retrain an MDP or assume a learned Markov policy.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import sys

from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import (
    ensure_rady_dataset, load_rady_latency_profile,
    estimate_e9h_guarded_initial_cost_ms,
)
from democracy_mrta.optimizer import (
    solve_visible_batched_greedy_assignment, solve_hungarian_assignment,
)
from democracy_mrta.scenario import generate_e0_scenario
from experiments.run_e9h_adaptive_deadline import (
    DEFAULT_OLD_FIXED_MS, build_e9h_deadline_schedule,
    run_e9h_original_voting_case,
)
from experiments.run_e9i_cost30_scaling import selected_e9i_arms
from experiments.run_p1_matched_five import (
    DEFAULT_RADY, read_source_sha, scene_sha256, verify_one_scene,
    write_csv, sha256_file,
)

OWNER = "experiments.run_p2j_probabilistic_batch"
MODES = ("one_batch_greedy", "probabilistic_global_margin",
         "probabilistic_complete_fallback")
FORMAL_LOSSES = tuple(range(0,91,10))
RAW_FIELDS = (
    "source_sha","seed","loss_percent","mode","scene_sha256",
    "robots","tasks","capacity","votes_per_voter","temperature","margin_rule",
    "native_complete","committed_tasks","coverage_percent",
    "committed_cost_m","cost_per_committed_task_m",
    "full_info_global_greedy_cost","native_complete_cost",
    "cost_increase_percent","native_stop_ms","sender_sends","sender_bytes",
    "task_sends","task_bytes","cost_sends","cost_bytes",
    "vote_sends","vote_bytes","score_sends","score_bytes",
    "commit_sends","commit_bytes","vote_tickets_attempted",
    "certified_score_edge_count","certified_score_supported_tasks",
    "certified_score_max_matching",
    "completion_fallback_count","completion_fallback_cost_m",
    "completion_fallback_pairs_json","vote_supported_cost_m",
    "cost_receiver_drops","vote_receiver_drops","rounds_executed",
    "assignment_digest","native_assignment_json","first_epoch_digest","native_diagnostic",
)
SUMMARY_FIELDS = (
    "loss_percent","mode","seeds","full_completion_percent",
    "mean_task_coverage_percent","mean_cost_per_committed_task_m",
    "cost_success_n","cost_increase_percent",
    "mean_stop_s","mean_sender_kB","mean_cost_sender_kB",
    "mean_vote_sender_kB","mean_score_sender_kB",
    "mean_certified_score_edges","mean_certified_score_supported_tasks",
    "mean_certified_score_max_matching",
    "mean_completion_fallback_count","fallback_seed_percent",
    "mean_completion_fallback_cost_m","mean_vote_supported_cost_m",
    "mean_vote_receiver_drops",
)


def fail(function: str, category: str, code: str, *, expected=None,
         actual=None, details: str = "") -> None:
    raise ProtocolError(Diagnostic(
        owner=OWNER,function=function,category=category,code=code,
        expected=expected,actual=actual,details=details,
    ))


def validate_p2j_config(args: argparse.Namespace) -> tuple[int, ...]:
    """Freeze formal axes before any original physical SEND is generated."""
    try:
        raw=tuple(float(x.strip()) for x in args.losses.split(","))
    except (TypeError,ValueError,AttributeError) as exc:
        fail("validate_p2j_config","data","P2J_BAD_LOSS_GRID",
             expected="comma-separated 0.00,0.10,...,0.90",actual=str(exc))
    levels=tuple(int(round(v*100)) for v in raw if math.isfinite(v))
    if (len(levels)!=len(raw) or not levels or
            levels!=tuple(sorted(set(levels))) or
            any(p not in FORMAL_LOSSES or abs(v-p/100)>1e-12
                for v,p in zip(raw,levels))):
        fail("validate_p2j_config","data","P2J_BAD_LOSS_GRID",
             expected=FORMAL_LOSSES,actual=raw)
    if (type(args.seeds) is not int or not 1<=args.seeds<=100
            or type(args.first_seed) is not int or args.first_seed<0
            or args.first_seed+args.seeds>100 or
            type(args.votes_per_voter) is not int
            or not 1<=args.votes_per_voter<=255 or
            type(args.temperature) not in (int,float)
            or not math.isfinite(args.temperature) or args.temperature<=0
            or args.margin_rule not in ("absolute","normalized")):
        fail("validate_p2j_config","data","P2J_INVALID_EXPERIMENT_AXIS",
             expected="seeds subset 0..99, votes_per_voter 1..255, "
                      "temperature finite >0, absolute/normalized margin",
             actual=vars(args))
    if args.formal and (
        levels!=FORMAL_LOSSES or args.seeds!=100 or args.first_seed!=0
        or args.votes_per_voter!=100 or args.temperature!=5.0
        or args.margin_rule!="absolute"
    ):
        fail("validate_p2j_config","contract","P2J_FORMAL_AXIS_CHANGED",
             expected={"loss":FORMAL_LOSSES,"seeds":100,"first_seed":0,
                       "votes_per_voter":100,"temperature":5.0,"margin_rule":"absolute"},
             actual=vars(args))
    return levels


def audit_p2j_native_sender(
    *, native: dict, mode: str, robots: int, votes_per_voter: int,
) -> dict[str, int]:
    """One physical Cost + one Vote Batch per voter, every SEND paid."""
    phases=native["sender_by_phase"]
    if not isinstance(phases,dict):
        fail("audit_p2j_native_sender","dependency","P2J_NATIVE_SENDER_LEDGER_MISSING",
             expected="E9H physical per-phase sender ledger",actual=phases)
    result={}
    for name in ("task","cost","vote","score","commit"):
        if name not in phases:
            fail("audit_p2j_native_sender","contract","P2J_PHASE_MISSING",
                 expected=name,actual=tuple(phases))
        result[f"{name}_sends"]=int(phases[name]["sender_sends"])
        result[f"{name}_bytes"]=int(phases[name]["sender_bytes"])
    counts=(sum(result[f"{name}_sends"] for name in ("task","cost","vote","score","commit")),
            sum(result[f"{name}_bytes"] for name in ("task","cost","vote","score","commit")))
    actual=(int(native["total_original_send_count"]),
            int(native["total_sender_application_bytes"]))
    if counts!=actual:
        fail("audit_p2j_native_sender","contract","P2J_SENDER_TOTAL_MISMATCH",
             expected=actual,actual=counts)
    if (result["cost_sends"]!=robots or result["vote_sends"]!=robots
            or result["task_sends"]!=int(native["task_announcement_sender_frames"])
            or int(native["rounds_executed"])!=1
            or result["commit_sends"]!=int(native["tasks_committed"])):
        fail("audit_p2j_native_sender","contract","P2J_ONE_BATCH_SEND_CONTRACT",
             expected={"Cost":robots,"Vote":robots,"rounds":1,
                       "Commit":"exactly committed tasks"},
             actual={**result,"rounds":native["rounds_executed"]})
    # A ticket is a local logical draw, not a separate physical packet.
    result["vote_tickets_attempted"]=(
        robots*votes_per_voter if mode!="one_batch_greedy" else 0
    )
    if mode!="one_batch_greedy" and result["vote_bytes"]>robots*1200:
        fail("audit_p2j_native_sender","contract","P2J_PROBABILITY_PACKET_NOT_BATCHED",
             expected=f"at most {robots} x 1200B Vote",actual=result["vote_bytes"])
    return result


def execute_p2j_native(
    *, scene, profile, p_loss: float, mode: str,
    votes_per_voter: int, temperature: float, margin_rule: str,
) -> dict:
    """Invoke original E9H physical epoch; no experiment-owned allocation."""
    if mode not in MODES:
        fail("execute_p2j_native","data","P2J_UNKNOWN_MODE",
             expected=MODES,actual=mode)
    n=scene.num_robots
    strategy=("probabilistic_batch" if mode!="one_batch_greedy" else "greedy_batch")
    arm=next(a for a in selected_e9i_arms() if a[0]=="adaptive_guarded_k1_received")
    schedule=build_e9h_deadline_schedule(
        profile=profile,robots=n,design_rate_mbps=144.0,
        margin_factor=1.0,voting_strategy=strategy,batch_vote_scope="all",
    )
    guard=estimate_e9h_guarded_initial_cost_ms(
        profile=profile,total_robots=n,total_tasks=n,reference_phy_mbps=144.0,
    )
    return run_e9h_original_voting_case(
        scenario=scene,profile=profile,n=n,seed=scene.seed,p_loss=p_loss,
        p_vote_loss=p_loss,rate=144.0,max_rounds=1,
        fixed_timeout_ms=DEFAULT_OLD_FIXED_MS,arm=arm,
        schedules={1.0:schedule},guarded_cost_ms=guard,
        oracle_total_cost=solve_hungarian_assignment(scene.cost_matrix).total_cost,
        voting_strategy=strategy,batch_vote_scope="all",
        capture_assignment_pairs=True,
        votes_per_voter=votes_per_voter,temperature=temperature,
        margin_rule=margin_rule,
        completion_policy=(
            "idle_robot_id" if mode=="probabilistic_complete_fallback" else "none"
        ),
    )


def measure_p2j_complete_quality(*, scene, native: dict) -> tuple[float,object,object]:
    """Independent offline Global Greedy reference; no native hidden Cost repair."""
    full=solve_visible_batched_greedy_assignment(
        scene.cost_matrix,frozenset(range(scene.num_robots)),
    )
    complete=bool(native["full_commit"]) and int(native["tasks_committed"])==scene.num_tasks
    if not complete:
        return float(full.total_cost),"",""
    cost=float(native["total_assignment_cost"])
    return float(full.total_cost),cost,100*(cost/full.total_cost-1)


def run_one_p2j_case(
    *, scene, profile, p_loss: float, mode: str, source_sha: str,
    votes_per_voter: int, temperature: float, margin_rule: str,
) -> dict:
    """Original execution -> native SEND audit -> offline reference -> immutable case."""
    verify_one_scene(scene)
    native=execute_p2j_native(
        scene=scene,profile=profile,p_loss=p_loss,mode=mode,
        votes_per_voter=votes_per_voter,temperature=temperature,
        margin_rule=margin_rule,
    )
    paid=audit_p2j_native_sender(
        native=native,mode=mode,robots=scene.num_robots,
        votes_per_voter=votes_per_voter,
    )
    pairs=tuple((int(r),int(t)) for r,t in native["native_assignment_pairs"])
    if (len(pairs)!=int(native["tasks_committed"])
            or len({r for r,t in pairs})!=len(pairs)
            or len({t for r,t in pairs})!=len(pairs)
            or any(r<0 or r>=scene.num_robots or t<0 or t>=scene.num_tasks
                   for r,t in pairs)):
        fail("run_one_p2j_case","safety","P2J_ORIGINAL_PAIR_DUPLICATE_OR_INVALID",
             expected="only unique in-range native committed robot/task pairs",
             actual=pairs[:12])
    independently_recomputed_cost=sum(scene.cost_matrix[r][t] for r,t in pairs)
    if abs(independently_recomputed_cost-float(native["total_assignment_cost"]))>1e-8:
        fail("run_one_p2j_case","contract","P2J_NATIVE_PAIR_COST_MISMATCH",
             expected=independently_recomputed_cost,
             actual=native["total_assignment_cost"])
    # AFTER native Commit, measure realized fallback Cost offline from
    # original E0 truth. It is NEVER supplied to the assignment planner.
    fallback=tuple((int(r),int(t)) for r,t in native["completion_fallback_pairs"])
    if (len(fallback)!=int(native["completion_fallback_count"])
            or len(set(fallback))!=len(fallback)
            or not set(fallback).issubset(set(pairs))):
        fail("run_one_p2j_case","contract","P2J_V3_FALLBACK_NATIVE_TRACE_MISMATCH",
             expected="fallback count == unique subset of real committed pairs",
             actual={"pairs":fallback,"count":native["completion_fallback_count"]})
    if mode!="probabilistic_complete_fallback" and fallback:
        fail("run_one_p2j_case","contract","P2J_V3_FALLBACK_LEAKED_TO_CONTROL",
             expected="no fallback in original Greedy and P2J-v2",actual=fallback)
    if mode!="one_batch_greedy":
        counted_edges=int(native["certified_score_edge_count"])
        covered_tasks=int(native["certified_score_supported_tasks"])
        bound=int(native["certified_score_max_matching"])
        actual_count=int(native["tasks_committed"])
        expected_count=(bound+len(fallback)
                        if mode=="probabilistic_complete_fallback" else bound)
        if (actual_count!=expected_count
                or not 0<=bound<=covered_tasks<=scene.num_tasks
                or bound>scene.num_robots or counted_edges<covered_tasks
                or (mode=="probabilistic_complete_fallback"
                    and actual_count!=scene.num_tasks)):
            fail("run_one_p2j_case","contract",
                 "P2J_V3_CERTIFIED_SCORE_COMPLETION_CONTRACT",
                 expected={"committed":"certified max matching + paid fallback",
                           "v3_total_tasks":scene.num_tasks},
                 actual={"score_edges":counted_edges,"supported_tasks":covered_tasks,
                         "score_maximum":bound,"fallback_count":len(fallback),
                         "committed":actual_count})
    fallback_cost=sum(scene.cost_matrix[r][t] for r,t in fallback)
    vote_supported_cost=float(native["total_assignment_cost"])-fallback_cost
    reference,cost,increase=measure_p2j_complete_quality(scene=scene,native=native)
    return {
        "source_sha":source_sha,"seed":scene.seed,
        "loss_percent":int(round(p_loss*100)),"mode":mode,
        "scene_sha256":scene_sha256(scene),"robots":scene.num_robots,
        "tasks":scene.num_tasks,"capacity":1,
        "votes_per_voter":votes_per_voter if mode!="one_batch_greedy" else "",
        "temperature":temperature if mode!="one_batch_greedy" else "",
        "margin_rule":margin_rule if mode!="one_batch_greedy" else "",
        "native_complete":int(native["full_commit"]),
        "committed_tasks":int(native["tasks_committed"]),
        "coverage_percent":100*int(native["tasks_committed"])/scene.num_tasks,
        "committed_cost_m":float(native["total_assignment_cost"]),
        "cost_per_committed_task_m":(float(native["total_assignment_cost"])/int(native["tasks_committed"])
                                      if int(native["tasks_committed"]) else ""),
        "full_info_global_greedy_cost":reference,
        "native_complete_cost":cost,
        "cost_increase_percent":increase,
        "native_stop_ms":float(native["allocation_or_stop_ms"]),
        "sender_sends":int(native["total_original_send_count"]),
        "sender_bytes":int(native["total_sender_application_bytes"]),
        **paid,
        "cost_receiver_drops":int(native["cost_remote_packet_drop_count"]),
        "vote_receiver_drops":int(native["vote_remote_packet_drop_count"]),
        "rounds_executed":int(native["rounds_executed"]),
        "certified_score_edge_count":native["certified_score_edge_count"],
        "certified_score_supported_tasks":native["certified_score_supported_tasks"],
        "certified_score_max_matching":native["certified_score_max_matching"],
        "completion_fallback_count":len(fallback),
        "completion_fallback_cost_m":fallback_cost,
        "completion_fallback_pairs_json":json.dumps(fallback,separators=(",",":")),
        "vote_supported_cost_m":vote_supported_cost,
        "assignment_digest":native["assignment_digest_sha256"],
        "native_assignment_json":json.dumps(pairs,separators=(",",":")),
        "first_epoch_digest":native["first_epoch_sha256"],
        "native_diagnostic":"",
    }


def summarize_p2j_cases(rows: list[dict],losses: tuple[int,...]) -> list[dict]:
    """All-seed stop/bytes/coverage; only completed allocations have cost gaps."""
    output=[]
    for loss in losses:
        for mode in MODES:
            cohort=[r for r in rows if r["loss_percent"]==loss and r["mode"]==mode]
            if not cohort:
                fail("summarize_p2j_cases","contract","P2J_MISSING_COHORT",
                     expected=(loss,mode),actual=len(cohort))
            complete=[r for r in cohort if r["native_complete"]]
            if any(r["cost_increase_percent"] in ("",None) for r in complete):
                fail("summarize_p2j_cases","contract","P2J_SUCCESS_MISSING_COST",
                     expected=len(complete),actual=complete[:1])
            def mean(name,group=cohort):
                return sum(float(r[name]) for r in group)/len(group) if group else ""
            output.append({
                "loss_percent":loss,"mode":mode,"seeds":len(cohort),
                "full_completion_percent":100*len(complete)/len(cohort),
                "mean_task_coverage_percent":mean("coverage_percent"),
                "mean_cost_per_committed_task_m":mean(
                    "cost_per_committed_task_m",
                    [r for r in cohort if r["committed_tasks"]>0],
                ),
                "cost_success_n":len(complete),
                "cost_increase_percent":mean("cost_increase_percent",complete),
                "mean_stop_s":mean("native_stop_ms")/1000,
                "mean_sender_kB":mean("sender_bytes")/1000,
                "mean_cost_sender_kB":mean("cost_bytes")/1000,
                "mean_vote_sender_kB":mean("vote_bytes")/1000,
                "mean_score_sender_kB":mean("score_bytes")/1000,
                "mean_certified_score_edges":mean(
                    "certified_score_edge_count",
                    [r for r in cohort if r["mode"]=="probabilistic_global_margin"],
                ),
                "mean_certified_score_supported_tasks":mean(
                    "certified_score_supported_tasks",
                    [r for r in cohort if r["mode"]=="probabilistic_global_margin"],
                ),
                "mean_certified_score_max_matching":mean(
                    "certified_score_max_matching",
                    [r for r in cohort if r["mode"]=="probabilistic_global_margin"],
                ),
                "mean_vote_receiver_drops":mean("vote_receiver_drops"),
            })
    return output


def validate_p2j_matched_grid(
    rows: list[dict], losses: tuple[int,...], first_seed: int, seeds: int,
) -> None:
    """Both arms are paired on identical original E0 seed scenes and greedy cost."""
    expected=tuple((loss,seed,mode)
                   for loss in losses
                   for seed in range(first_seed,first_seed+seeds)
                   for mode in MODES)
    observed=tuple((r["loss_percent"],r["seed"],r["mode"]) for r in rows)
    if expected!=observed:
        fail("validate_p2j_matched_grid","contract","P2J_GRID_NOT_PAIRED",
             expected=len(expected),actual={"count":len(observed),"unique":len(set(observed))})
    for i in range(0,len(rows),2):
        a,b=rows[i:i+2]
        if (a["scene_sha256"]!=b["scene_sha256"]
                or a["full_info_global_greedy_cost"]!=b["full_info_global_greedy_cost"]):
            fail("validate_p2j_matched_grid","contract","P2J_SCENE_OR_REFERENCE_MISMATCH",
                 expected=(a["scene_sha256"],a["full_info_global_greedy_cost"]),
                 actual=(b["scene_sha256"],b["full_info_global_greedy_cost"]))
    for row in rows:
        complete=bool(row["native_complete"])
        if complete!=(row["cost_increase_percent"] not in ("",None)):
            fail("validate_p2j_matched_grid","contract","P2J_INCOMPLETE_COST_IMPUTED",
                 expected="cost iff all tasks native committed",actual=row)


def save_p2j_evidence(*, root: Path, rows: list[dict], args,
                      config: dict, source_sha: str, losses: tuple[int,...]) -> None:
    summary=summarize_p2j_cases(rows,losses)
    summary_path=root/"summary_p2j.csv"
    write_csv(summary_path,summary,fields=SUMMARY_FIELDS)
    raw_path=root/"per_seed_p2j.csv"
    config_path=root/"run_config_p2j.json"
    manifest={
        "study":"P2J_V2_RELIABLE_SCORE_GLOBAL_MATCHING",
        "source_sha":source_sha,"created_utc":datetime.now(timezone.utc).isoformat(),
        "python":sys.version,"platform":platform.platform(),
        "formal":bool(args.formal),"config":config,
        "cases":len(rows),"groups":len(summary),
        "sha256":{p.name:sha256_file(p) for p in
                  (raw_path,config_path,summary_path)},
        "notice":"No-loss Greedy parity is required only for control. "
                 "Stochastic global-matching results may remain incomplete if the CERTIFIED Score graph is Hall-deficient; "
                 "neither successes nor cost quality may be fabricated.",
    }
    (root/"manifest_p2j.json").write_text(
        json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8",
    )


def run_p2j(args):
    losses=validate_p2j_config(args)
    source_sha=read_source_sha()
    profile=load_rady_latency_profile(ensure_rady_dataset(args.rady_json))
    root=Path(args.output_root)
    if root.exists():
        fail("run_p2j","state","P2J_OUTPUT_EXISTS",
             expected="fresh append-only evidence directory",actual=str(root))
    root.mkdir(parents=True)
    config={
        "study":"P2J_V2_RELIABLE_SCORE_GLOBAL_MATCHING",
        "source_sha":source_sha,"loss_percent":losses,
        "first_seed":args.first_seed,"seeds":args.seeds,
        "robots":100,"tasks":100,"capacity":1,"modes":MODES,
        "votes_per_voter":args.votes_per_voter,
        "temperature":args.temperature,"margin_rule":args.margin_rule,
        "vote_policy":"Uniform task then per-task visible-Cost Boltzmann",
        "assignment":"Global max-cardinality certified Score matching, then "+args.margin_rule+" signed vote margin, received ticket count, announced own Cost",
        "transmission":"one original Cost broadcast and one serialized Vote per voter; no DATA retries; reliable paid Score/Commit",
        "radio":"Rady empirical latency samples plus hypothetical 144Mbps shared serialized medium",
        "cost_reference":"offline full-info global minimum-pair Greedy (complete-only)",
        "rady_json":str(args.rady_json),"formal":bool(args.formal),
    }
    (root/"run_config_p2j.json").write_text(
        json.dumps(config,ensure_ascii=False,indent=2),encoding="utf-8",
    )
    rows=[]
    raw=root/"per_seed_p2j.csv"
    with raw.open("x",newline="",encoding="utf-8") as out:
        writer=csv.DictWriter(out,fieldnames=RAW_FIELDS,extrasaction="raise")
        writer.writeheader()
        for loss in losses:
            for seed in range(args.first_seed,args.first_seed+args.seeds):
                scene=generate_e0_scenario(seed,100,100)
                for mode in MODES:
                    result=run_one_p2j_case(
                        scene=scene,profile=profile,p_loss=loss/100,mode=mode,
                        source_sha=source_sha,votes_per_voter=args.votes_per_voter,
                        temperature=args.temperature,margin_rule=args.margin_rule,
                    )
                    writer.writerow(result)
                    out.flush()
                    os.fsync(out.fileno())
                    rows.append(result)
                    print(f"P2J PL={loss}% seed={seed} mode={mode} "
                          f"committed={result['committed_tasks']}/100 "
                          f"cost_gap={result['cost_increase_percent']} "
                          f"stop_ms={result['native_stop_ms']:.3f} "
                          f"SEND_bytes={result['sender_bytes']}",flush=True)
    validate_p2j_matched_grid(rows,losses,args.first_seed,args.seeds)
    save_p2j_evidence(root=root,rows=rows,args=args,
                      config=config,source_sha=source_sha,losses=losses)
    print(f"P2J_COMPLETE rows={len(rows)} groups={2*len(losses)} "
          f"root={root}",flush=True)


def parse_args(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal",action="store_true")
    parser.add_argument("--losses",
                        default=",".join(f"{x/100:.2f}" for x in FORMAL_LOSSES))
    parser.add_argument("--seeds",type=int,default=2)
    parser.add_argument("--first-seed",type=int,default=0)
    parser.add_argument("--votes-per-voter",type=int,default=100)
    parser.add_argument("--temperature",type=float,default=5.0)
    parser.add_argument("--margin-rule",choices=("absolute","normalized"),
                        default="absolute")
    parser.add_argument("--rady-json",type=Path,default=DEFAULT_RADY)
    parser.add_argument("--output-root",type=Path,required=True)
    return parser.parse_args(argv)


def main(argv=None):
    run_p2j(parse_args(argv))


if __name__=="__main__":
    main()
