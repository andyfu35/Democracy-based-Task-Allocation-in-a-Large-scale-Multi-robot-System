"""P2H Figure 1: TRUE interactive T0 Vote/Commit -> retire -> T1, paired with Centralized.

This is NOT archived P2G's one Vote BATCH, nor P2F's 300-epoch global
batch ballot filter. Existing P2G/ P2E Figure 2 remains immutable.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path

from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import (
    ensure_rady_dataset, load_rady_latency_profile,
    estimate_e9h_guarded_initial_cost_ms,
)
from democracy_mrta.optimizer import (
    solve_hungarian_assignment, solve_visible_task_ordered_greedy_assignment,
)
from democracy_mrta.scenario import generate_e0_scenario
from experiments.p1_feasibility import FirstFeasibleObserver
from experiments.p2g_plot import render_p2g_figure
from experiments.run_e9h_adaptive_deadline import (
    DEFAULT_OLD_FIXED_MS, build_e9h_deadline_schedule,
    run_e9h_original_voting_case,
)
from experiments.run_e9i_cost30_scaling import selected_e9i_arms
from experiments.run_p1_matched_five import (
    DEFAULT_RADY, read_source_sha, scene_sha256, sha256_file,
    verify_one_scene, write_csv,
)
from experiments.run_p2d_centralized import run_one_centralized_case


OWNER="experiments.run_p2h_sequential_figure1"
LOSSES=tuple(range(0,91,10))
MODES=("task_ordered_vote_sequential_once","centralized_task_ordered_sequential_once")
PHASES=("task","cost","vote","score","commit")
RAW_FIELDS=(
    "loss_percent","seed","mode","source_sha","scene_sha256",
    "robots","tasks","capacity","native_success","final_feasible",
    "committed_task_count","task_coverage","rounds_executed",
    "native_stop_ms","native_sender_sends","native_sender_bytes",
    "task_sender_sends","cost_sender_sends","cost_sender_bytes",
    "vote_sender_sends","score_sender_sends","assignment_sender_sends",
    "commit_sender_sends","native_receiver_drops",
    "full_info_reference_cost_m","final_total_distance_m",
    "cost_increase_percent","quality_sample_eligible","native_stop_reason",
    "native_assignment_json","attempted_task_ids_json",
    "per_task_commits_json","original_traffic_ledger_json",
)
SUMMARY_FIELDS=(
    "loss_percent","method","trials","native_complete","completion_rate_percent",
    "mean_task_coverage","quality_sample_count","cost_increase_percent",
    "mean_stop_s","mean_sender_kb","mean_rounds_executed",
)


def fail(function,category,code,expected=None,actual=None,details=""):
    raise ProtocolError(Diagnostic(
        owner=OWNER,function=function,category=category,code=code,
        expected=expected,actual=actual,details=details,
    ))


def validate_p2h_config(args):
    """Data/contract boundary for exact 100R100T C1 and paired formal cohort."""
    try:
        floats=tuple(float(x.strip()) for x in args.losses.split(","))
    except (ValueError,AttributeError,TypeError) as e:
        fail("validate_p2h_config","data","P2H_INVALID_LOSS_GRID",LOSSES,str(e))
    losses=tuple(round(100*x) for x in floats if math.isfinite(x))
    if (not floats or len(losses)!=len(floats)
            or losses!=tuple(sorted(set(losses)))
            or any(p not in LOSSES or abs(p/100.0-v)>1e-10
                   for p,v in zip(losses,floats))):
        fail("validate_p2h_config","data","P2H_INVALID_LOSS_GRID",LOSSES,floats)
    if (type(args.seeds) is not int or type(args.first_seed) is not int
            or not 1<=args.seeds<=100 or not 0<=args.first_seed
            or args.first_seed+args.seeds>100):
        fail("validate_p2h_config","data","P2H_INVALID_SEED_RANGE",
             "contiguous seeds inside [0,99]",(args.first_seed,args.seeds))
    if args.formal and (losses!=LOSSES or args.seeds!=100 or args.first_seed!=0):
        fail("validate_p2h_config","contract","P2H_FORMAL_COHORT_CHANGED",
             (LOSSES,0,100),(losses,args.first_seed,args.seeds))
    return losses


def case_keys(losses,first_seed,seeds):
    return tuple((p,seed,mode) for p in losses
                 for seed in range(first_seed,first_seed+seeds)
                 for mode in MODES)


def prepare_p2h_evidence(args,source_sha,losses,rady_sha):
    """Append-only new-root or exact SHA/config/prefix resume; never overwrite P2G."""
    root=Path(args.output_root)
    config={
        "study":"P2H_INTERACTIVE_SEQUENTIAL_TASK_VOTING_ONCE",
        "source_sha":source_sha,"rady_sha256":rady_sha,
        "rady_path":str(Path(args.rady_json).expanduser().resolve()),
        "loss_percent":losses,"first_seed":args.first_seed,"seeds":args.seeds,
        "formal":bool(args.formal),"modes":MODES,"robots":100,"tasks":100,
        "capacity":1,"max_task_epochs":100,"cost_repetitions":1,
        "vote_repetitions":1,"coordinator_cost_repetitions":1,
        "proposed_strategy":"greedy_task/received_plurality with 100 per-task epochs",
        "centralized_scope":"task_ordered/task_sequence, one assignment and Commit per task",
        "radio":"Rady sampled latency plus hypothetical shared 144Mbps medium",
        "sender_bytes":"sum actual attempted application sender bytes including dropped SENDs",
        "complete_quality":"only fully completed native runs; full info task-ID Greedy reference",
    }
    cfg=root/"run_config_p2h.json";raw=root/"per_seed_p2h.csv"
    if not args.resume:
        if root.exists():
            fail("prepare_p2h_evidence","state","P2H_OUTPUT_ALREADY_EXISTS",
                 "new unique output root",str(root))
        root.mkdir(parents=True)
        cfg.write_text(json.dumps(config,indent=2,ensure_ascii=False),encoding="utf-8")
        with raw.open("x",newline="",encoding="utf-8") as f:
            csv.DictWriter(f,fieldnames=RAW_FIELDS).writeheader()
        return [],config
    if (not raw.is_file() or not cfg.is_file() or
            (root/"manifest_p2h.json").exists()):
        fail("prepare_p2h_evidence","state","P2H_UNSAFE_RESUME_ROOT",
             "incomplete same-source P2H root",str(root))
    try:
        previous=json.loads(cfg.read_text(encoding="utf-8"))
    except (ValueError,OSError) as e:
        fail("prepare_p2h_evidence","data","P2H_RESUME_CONFIG_INVALID","JSON",str(e))
    if previous!=json.loads(json.dumps(config)):
        fail("prepare_p2h_evidence","contract","P2H_RESUME_CONFIG_CHANGED",
             previous,config)
    with raw.open(newline="",encoding="utf-8") as f:
        reader=csv.DictReader(f)
        if tuple(reader.fieldnames or ())!=RAW_FIELDS:
            fail("prepare_p2h_evidence","contract","P2H_RESUME_HEADER_CHANGED",
                 RAW_FIELDS,reader.fieldnames)
        rows=list(reader)
    observed=tuple((int(r["loss_percent"]),int(r["seed"]),r["mode"]) for r in rows)
    expected=case_keys(losses,args.first_seed,args.seeds)
    if observed!=expected[:len(observed)]:
        fail("prepare_p2h_evidence","contract","P2H_RESUME_PREFIX_MISMATCH",
             expected[:len(observed)],observed)
    for r in rows:
        scene=generate_e0_scenario(int(r["seed"]),100,100)
        if (r["source_sha"]!=source_sha or
                r["scene_sha256"]!=scene_sha256(scene) or
                int(r["rounds_executed"])>100 or
                int(r["robots"])!=100 or int(r["tasks"])!=100
                or int(r["capacity"])!=1):
            fail("prepare_p2h_evidence","contract","P2H_RESUME_CASE_CHANGED",
                 "same source, original E0 scene, 100R100T C1",r)
    return rows,config


def execute_original_sequential_voting(scene,profile,p_loss):
    """Run existing real greedy_task owner, not P2F's global batch selector."""
    n=scene.num_robots
    observer=FirstFeasibleObserver(n)
    arm=next(a for a in selected_e9i_arms() if a[0]=="adaptive_guarded_k1_received")
    schedule=build_e9h_deadline_schedule(
        profile=profile,robots=n,design_rate_mbps=144.0,
        margin_factor=1.0,voting_strategy="greedy_task",
    )
    guarded=estimate_e9h_guarded_initial_cost_ms(
        profile=profile,total_robots=n,total_tasks=n,
        reference_phy_mbps=144.0,
    )
    native=run_e9h_original_voting_case(
        scenario=scene,profile=profile,n=n,seed=scene.seed,p_loss=p_loss,
        p_vote_loss=p_loss,rate=144.0,max_rounds=n,
        fixed_timeout_ms=DEFAULT_OLD_FIXED_MS,
        arm=arm,schedules={1.0:schedule},guarded_cost_ms=guarded,
        oracle_total_cost=solve_hungarian_assignment(scene.cost_matrix).total_cost,
        external_observer=observer.observe,
        voting_strategy="greedy_task",batch_vote_scope="all",
        capture_task_epoch_ids=True,
    )
    return native,tuple((int(r),int(t)) for r,t in observer.last_pairs)


