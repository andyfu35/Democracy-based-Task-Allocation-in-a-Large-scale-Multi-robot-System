"""P2G: 2 new native methods + 4 verified historical arms -> TWO large 2x2 SVGs.

Figure 1: Proposed Sequential, each task tried once, versus Centralized One-Shot.
Figure 2: Proposed multi-round Batch, native CBAA, native CBBA, Centralized
Cost retransmission to missing recipients, with original Global Greedy planner.
Existing P2/P2D/P2E/P2F raw archives are never modified or relabeled as new.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import ensure_rady_dataset, load_rady_latency_profile
from democracy_mrta.optimizer import solve_visible_batched_greedy_assignment
from democracy_mrta.scenario import generate_e0_scenario
from experiments.p2g_plot import FAMILIES, render_p2g_figure
from experiments.run_p1_matched_five import (
    DEFAULT_RADY, read_source_sha, run_matched_case, scene_sha256,
    sha256_file, verify_one_scene, write_csv,
)
from experiments.run_p2d_centralized import run_one_centralized_case
from experiments.run_p2f_sequential_voting import (
    audit_native_sender_phases, count_observed_commits,
    extract_validated_native_batch,
)

OWNER = "experiments.run_p2g_two_figures"
LOSSES = tuple(range(0, 91, 10))
NEW_MODES = ("sequential_once", "centralized_retry")
LEGACY_MODES = ("centralized", "multi_round", "cbaa", "cbba")
ROUNDS = {"sequential_once":100, "centralized_retry":300}
LEGACY_CSV = Path("docs/figures/p2de/formal/verified_50point_summary.csv")
LEGACY_BLOB = "5326876027a9b42ac0fb95033b14cea79e46672e"
LEGACY_SHA = {
    "multi_round":"7271c11f8d74858c6066e6fca00a97643a0317dc",
    "centralized":"7271c11f8d74858c6066e6fca00a97643a0317dc",
    "cbaa":"f514cfa3613e7b0bad5c739d136b09fea8c3f92c",
    "cbba":"f514cfa3613e7b0bad5c739d136b09fea8c3f92c",
}
RAW_FIELDS = (
    "loss_percent","seed","mode","source_sha","scene_sha256",
    "robots","tasks","capacity","native_success","final_feasible",
    "committed_task_count","task_coverage","rounds_executed",
    "native_stop_ms","native_sender_sends","native_sender_bytes",
    "cost_sender_sends","cost_sender_bytes","vote_sender_sends",
    "score_sender_sends","commit_sender_sends","native_receiver_drops",
    "full_info_greedy_cost_m","final_total_distance_m",
    "cost_increase_percent","quality_sample_eligible",
    "native_stop_reason","native_diagnostic",
    "native_assignment_json","original_traffic_ledger_json",
)
SUMMARY_FIELDS = (
    "loss_percent","method","trials","native_complete",
    "completion_rate_percent","mean_task_coverage","quality_sample_count",
    "cost_increase_percent","mean_stop_s","mean_sender_kb",
    "mean_rounds_executed",
)


def fail(function, category, code, expected=None, actual=None, details=""):
    raise ProtocolError(Diagnostic(
        owner=OWNER, function=function, category=category, code=code,
        expected=expected, actual=actual, details=details,
    ))


def validate_p2g_config(args):
    """Freeze paired formal cohort and a strict loss/seed grid."""
    try:
        raw=tuple(float(v.strip()) for v in args.losses.split(","))
    except (ValueError,TypeError,AttributeError) as e:
        fail("validate_p2g_config","data","P2G_INVALID_LOSS_GRID",LOSSES,str(e))
    losses=tuple(round(v*100) for v in raw if math.isfinite(v))
    if (len(losses)!=len(raw) or not raw or
            losses!=tuple(sorted(set(losses))) or
            any(v not in LOSSES or abs(v/100-f)>1e-10
                for v,f in zip(losses,raw))):
        fail("validate_p2g_config","data","P2G_INVALID_LOSS_GRID",LOSSES,raw)
    if (type(args.seeds) is not int or type(args.first_seed) is not int
            or not 1<=args.seeds<=100 or not 0<=args.first_seed
            or args.first_seed+args.seeds>100):
        fail("validate_p2g_config","data","P2G_INVALID_SEEDS",
             "1..100 contiguous seeds inside [0,99]",
             (args.first_seed,args.seeds))
    if args.formal and (losses!=LOSSES or args.seeds!=100 or args.first_seed!=0):
        fail("validate_p2g_config","contract","P2G_FORMAL_COHORT_CHANGED",
             (LOSSES,0,100),(losses,args.first_seed,args.seeds))
    return losses


def case_keys(losses, first_seed, seeds):
    """Deterministic append-only source order for exactly two NEW native arms."""
    return tuple(
        (loss,seed,mode) for loss in losses
        for seed in range(first_seed,first_seed+seeds)
        for mode in NEW_MODES
    )


def prepare_p2g_evidence(args, source_sha, losses):
    """New root by default; resume only exact same Git source/config and prefix."""
    root=Path(args.output_root)
    config={
        "study":"P2G_TWO_FAMILY_GREEDY_SINGLE_ATTEMPT_VS_REPEATABLE",
        "source_sha":source_sha,"new_modes":NEW_MODES,"new_mode_limits":ROUNDS,
        "historical_p2de_git_blob":LEGACY_BLOB,
        "loss_percent":losses,"first_seed":args.first_seed,
        "seeds":args.seeds,"formal":bool(args.formal),
        "robots":100,"tasks":100,"capacity":1,
        "rady_json":str(Path(args.rady_json).expanduser().resolve()),
        "radio":"Rady bootstrap and assumed 144Mbps shared medium",
        "sender_bytes":"physical attempted application payload SENDs, including drops",
        "native_differences":"Proposed fresh Vote redecision vs Centralized Cost retry; CBAA/CBBA own original algorithms",
    }
    cfg=root/"run_config_p2g.json";raw=root/"per_seed_p2g.csv"
    if not args.resume:
        if root.exists():
            fail("prepare_p2g_evidence","state","P2G_OUTPUT_EXISTS","new result directory",str(root))
        root.mkdir(parents=True)
        cfg.write_text(json.dumps(config,indent=2,ensure_ascii=False),encoding="utf-8")
        with raw.open("x",newline="",encoding="utf-8") as f:
            csv.DictWriter(f,fieldnames=RAW_FIELDS).writeheader()
        return [],config
    if not cfg.is_file() or not raw.is_file() or (root/"manifest_p2g.json").exists():
        fail("prepare_p2g_evidence","state","P2G_INVALID_RESUME_ROOT",
             "incomplete P2G output with identical source",str(root))
    try:
        old=json.loads(cfg.read_text(encoding="utf-8"))
    except (ValueError,OSError) as exc:
        fail("prepare_p2g_evidence","data","P2G_BAD_RESUME_CONFIG","JSON",str(exc))
    if old!=json.loads(json.dumps(config)):
        fail("prepare_p2g_evidence","contract","P2G_RESUME_CONFIG_CHANGED",old,config)
    with raw.open(newline="",encoding="utf-8") as file:
        reader=csv.DictReader(file)
        if tuple(reader.fieldnames or ())!=RAW_FIELDS:
            fail("prepare_p2g_evidence","contract","P2G_RESUME_COLUMNS_CHANGED",
                 RAW_FIELDS,reader.fieldnames)
        rows=list(reader)
    observed=tuple((int(r["loss_percent"]),int(r["seed"]),r["mode"]) for r in rows)
    expected=case_keys(losses,args.first_seed,args.seeds)
    if observed!=expected[:len(observed)]:
        fail("prepare_p2g_evidence","contract","P2G_RESUME_PREFIX_CHANGED",
             expected[:len(observed)],observed)
    for r in rows:
        scene=generate_e0_scenario(int(r["seed"]),100,100)
        if (r["source_sha"]!=source_sha or
                r["scene_sha256"]!=scene_sha256(scene) or
                int(r["robots"])!=100 or int(r["tasks"])!=100 or
                int(r["rounds_executed"])>ROUNDS[r["mode"]]):
            fail("prepare_p2g_evidence","contract","P2G_RESUME_ROW_CHANGED",
                 "source, scene, mode limit and dimensions unchanged",r)
    return rows,config


def read_verified_legacy_summary(losses):
    """SHA-pinned ORIGINAL published 50 groups; no source ZIP fiction."""
    path=LEGACY_CSV
    if not path.is_file():
        fail("read_verified_legacy_summary","dependency","P2G_VERIFIED_LEGACY_SUMMARY_MISSING",
             str(path),None)
    raw=path.read_bytes()
    git_blob=hashlib.sha1(
        b"blob "+str(len(raw)).encode("ascii")+b"\0"+raw
    ).hexdigest()
    if git_blob!=LEGACY_BLOB:
        fail("read_verified_legacy_summary","contract","P2G_LEGACY_BLOB_CHANGED",
             LEGACY_BLOB,git_blob)
    with path.open(newline="",encoding="utf-8") as f:
        records=list(csv.DictReader(f))
    expected={(p,m) for p in LOSSES
              for m in ("single_round","multi_round","cbaa","cbba","centralized")}
    actual=[(int(r["loss_percent"]),r["method"]) for r in records]
    if len(actual)!=50 or set(actual)!=expected:
        fail("read_verified_legacy_summary","contract","P2G_LEGACY_GRID_CHANGED",
             (50,expected),(len(actual),set(actual)))
    for r in records:
        m=r["method"]
        if (int(r["trials"])!=100 or
                not 0<=int(r["cost_success_n"])<=int(r["native_complete"])<=100):
            fail("read_verified_legacy_summary","contract",
                 "P2G_LEGACY_QUALITY_DENOMINATOR_CHANGED",
                 "100 trials and quality n<=completed",r)
        if m in LEGACY_SHA and r["source_native_git_sha"]!=LEGACY_SHA[m]:
            fail("read_verified_legacy_summary","contract",
                 "P2G_LEGACY_NATIVE_SHA_CHANGED",LEGACY_SHA[m],r)
        if (int(r["cost_success_n"])==0)!=(r["cost_increase_percent"] in ("",None)):
            fail("read_verified_legacy_summary","contract",
                 "P2G_LEGACY_COST_MISSINGNESS",
                 "n=0 iff cost empty",r)
    return records,{"p2de_verified_blob":git_blob,
                    "p2de_verified_sha256":hashlib.sha256(raw).hexdigest(),
                    "verified_rows":50,"historical_native_git_sha":LEGACY_SHA}


def audit_centralized_retry_sender_phases(native):
    """Independently check actual physical central Cost retry traffic."""
    try:
        ledger=json.loads(native["original_traffic_ledger_json"])
        phases=ledger["network"]["sender_by_phase"]
        total_sends=sum(int(x["sender_sends"]) for x in phases.values())
        total_bytes=sum(int(x["sender_bytes"]) for x in phases.values())
        cost=phases["centralized_cost"]
        cost_sends=int(cost["sender_sends"])
        cost_bytes=int(cost["sender_bytes"])
        task=phases.get("task_announcement",{"sender_sends":0})
        commit=phases.get("commit",{"sender_sends":0})
        assignment=phases.get("centralized_assignment",{"sender_sends":0})
    except (KeyError,TypeError,ValueError,json.JSONDecodeError) as exc:
        fail("audit_centralized_retry_sender_phases","data",
             "P2G_MALFORMED_CENTRAL_SENDER_LEDGER",
             "physical network sender_by_phase",str(exc))
    expected=(int(native["native_sender_sends"]),int(native["native_sender_bytes"]))
    if (total_sends,total_bytes)!=expected:
        fail("audit_centralized_retry_sender_phases","contract",
             "P2G_CENTRAL_SENDER_SUM_MISMATCH",expected,(total_sends,total_bytes))
    if (cost_sends!=int(native["cost_sender_sends"])
            or cost_bytes!=int(native["cost_sender_bytes"])
            or int(assignment["sender_sends"])!=1
            or int(commit["sender_sends"])!=int(native["committed_task_count"])
            or int(task["sender_sends"])!=3):
        fail("audit_centralized_retry_sender_phases","contract",
             "P2G_CENTRAL_PHASE_MISMATCH",
             "one TASK=3, one assignment, one Commit per pair, Cost physical",
             {"task":task,"cost":cost,"decision":assignment,"commit":commit})
    return {
        "rounds":int(native["cost_rounds_executed"]),
        "cost_sends":cost_sends,"cost_bytes":cost_bytes,
        "vote_sends":0,"score_sends":0,
        "commit_sends":int(commit["sender_sends"]),
        "drops":int(native["cost_receiver_drops"]),
    }


def execute_p2g_native(scene, profile, p_loss, mode):
    """Call the real original method owner, never plan or assign in study code."""
    if mode=="sequential_once":
        native=run_matched_case(
            scene,profile,"voting",p_loss,160,ROUNDS[mode],
            voting_strategy="greedy_batch",batch_vote_scope="one_task",
        )
        batch,rounds=extract_validated_native_batch(scene,native,ROUNDS[mode])
        pairs=count_observed_commits(native)
        physical=audit_native_sender_phases(native,batch["sender_by_phase"])
        ledger=json.loads(native["original_traffic_ledger_json"])
        audit={
            "rounds":rounds,
            "cost_sends":physical["cost_sender_sends"],
            "cost_bytes":physical["cost_sender_bytes"],
            "vote_sends":physical["vote_sender_sends"],
            "score_sends":physical["score_sender_sends"],
            "commit_sends":physical["commit_sender_sends"],
            "drops":int(ledger["native"]["cost_receiver_drops"])+
                    int(ledger["native"]["vote_receiver_drops"]),
        }
    elif mode=="centralized_retry":
        native=run_one_centralized_case(
            scene,profile,p_loss,max_cost_rounds=ROUNDS[mode],
        )
        pairs=tuple((int(r),int(t)) for r,t in json.loads(native["native_assignment_json"]))
        audit=audit_centralized_retry_sender_phases(native)
    else:
        fail("execute_p2g_native","data","P2G_UNKNOWN_NATIVE_MODE",
             NEW_MODES,mode)
    return native,pairs,audit


def validate_p2g_native_outcome(scene, native, pairs, audit, mode):
    """Safety/contract audit without mutating the owner or observer."""
    rounds=audit["rounds"]
    cost_sends=audit["cost_sends"]
    if (mode=="sequential_once" and
            (cost_sends!=scene.num_robots or rounds>scene.num_tasks)):
        fail("validate_p2g_native_outcome","contract","P2G_SERIAL_SCOPE_VIOLATED",
             {"Cost":scene.num_robots,"task_epochs_max":scene.num_tasks},
             {"Cost":cost_sends,"rounds":rounds})
    if (mode=="centralized_retry" and
            (cost_sends<scene.num_robots-1 or
             cost_sends>(scene.num_robots-1)*ROUNDS[mode] or
             rounds>ROUNDS[mode])):
        fail("validate_p2g_native_outcome","contract","P2G_CENTRAL_RETRY_BOUND_VIOLATED",
             "99<=Cost SENDs<=29700 and rounds<=300",
             (cost_sends,rounds))
    if len(pairs)!=len({r for r,t in pairs}) or len(pairs)!=len({t for r,t in pairs}):
        fail("validate_p2g_native_outcome","safety","P2G_DUPLICATE_PAIR",
             "capacity=1",pairs)
    if (int(native["native_success"]) and
            (not int(native["final_feasible"]) or len(pairs)!=scene.num_tasks)):
        fail("validate_p2g_native_outcome","contract",
             "P2G_SUCCESS_WITHOUT_100_VALID_PAIRS",
             scene.num_tasks,(native["native_success"],native["final_feasible"],len(pairs)))


def measure_p2g_complete_quality(scene, native):
    """Offline Global Greedy is NEVER exposed to the native method planner."""
    full=solve_visible_batched_greedy_assignment(
        scene.cost_matrix,frozenset(range(scene.num_robots)),
    )
    success=int(native["native_success"]) and int(native["final_feasible"])
    cost=float(native["final_total_distance_m"]) if success else ""
    increase=100*(cost/full.total_cost-1) if success else ""
    return full.total_cost,cost,increase


def run_one_p2g_case(scene, profile, p_loss, mode, source_sha):
    """Orchestrate one native run, separate audits, and source-labeled evidence."""
    verify_one_scene(scene)
    native,pairs,audit=execute_p2g_native(scene,profile,p_loss,mode)
    validate_p2g_native_outcome(scene,native,pairs,audit,mode)
    reference,cost,inc=measure_p2g_complete_quality(scene,native)
    return {
        "loss_percent":int(round(p_loss*100)),"seed":scene.seed,"mode":mode,
        "source_sha":source_sha,"scene_sha256":scene_sha256(scene),
        "robots":scene.num_robots,"tasks":scene.num_tasks,"capacity":1,
        "native_success":int(native["native_success"]),
        "final_feasible":int(native["final_feasible"]),
        "committed_task_count":len(pairs),"task_coverage":len(pairs)/scene.num_tasks,
        "rounds_executed":audit["rounds"],
        "native_stop_ms":native["native_stop_ms"],
        "native_sender_sends":native["native_sender_sends"],
        "native_sender_bytes":native["native_sender_bytes"],
        "cost_sender_sends":audit["cost_sends"],
        "cost_sender_bytes":audit["cost_bytes"],
        "vote_sender_sends":audit["vote_sends"],
        "score_sender_sends":audit["score_sends"],
        "commit_sender_sends":audit["commit_sends"],
        "native_receiver_drops":audit["drops"],
        "full_info_greedy_cost_m":reference,
        "final_total_distance_m":cost,
        "cost_increase_percent":inc,
        "quality_sample_eligible":int(cost!=""),
        "native_stop_reason":native["native_stop_reason"],
        "native_diagnostic":native["native_diagnostic"],
        "native_assignment_json":native["native_assignment_json"],
        "original_traffic_ledger_json":native["original_traffic_ledger_json"],
    }


def validate_p2g_grid(rows,losses,first_seed,seeds):
    """Exactly two arms per scene and native SEND and failed-cost invariants."""
    expected=case_keys(losses,first_seed,seeds)
    observed=tuple((int(r["loss_percent"]),int(r["seed"]),r["mode"]) for r in rows)
    if expected!=observed:
        fail("validate_p2g_grid","contract","P2G_NATIVE_GRID_INCOMPLETE",
             len(expected),{"rows":len(observed),"unique":len(set(observed))})
    by_key={(int(r["loss_percent"]),int(r["seed"]),r["mode"]):r for r in rows}
    for loss in losses:
        for seed in range(first_seed,first_seed+seeds):
            a=by_key[(loss,seed,"sequential_once")]
            b=by_key[(loss,seed,"centralized_retry")]
            if (a["scene_sha256"]!=b["scene_sha256"] or
                    float(a["full_info_greedy_cost_m"])!=float(b["full_info_greedy_cost_m"])):
                fail("validate_p2g_grid","contract","P2G_SCENE_NOT_PAIRED",
                     (loss,seed,"same coordinates and cost reference"),(a,b))
    for r in rows:
        if (int(r["rounds_executed"])>ROUNDS[r["mode"]]
                or not 0<=float(r["task_coverage"])<=1
                or abs(float(r["task_coverage"])*100-int(r["committed_task_count"]))>1e-9
                or int(r["native_sender_bytes"])<int(r["cost_sender_bytes"])):
            fail("validate_p2g_grid","contract","P2G_NATIVE_LEDGER_INVALID",
                 "round limit, valid coverage, physically paid Cost Bytes",r)
        success=bool(int(r["native_success"])) and bool(int(r["final_feasible"]))
        if success != (r["cost_increase_percent"] not in ("",None)):
            fail("validate_p2g_grid","contract","P2G_INCOMPLETE_COST_IMPUTED",
                 "cost only for native complete cases",r)


def summarize_new_p2g(rows,losses):
    """All-seed sender exposure and stop, success-only quality with sample n."""
    output=[]
    for loss in losses:
        for mode in NEW_MODES:
            cells=[r for r in rows if int(r["loss_percent"])==loss and r["mode"]==mode]
            if not cells:
                fail("summarize_new_p2g","contract","P2G_EMPTY_SUMMARY_COHORT",
                     (loss,mode),"empty")
            n=len(cells)
            qualified=[r for r in cells if int(r["native_success"]) and
                       int(r["final_feasible"])]
            quality=[float(r["cost_increase_percent"]) for r in qualified
                     if r["cost_increase_percent"] not in ("",None)]
            if len(quality)!=len(qualified):
                fail("summarize_new_p2g","contract","P2G_MISSING_SUCCESS_COST",
                     len(qualified),len(quality))
            output.append({
                "loss_percent":loss,"method":mode,"trials":n,
                "native_complete":len(qualified),
                "completion_rate_percent":100*len(qualified)/n,
                "mean_task_coverage":sum(float(r["task_coverage"]) for r in cells)/n,
                "quality_sample_count":len(quality),
                "cost_increase_percent":sum(quality)/len(quality) if quality else "",
                "mean_stop_s":sum(float(r["native_stop_ms"]) for r in cells)/n/1000,
                "mean_sender_kb":sum(float(r["native_sender_bytes"]) for r in cells)/n/1000,
                "mean_rounds_executed":sum(float(r["rounds_executed"]) for r in cells)/n,
            })
    return output


def build_figure_source(new_summary,legacy,losses):
    """Join two native-source cohorts without renaming their actual algorithms."""
    verified={}
    rename={"centralized":"centralized_one_shot","multi_round":"proposed_multi",
            "cbaa":"cbaa","cbba":"cbba"}
    for r in legacy:
        p=int(r["loss_percent"])
        if p not in losses or r["method"] not in rename:
            continue
        target=rename[r["method"]]
        verified[(p,target)]={
            "loss_percent":p,"method":target,"trials":int(r["trials"]),
            "native_complete":int(r["native_complete"]),
            "completion_rate_percent":float(r["completion_rate_percent"]),
            "mean_task_coverage":float(r["mean_terminal_conflict_free_task_coverage_percent"])/100,
            "quality_sample_count":int(r["cost_success_n"]),
            "cost_increase_percent":r["cost_increase_percent"],
            "mean_stop_s":float(r["mean_all_seed_native_stop_s"]),
            "mean_sender_kb":float(r["mean_attempted_sender_kB"]),
        }
    fresh={(int(r["loss_percent"]),r["method"]):r for r in new_summary}
    figures={}
    for family,methods in FAMILIES.items():
        pool={**verified,**fresh}
        figures[family]=[pool[(p,method)] for p in losses for method in methods]
    return figures


def write_p2g_results(args,rows,losses,config,source_sha,legacy,provenance):
    """Append-only raw already fsynced; derived CSV+figure and source SHA manifest."""
    root=Path(args.output_root)
    new=summarize_new_p2g(rows,losses)
    summary_path=root/"summary_p2g.csv"
    write_csv(summary_path,new,fields=SUMMARY_FIELDS)
    outputs=[root/"run_config_p2g.json",root/"per_seed_p2g.csv",summary_path]
    if args.formal:
        figure_rows=build_figure_source(new,legacy,losses)
        for family,filename in (
            ("one_attempt","figure1_single_attempt.svg"),
            ("repeatable","figure2_repeatable.svg"),
        ):
            dest=root/filename
            dest.write_text(render_p2g_figure(figure_rows[family],losses,family),
                            encoding="utf-8")
            outputs.append(dest)
    manifest={
        "study":"P2G_TWO_LARGE_FOUR_PANEL_FIGURES",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "new_native_source_sha":source_sha,"config":config,
        "new_native_cases":len(rows),"new_summary_groups":len(new),
        "new_modes":NEW_MODES,
        "historical_method_cases_in_figures":(4*10*100 if args.formal else 0),
        "historical_aggregate_provenance":provenance,
        "historical_source_notice":"P2D One Shot Centralized, P2E Proposed multi, original P2 CBAA/CBBA are SHA-pinned aggregates, NOT new method executions",
        "timing_notice":"Rady latency and assumed 144Mbps, not measured field network",
        "native_protocol_notice":"Proposed re-votes, Centralized retries missing Cost; CBAA/CBBA stay unmodified native consensus",
        "sender_bytes_definition":"actual attempted application SEND, including Cost/Vote packets lost to receivers",
        "cost_definition":"signed percent over same-scene offline full-info minimum-pair Global Greedy, only native-complete cases",
        "sha256":{p.name:sha256_file(p) for p in outputs},
    }
    (root/"manifest_p2g.json").write_text(
        json.dumps(manifest,indent=2,ensure_ascii=False),encoding="utf-8"
    )
    return new


def run_p2g(args):
    losses=validate_p2g_config(args)
    original,provenance=read_verified_legacy_summary(losses)
    source_sha=read_source_sha()
    profile=load_rady_latency_profile(ensure_rady_dataset(args.rady_json))
    rows,config=prepare_p2g_evidence(args,source_sha,losses)
    expected=case_keys(losses,args.first_seed,args.seeds)
    raw_path=Path(args.output_root)/"per_seed_p2g.csv"
    with raw_path.open("a",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=RAW_FIELDS)
        for loss,seed,mode in expected[len(rows):]:
            scene=generate_e0_scenario(seed,100,100)
            r=run_one_p2g_case(scene,profile,loss/100,mode,source_sha)
            writer.writerow({key:r.get(key,"") for key in RAW_FIELDS})
            f.flush()
            os.fsync(f.fileno())
            rows.append(r)
            print(f"P2G PL={loss}% seed={seed} mode={mode} "
                  f"committed={r['committed_task_count']} "
                  f"rounds={r['rounds_executed']} "
                  f"bytes={r['native_sender_bytes']} "
                  f"stop_ms={float(r['native_stop_ms']):.3f} "
                  f"cost_increase={r['cost_increase_percent']}",flush=True)
    validate_p2g_grid(rows,losses,args.first_seed,args.seeds)
    summary=write_p2g_results(
        args,rows,losses,config,source_sha,original,provenance
    )
    print(f"P2G_COMPLETE native_cases={len(rows)} groups={len(summary)} "
          f"figures={2 if args.formal else 0} root={args.output_root}",
          flush=True)
    return summary


def parse_args(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--formal",action="store_true")
    p.add_argument("--losses",default=",".join(f"{x/100:.2f}" for x in LOSSES))
    p.add_argument("--seeds",type=int,default=2)
    p.add_argument("--first-seed",type=int,default=0)
    p.add_argument("--rady-json",type=Path,default=DEFAULT_RADY)
    p.add_argument("--output-root",type=Path,required=True)
    p.add_argument("--resume",action="store_true")
    return p.parse_args(argv)


def main(argv=None):
    run_p2g(parse_args(argv))


if __name__=="__main__":
    main()