def audit_one_pass_voting_epochs(scene,native,pairs):
    """First protocol boundary: exactly T0..T99, each Vote epoch then only own Commit."""
    try:
        attempted=tuple(int(v) for v in native["voted_task_ids"])
        committed_by_epoch=tuple(
            tuple((int(r),int(t)) for r,t in epoch)
            for epoch in native["newly_committed_by_epoch"]
        )
    except (TypeError,ValueError,KeyError) as e:
        fail("audit_one_pass_voting_epochs","data",
             "P2H_MISSING_NATIVE_VOTE_EPOCH_TRACE",
             "original 100 native task IDs and per-epoch Commit pairs",str(e))
    expected=tuple(range(scene.num_tasks))
    if attempted!=expected or len(committed_by_epoch)!=len(expected):
        fail("audit_one_pass_voting_epochs","contract",
             "P2H_VOTE_TASK_REPEATED_OR_SKIPPED",expected,attempted)
    if any(len(commits)>1 or any(t!=task_id for _,t in commits)
           for task_id,commits in zip(attempted,committed_by_epoch)):
        fail("audit_one_pass_voting_epochs","contract",
             "P2H_COMMIT_OUTSIDE_CURRENT_TASK",
             "zero or one Commit strictly on the current task",committed_by_epoch)
    flattened=tuple(pair for epoch in committed_by_epoch for pair in epoch)
    if (len(flattened)!=len({r for r,t in flattened})
            or len(flattened)!=len({t for r,t in flattened})
            or tuple(sorted(flattened,key=lambda v:(v[1],v[0])))!=
               tuple(sorted(pairs,key=lambda v:(v[1],v[0])))):
        fail("audit_one_pass_voting_epochs","safety",
             "P2H_VOTE_COMMIT_LEDGER_DIVERGENCE",pairs,flattened)
    return attempted,committed_by_epoch


def audit_native_sender_phases(native,pairs,scene):
    """Charge attempted physical sender Cost/Vote even when all receivers drop."""
    phases=native["sender_by_phase"]
    try:
        sends=sum(int(x["sender_sends"]) for x in phases.values())
        bytes_sent=sum(int(x["sender_bytes"]) for x in phases.values())
        gets=lambda p,unit:int(phases[p][f"sender_{unit}"])
        expected=(int(native["total_original_send_count"]),
                  int(native["total_sender_application_bytes"]))
        actual=(sends,bytes_sent)
    except (TypeError,ValueError,KeyError) as e:
        fail("audit_native_sender_phases","data","P2H_INVALID_SENDER_PHASE",
             "physically billed sender_by_phase",str(e))
    if actual!=expected:
        fail("audit_native_sender_phases","contract","P2H_SENDER_BYTES_MISMATCH",
             expected,actual)
    if (gets("cost","sends")!=scene.num_robots
            or gets("task","sends")!=3
            or gets("commit","sends")!=len(pairs)
            or gets("vote","sends")!=int(native["vote_sender_frames"])
            or gets("score","sends")!=
               int(native["vote_score_send_count"])):
        fail("audit_native_sender_phases","contract","P2H_NOT_ONE_COST_AND_VOTE_PER_TASK",
             "one Cost send/robot, one task broadcast; per-task Vote/Score/Commit",
             {"phase_sends":{p:gets(p,"sends") for p in PHASES},
              "committed":len(pairs)})
    return phases


def audit_centralized_sequential_sender_phases(native,pairs,scene):
    """Physical Cost once, N per-task assignment SEND/Commit; no hidden rows."""
    try:
        ledger=json.loads(native["original_traffic_ledger_json"])
        phases=ledger["network"]["sender_by_phase"]
        actual=(sum(int(x["sender_sends"]) for x in phases.values()),
                sum(int(x["sender_bytes"]) for x in phases.values()))
        expected=(int(native["native_sender_sends"]),
                  int(native["native_sender_bytes"]))
        trace=tuple(ledger["sequential_decision_commit_trace"])
        received=tuple(int(x) for x in ledger["received_cost_rows"])
        cost=phases["centralized_cost"]
        assignments=phases["centralized_assignment"]
        commits=phases["commit"]
        tasks=phases["task_announcement"]
    except (KeyError,TypeError,ValueError,json.JSONDecodeError) as e:
        fail("audit_centralized_sequential_sender_phases","data",
             "P2H_CENTRAL_NATIVE_LEDGER_INVALID",
             "native physical sender and per-task event trace",str(e))
    if (actual!=expected
            or int(cost["sender_sends"])!=scene.num_robots-1
            or int(assignments["sender_sends"])!=len(pairs)
            or int(commits["sender_sends"])!=len(pairs)
            or int(tasks["sender_sends"])!=3
            or int(native["cost_rounds_executed"])!=1
            or len(trace)!=len(pairs)
            or any(robot not in received for robot,task_id in pairs)):
        fail("audit_centralized_sequential_sender_phases","contract",
             "P2H_CENTRAL_SEQUENCE_LEDGER_MISMATCH",
             "99 Cost once, one paid assignment+Commit per visible pair",
             {"sender_count":actual,"expected":expected,
              "native_pair_count":len(pairs),"trace_count":len(trace)})
    previous=0.0
    for pair,t in zip(pairs,trace):
        if (t["task_id"]!=pair[1] or
                t["assignment_send_ms"]+1e-9<previous or
                t["commit_send_ms"]+1e-9<t["assignment_arrival_ms"] or
                t["commit_arrival_ms"]+1e-9<t["commit_send_ms"]):
            fail("audit_centralized_sequential_sender_phases","time",
                 "P2H_CENTRAL_NEXT_TASK_BEFORE_COMMIT",
                 "T(k+1) starts after prior Commit, each Commit after its Assignment",
                 {"pair":pair,"trace":t,"previous_commit_ms":previous})
        previous=float(t["commit_arrival_ms"])
    return ledger,phases,trace


def measure_p2h_full_info_task_order_quality(scene,pairs,native_complete):
    """Offline-only reference; never feed full-information Costs into native method."""
    reference=solve_visible_task_ordered_greedy_assignment(
        scene.cost_matrix,frozenset(range(scene.num_robots)),
    ).total_cost
    completed=bool(native_complete) and len(pairs)==scene.num_tasks
    if completed:
        total=sum(scene.cost_matrix[r][t] for r,t in pairs)
        return reference,total,100*(total/reference-1)
    return reference,"",""


def run_one_p2h_case(scene,profile,p_loss,mode,source_sha):
    """Pair one true native owner run with independent physical/state audits."""
    verify_one_scene(scene)
    if mode==MODES[0]:
        native,pairs=execute_original_sequential_voting(scene,profile,p_loss)
        attempts,epoch_commits=audit_one_pass_voting_epochs(scene,native,pairs)
        phases=audit_native_sender_phases(native,pairs,scene)
        stop=float(native["allocation_or_stop_ms"])
        total_sends=int(native["total_original_send_count"])
        total_bytes=int(native["total_sender_application_bytes"])
        complete=int(native["full_commit"])
        rounds=int(native["rounds_executed"])
        drops=int(native["cost_remote_packet_drop_count"])+int(
            native["vote_remote_packet_drop_count"])
        reason=("task_sequence_full_commit" if complete else "one_task_once_incomplete")
        ledger={"native":native,"sender_by_phase":phases}
        cost_sends=int(native["cost_sender_frames"])
        phase_key="cost"
        score_sends=int(native["vote_score_send_count"])
        vote_sends=int(native["vote_sender_frames"])
        assignment_sends=0
        commit_sends=int(native["commit_send_count"])
        task_sends=int(native["task_announcement_sender_frames"])
    elif mode==MODES[1]:
        native=run_one_centralized_case(
            scene,profile,p_loss,max_cost_rounds=1,
            planning_rule="task_ordered",assignment_scope="task_sequence",
        )
        pairs=tuple((int(r),int(t)) for r,t in json.loads(
            native["native_assignment_json"]))
        ledger,phases,trace=audit_centralized_sequential_sender_phases(
            native,pairs,scene,
        )
        attempts=tuple(range(scene.num_tasks))
        epoch_commits=tuple(tuple([pair]) for pair in pairs)
        stop=float(native["native_stop_ms"])
        total_sends=int(native["native_sender_sends"])
        total_bytes=int(native["native_sender_bytes"])
        complete=int(native["native_success"])
        rounds=scene.num_tasks
        drops=int(native["cost_receiver_drops"])
        reason=native["native_stop_reason"]
        cost_sends=int(native["cost_sender_sends"])
        phase_key="centralized_cost"
        vote_sends=0;score_sends=0
        assignment_sends=int(ledger["assignment_sender_frames"])
        commit_sends=int(ledger["commit_sender_frames"])
        task_sends=int(ledger["task_sender_frames"])
    else:
        fail("run_one_p2h_case","data","P2H_UNKNOWN_NATIVE_MODE",MODES,mode)
    if (len(pairs)!=len({r for r,t in pairs})
            or len(pairs)!=len({t for r,t in pairs})
            or complete!=int(len(pairs)==scene.num_tasks)
            or any(r<0 or r>=scene.num_robots or t<0 or t>=scene.num_tasks
                   for r,t in pairs)):
        fail("run_one_p2h_case","safety","P2H_INVALID_NATIVE_FULL_COMMIT",
             "capacity-one committed task/robot identities and accurate native success",
             {"pairs":pairs,"native_success":complete})
    reference,actual,gap=measure_p2h_full_info_task_order_quality(
        scene,pairs,complete,
    )
    return {
        "loss_percent":int(round(p_loss*100)),"seed":scene.seed,"mode":mode,
        "source_sha":source_sha,"scene_sha256":scene_sha256(scene),
        "robots":scene.num_robots,"tasks":scene.num_tasks,"capacity":1,
        "native_success":complete,"final_feasible":complete,
        "committed_task_count":len(pairs),"task_coverage":len(pairs)/scene.num_tasks,
        "rounds_executed":rounds,"native_stop_ms":stop,
        "native_sender_sends":total_sends,"native_sender_bytes":total_bytes,
        "task_sender_sends":task_sends,"cost_sender_sends":cost_sends,
        "cost_sender_bytes":int(phases[phase_key]["sender_bytes"]),
        "vote_sender_sends":vote_sends,"score_sender_sends":score_sends,
        "assignment_sender_sends":assignment_sends,
        "commit_sender_sends":commit_sends,
        "native_receiver_drops":drops,
        "full_info_reference_cost_m":reference,
        "final_total_distance_m":actual,"cost_increase_percent":gap,
        "quality_sample_eligible":int(actual!=""),"native_stop_reason":reason,
        "native_assignment_json":json.dumps(pairs,separators=(",",":")),
        "attempted_task_ids_json":json.dumps(attempts),
        "per_task_commits_json":json.dumps(epoch_commits),
        "original_traffic_ledger_json":json.dumps(ledger,default=str,sort_keys=True),
    }


def validate_p2h_complete_grid(rows,losses,first_seed,seeds):
    """One exact paired scene and two correct source-native method IDs."""
    expected=case_keys(losses,first_seed,seeds)
    observed=tuple((int(r["loss_percent"]),int(r["seed"]),r["mode"]) for r in rows)
    if observed!=expected:
        fail("validate_p2h_complete_grid","contract","P2H_NATIVE_GRID_MISSING",
             len(expected),{"rows":len(observed),"unique":len(set(observed))})
    for i in range(0,len(rows),len(MODES)):
        pair=rows[i:i+len(MODES)]
        if (len({r["scene_sha256"] for r in pair})!=1 or
                len({float(r["full_info_reference_cost_m"]) for r in pair})!=1):
            fail("validate_p2h_complete_grid","contract","P2H_UNPAIRED_REFERENCE",
                 "same source scene and full-info task-order Greedy",pair)


def validate_p2h_zero_loss(rows):
    """Both native executions MUST reach same fully visible ordered Greedy at PL0."""
    for row in rows:
        if int(row["loss_percent"])!=0:
            continue
        if (int(row["committed_task_count"])!=100 or
                not int(row["native_success"]) or
                row["cost_increase_percent"] in ("",None) or
                abs(float(row["cost_increase_percent"]))>1e-8):
            fail("validate_p2h_zero_loss","contract","P2H_ZERO_LOSS_NOT_GREEDY",
                 "100/100 Commit and 0 cost gap vs same-seed task-order Greedy",
                 {"seed":row["seed"],"mode":row["mode"],
                  "committed":row["committed_task_count"],
                  "gap":row["cost_increase_percent"]})


def summarize_p2h_native(rows,losses):
    """Unconditional time/Bytes/coverage; only successful complete-case costs."""
    result=[]
    for p in losses:
        for mode in MODES:
            cohort=[r for r in rows if int(r["loss_percent"])==p and r["mode"]==mode]
            if not cohort:
                fail("summarize_p2h_native","contract","P2H_EMPTY_NATIVE_COHORT",
                     (p,mode),"empty")
            complete=[r for r in cohort if int(r["native_success"]) and
                      int(r["final_feasible"])]
            n=len(cohort)
            quality=[float(r["cost_increase_percent"]) for r in complete
                     if r["cost_increase_percent"] not in ("",None)]
            if len(quality)!=len(complete):
                fail("summarize_p2h_native","contract",
                     "P2H_SUCCESS_COST_MISSING",len(complete),len(quality))
            result.append({
                "loss_percent":p,"method":mode,"trials":n,
                "native_complete":len(complete),
                "completion_rate_percent":100*len(complete)/n,
                "mean_task_coverage":sum(float(r["task_coverage"]) for r in cohort)/n,
                "quality_sample_count":len(quality),
                "cost_increase_percent":sum(quality)/len(quality) if quality else "",
                "mean_stop_s":sum(float(r["native_stop_ms"]) for r in cohort)/n/1000,
                "mean_sender_kb":sum(float(r["native_sender_bytes"]) for r in cohort)/n/1000,
                "mean_rounds_executed":sum(float(r["rounds_executed"]) for r in cohort)/n,
            })
    return result


def write_p2h_results(args,rows,losses,config,source_sha):
    """Only derived data/SVG/manifest after native grid and PL0 acceptance."""
    root=Path(args.output_root)
    summary=summarize_p2h_native(rows,losses)
    summary_csv=root/"summary_p2h.csv"
    write_csv(summary_csv,summary,fields=SUMMARY_FIELDS)
    outputs=[root/"run_config_p2h.json",root/"per_seed_p2h.csv",summary_csv]
    if args.formal:
        figure=root/"figure1_interactive_sequential.svg"
        figure.write_text(
            render_p2g_figure(summary,losses,"interactive"),encoding="utf-8",
        )
        outputs.append(figure)
    manifest={
        "study":"P2H_INTERACTIVE_SEQUENTIAL_TASK_VOTING_ONCE",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "source_sha":source_sha,"config":config,
        "native_cases":len(rows),"native_summary_groups":len(summary),
        "figure1_native_only":True,
        "figure2_notice":"P2G Figure2 remains original repeatable methods and is not rerun",
        "cost_quality_notice":"Only fully completed native capacity-one runs; missing is NOT 0",
        "traffic_notice":"Application sender physical SENDs include dropped Cost/Vote",
        "native_protocol_notice":"One Cost phase; T0 Vote+Score+Commit then retire; central T0 Assignment+Commit then T1; no retries",
        "sha256":{f.name:sha256_file(f) for f in outputs},
    }
    (root/"manifest_p2h.json").write_text(
        json.dumps(manifest,indent=2,ensure_ascii=False),encoding="utf-8",
    )
    return summary


def run_p2h(args):
    losses=validate_p2h_config(args)
    source_sha=read_source_sha()
    rady_path=ensure_rady_dataset(args.rady_json)
    profile=load_rady_latency_profile(rady_path)
    rows,config=prepare_p2h_evidence(
        args,source_sha,losses,sha256_file(rady_path),
    )
    expected=case_keys(losses,args.first_seed,args.seeds)
    raw=Path(args.output_root)/"per_seed_p2h.csv"
    with raw.open("a",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=RAW_FIELDS)
        for p,seed,mode in expected[len(rows):]:
            scene=generate_e0_scenario(seed,100,100)
            result=run_one_p2h_case(scene,profile,p/100.0,mode,source_sha)
            writer.writerow({k:result.get(k,"") for k in RAW_FIELDS})
            f.flush()
            os.fsync(f.fileno())
            rows.append(result)
            print(
                f"P2H PL={p}% seed={seed} mode={mode} "
                f"committed={result['committed_task_count']} "
                f"rounds={result['rounds_executed']} "
                f"bytes={result['native_sender_bytes']} "
                f"stop_ms={result['native_stop_ms']:.3f} "
                f"cost_increase={result['cost_increase_percent']}",flush=True,
            )
    validate_p2h_complete_grid(rows,losses,args.first_seed,args.seeds)
    validate_p2h_zero_loss(rows)
    summary=write_p2h_results(args,rows,losses,config,source_sha)
    print(f"P2H_COMPLETE cases={len(rows)} groups={len(summary)} "
          f"figure={int(bool(args.formal))} root={args.output_root}",flush=True)
    return summary


def parse_args(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--formal",action="store_true")
    p.add_argument("--losses",default=",".join(f"{v/100:.2f}" for v in LOSSES))
    p.add_argument("--seeds",type=int,default=2)
    p.add_argument("--first-seed",type=int,default=0)
    p.add_argument("--rady-json",type=Path,default=DEFAULT_RADY)
    p.add_argument("--output-root",type=Path,required=True)
    p.add_argument("--resume",action="store_true")
    return p.parse_args(argv)


def main(argv=None):
    run_p2h(parse_args(argv))


if __name__=="__main__":
    main()
