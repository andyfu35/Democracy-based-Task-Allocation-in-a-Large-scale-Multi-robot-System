"""P2F: paired iterative Global Greedy batch-versus-sequential voting.

Both native arms may repeat decisions up to 300 epochs. Task Cost is
broadcast only once; physical SEND bytes include dropped recipient frames.
This is an isolated new-source comparison, not replacement of P2E evidence.
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
from democracy_mrta.network import ensure_rady_dataset, load_rady_latency_profile
from democracy_mrta.optimizer import solve_visible_batched_greedy_assignment
from democracy_mrta.scenario import generate_e0_scenario
from democracy_mrta.task_information import encode_task_announcement
from experiments.run_p1_matched_five import (
    DEFAULT_RADY, OUTPUT_FIELDS, read_source_sha, run_matched_case,
    scene_sha256, sha256_file, verify_one_scene, write_csv,
)
from experiments.run_p2_packet_loss import validate_batched_voting_evidence

OWNER = "experiments.run_p2f_redecision_comparison"
MODES = ("batch", "sequential")
ROUND_LIMITS = {"batch": 300, "sequential": 300}
LOSSES = tuple(range(0, 91, 10))
PHASES = ("task", "cost", "vote", "score", "commit")
EXTRA_FIELDS = (
    "committed_task_count", "task_coverage", "rounds_executed",
    "first_epoch_sha256", "full_info_greedy_cost_m",
    "quality_vs_full_info_greedy",
) + tuple(
    f"{phase}_sender_{unit}"
    for phase in PHASES for unit in ("sends", "bytes")
)
RAW_FIELDS = ("loss_percent", "mode", "max_rounds") + OUTPUT_FIELDS + EXTRA_FIELDS


def fail(function, category, code, expected=None, actual=None, details=""):
    raise ProtocolError(Diagnostic(
        owner=OWNER, function=function, category=category, code=code,
        expected=expected, actual=actual, details=details,
    ))


def validate_comparison_config(args: argparse.Namespace) -> tuple[int, ...]:
    """Freeze paired loss, seed and equal 300-epoch limits."""
    try:
        raw = tuple(float(x.strip()) for x in args.losses.split(","))
    except (ValueError, AttributeError, TypeError):
        fail("validate_comparison_config", "data", "P2F_INVALID_LOSS_GRID",
             "ascending subset of {0,0.1,..,0.9}", getattr(args,"losses",None))
    if not raw or any(not math.isfinite(x) for x in raw):
        fail("validate_comparison_config", "data", "P2F_INVALID_LOSS_GRID",
             "finite ascending subset of {0,0.1,..,0.9}", raw)
    losses = tuple(round(x*100) for x in raw)
    if (not losses or losses != tuple(sorted(set(losses)))
            or any(p not in LOSSES or not math.isfinite(x)
                   or abs(p/100-x)>1e-12 for p,x in zip(losses,raw))):
        fail("validate_comparison_config", "data", "P2F_INVALID_LOSS_GRID",
             LOSSES, raw)
    if (type(args.seeds) is not int or type(args.first_seed) is not int
            or not 1<=args.seeds<=100 or args.first_seed<0
            or args.seeds+args.first_seed>100):
        fail("validate_comparison_config", "data", "P2F_INVALID_SEED_RANGE",
             "1..100 seeds within original seed 0..99",
             (args.first_seed,args.seeds))
    if args.formal and (losses!=LOSSES or args.seeds!=100 or args.first_seed!=0):
        fail("validate_comparison_config", "contract", "P2F_FORMAL_CONFIG_CHANGED",
             (LOSSES,0,100),(losses,args.first_seed,args.seeds))
    return losses


def case_keys(losses, first_seed, seeds):
    return tuple(
        (loss, seed, mode) for loss in losses
        for seed in range(first_seed,first_seed+seeds) for mode in MODES
    )


def prepare_comparison_evidence(args, source_sha, losses):
    """Append only; resume cannot change source/config nor corrupt order."""
    root=Path(args.output_root)
    config={
        "study":"P2F_BATCH_VS_SEQUENTIAL_GLOBAL_GREEDY",
        "source_sha":source_sha,"method":"voting","voting_strategy":"greedy_batch","vote_scope_by_mode":{"batch":"all","sequential":"one_task"},
        "modes":MODES,"round_limits":ROUND_LIMITS,
        "robots":100,"tasks":100,"capacity":1,
        "loss_percent":losses,"first_seed":args.first_seed,
        "seeds":args.seeds,"formal":bool(args.formal),
        "rady_json":str(Path(args.rady_json).expanduser().resolve()),
        "sender_bytes_definition":"sum physically emitted application SEND payload, including dropped",
    }
    cfg=root/"run_config_p2f.json"
    raw=root/"per_seed_p2f.csv"
    if not args.resume:
        if root.exists():
            fail("prepare_comparison_evidence","state","P2F_OUTPUT_EXISTS",
                 "new unique result directory",str(root))
        root.mkdir(parents=True)
        cfg.write_text(json.dumps(config,indent=2),encoding="utf-8")
        with raw.open("x",newline="",encoding="utf-8") as file:
            csv.DictWriter(file,fieldnames=RAW_FIELDS).writeheader()
        return [],config
    if (not cfg.is_file() or not raw.is_file()
            or (root/"manifest_p2f.json").exists()):
        fail("prepare_comparison_evidence","state","P2F_INVALID_RESUME_ROOT",
             "incomplete compatible P2F evidence",str(root))
    old=json.loads(cfg.read_text(encoding="utf-8"))
    if old != json.loads(json.dumps(config)):
        fail("prepare_comparison_evidence","contract","P2F_RESUME_CONFIG_CHANGED",
             old,config)
    with raw.open(newline="",encoding="utf-8") as file:
        reader=csv.DictReader(file)
        if tuple(reader.fieldnames or ())!=RAW_FIELDS:
            fail("prepare_comparison_evidence","contract","P2F_RESUME_COLUMNS_CHANGED",
                 RAW_FIELDS,reader.fieldnames)
        records=list(reader)
    expected=case_keys(losses,args.first_seed,args.seeds)
    current=tuple((int(r["loss_percent"]),int(r["seed"]),r["mode"])
                  for r in records)
    if current!=expected[:len(current)]:
        fail("prepare_comparison_evidence","contract","P2F_RESUME_PREFIX_CHANGED",
             expected[:len(current)],current)
    for r in records:
        if (int(r["max_rounds"])!=ROUND_LIMITS[r["mode"]]
                or r["scene_sha256"]!=scene_sha256(
                    generate_e0_scenario(int(r["seed"]),100,100))
                or int(r["robots"])!=100 or int(r["tasks"])!=100
                or int(r["capacity"])!=1):
            fail("prepare_comparison_evidence","contract","P2F_RESUME_CASE_CHANGED",
                 "same scene, capacity, round limit and dimensions",r)
    return records,config


def extract_validated_native_batch(scene, native, max_rounds):
    """Check original native Cost and epoch contract without replacing it."""
    if native["native_diagnostic"]:
        # P1 archives the *first* native owner Diagnostic when a native run
        # fails. Propagate that owner/function/category/code unchanged.
        try:
            original=json.loads(native["native_diagnostic"])
            diagnostic=Diagnostic(**original)
        except (ValueError,TypeError,KeyError) as error:
            fail("extract_validated_native_batch","data",
                 "P2F_MALFORMED_NATIVE_DIAGNOSTIC",
                 "original Diagnostic JSON",str(error))
        raise ProtocolError(diagnostic)
    try:
        batch=json.loads(native["original_traffic_ledger_json"])["batch"]
        rounds=int(batch["rounds_executed"])
        timed_rounds=int(batch["phase_timing"]["epochs"])
        task_frames=int(batch["task_announcement_sender_frames"])
        cost_frames=int(batch["cost_sender_frames"])
    except (KeyError,TypeError,ValueError,json.JSONDecodeError) as error:
        fail("extract_validated_native_batch","data",
             "P2F_MISSING_NATIVE_BATCH_EVIDENCE",
             "verified original native Vote/Score/Commit trace",str(error))
    if (not 1<=rounds<=max_rounds or rounds!=timed_rounds
            or not batch.get("first_epoch_sha256")):
        fail("extract_validated_native_batch","contract",
             "P2F_INVALID_ORIGINAL_EPOCH",
             (1,max_rounds,"matching native timing and fingerprint"),
             (rounds,timed_rounds,batch.get("first_epoch_sha256")))
    expected_task_frames=len(encode_task_announcement(scene.task_positions))
    if (task_frames!=expected_task_frames
            or cost_frames!=scene.num_robots):
        fail("extract_validated_native_batch","contract",
             "P2F_COST_ONCE_CONTRACT",
             (expected_task_frames,scene.num_robots),
             (task_frames,cost_frames))
    return batch,rounds


def count_observed_commits(native):
    """Safety-audit native Commit-backed observer pairs, including partial."""
    try:
        physical_pairs=tuple((int(r),int(t))
                             for r,t in json.loads(native["native_assignment_json"]))
    except (KeyError,TypeError,ValueError,json.JSONDecodeError) as error:
        fail("count_observed_commits","data","P2F_INVALID_NATIVE_PAIRS",
             "serialized physical robot/task pairs",str(error))
    if (len(physical_pairs)!=len({r for r,_ in physical_pairs})
            or len(physical_pairs)!=len({t for _,t in physical_pairs})):
        fail("count_observed_commits","safety","P2F_DUPLICATE_NATIVE_COMMIT",
             "one robot and one task per physical pair",physical_pairs)
    return physical_pairs


def audit_native_sender_phases(native, phase_sender):
    """Independently reconcile every physical SEND, not receiver delivery."""
    details={}
    for phase in PHASES:
        sending=phase_sender.get(phase)
        if sending is None:
            fail("audit_native_sender_phases","contract",
                 "P2F_MISSING_NATIVE_SENDER_PHASE",PHASES,tuple(phase_sender))
        for unit in ("sends","bytes"):
            name=f"{phase}_sender_{unit}"
            details[name]=int(sending[f"sender_{unit}"])
            if details[name]<0:
                fail("audit_native_sender_phases","data",
                     "P2F_NEGATIVE_SENDER_TRAFFIC",">=0",
                     {"phase":phase,"unit":unit,"value":details[name]})
    actual=(sum(details[f"{p}_sender_sends"] for p in PHASES),
            sum(details[f"{p}_sender_bytes"] for p in PHASES))
    expected=(int(native["native_sender_sends"]),
              int(native["native_sender_bytes"]))
    if actual!=expected:
        fail("audit_native_sender_phases","contract",
             "P2F_SENDER_LEDGER_MISMATCH",expected,actual)
    return details


def measure_comparison_offline_quality(scene, native, p_loss):
    """Read-only full-information Greedy cost; never fed into native Voting."""
    full_greedy=solve_visible_batched_greedy_assignment(
        scene.cost_matrix, frozenset(range(scene.num_robots)),
    )
    quality=(
        float(native["final_total_distance_m"])/full_greedy.total_cost
        if int(native["native_success"]) and int(native["final_feasible"])
        else ""
    )
    return full_greedy.total_cost,quality


def run_one_comparison_case(
    scene, profile, p_loss: float, max_rounds: int, batch_vote_scope: str = "all",
) -> dict:
    """Use original E9H/P1 Voting owner; only the epoch cap differs."""
    if batch_vote_scope not in ("all", "one_task"):
        fail("run_one_comparison_case","data","P2F_INVALID_VOTE_SCOPE",
             ("all","one_task"),batch_vote_scope)
    if max_rounds != 300:
        fail("run_one_comparison_case","data","P2F_INVALID_ROUND_LIMIT",300,max_rounds)
    verify_one_scene(scene)
    mode="batch" if batch_vote_scope=="all" else "sequential"
    native=run_matched_case(
        scene, profile, "voting", p_loss, 160, max_rounds,
        voting_strategy="greedy_batch", batch_vote_scope=batch_vote_scope,
    )
    batch,rounds=extract_validated_native_batch(scene,native,max_rounds)
    pairs=count_observed_commits(native)
    details=audit_native_sender_phases(native,batch["sender_by_phase"])
    greedy_cost,quality=measure_comparison_offline_quality(scene,native,p_loss)
    return {
        "loss_percent":int(round(p_loss*100)),
        "mode":mode,"max_rounds":max_rounds,
        **native,
        "committed_task_count":len(pairs),
        "task_coverage":len(pairs)/scene.num_tasks,
        "rounds_executed":rounds,
        "first_epoch_sha256":batch["first_epoch_sha256"],
        "full_info_greedy_cost_m":greedy_cost,
        "quality_vs_full_info_greedy":quality,
        **details,
    }


def validate_comparison_grid(rows, losses, first_seed, seeds):
    """Strict exact two-arm paired cells, source geometry and send arithmetic."""
    keys=case_keys(losses,first_seed,seeds)
    actual=tuple((int(r["loss_percent"]),int(r["seed"]),r["mode"])
                 for r in rows)
    if actual!=keys:
        fail("validate_comparison_grid","contract","P2F_INCOMPLETE_GRID",
             len(keys),{"rows":len(actual),"unique":len(set(actual))})
    for row in rows:
        mode=row["mode"]
        if (int(row["max_rounds"])!=ROUND_LIMITS[mode]
                or int(row["rounds_executed"])>ROUND_LIMITS[mode]):
            fail("validate_comparison_grid","contract","P2F_ROUND_LIMIT_MISMATCH",
                 ROUND_LIMITS[mode],row.get("rounds_executed"))
        actual_sends=sum(int(row[f"{p}_sender_sends"]) for p in PHASES)
        actual_bytes=sum(int(row[f"{p}_sender_bytes"]) for p in PHASES)
        if (str(actual_sends)!=str(row["native_sender_sends"])
                or str(actual_bytes)!=str(row["native_sender_bytes"])):
            fail("validate_comparison_grid","contract","P2F_SENDER_LEDGER_MISMATCH",
                 (row["native_sender_sends"],row["native_sender_bytes"]),
                 (actual_sends,actual_bytes))
        if (float(row["task_coverage"])<0 or float(row["task_coverage"])>1
                or abs(float(row["task_coverage"])*100
                       -float(row["committed_task_count"]))>1e-9):
            # Formal grid is 100R/100T; 5R smoke exercises run_one only.
            fail("validate_comparison_grid","contract","P2F_INVALID_TASK_COVERAGE",
                 "committed_task_count / 100",
                 (row["task_coverage"],row["committed_task_count"]))


def validate_paired_scenes_and_cost(rows, losses, first_seed, seeds):
    """Paired methods share scene and full one-time Cost SEND count.

    Vote/Score/Commit fingerprints differ by design; do not demand identical
    initial voting traces or claim identical received Cost loss without source audit.
    """
    by_key={(int(r["loss_percent"]),int(r["seed"]),r["mode"]):r for r in rows}
    for loss in losses:
        for seed in range(first_seed,first_seed+seeds):
            a=by_key.get((loss,seed,"batch"))
            b=by_key.get((loss,seed,"sequential"))
            if a is None or b is None or a["scene_sha256"] != b["scene_sha256"]:
                fail("validate_paired_scenes_and_cost","contract",
                     "P2F_UNPAIRED_SCENE",(loss,seed,"matching native scene"),(a,b))
            for row in (a,b):
                if int(row["cost_sender_sends"]) != int(row["robots"]):
                    fail("validate_paired_scenes_and_cost","contract",
                         "P2F_COST_ONCE_CONTRACT",int(row["robots"]),
                         row["cost_sender_sends"])


def summarize_comparison(rows, losses):
    """All-seed exposure vs success-only quality; never zero-impute failures."""
    result=[]
    for loss in losses:
        for mode in MODES:
            cohort=[r for r in rows
                    if int(r["loss_percent"])==loss and r["mode"]==mode]
            complete=[r for r in cohort
                      if int(r["native_success"]) and int(r["final_feasible"])]
            def mean_metric(field, subset=cohort):
                values=[float(r[field]) for r in subset
                        if r.get(field) not in ("",None)]
                return (sum(values)/len(values) if values and
                        len(values)==len(subset) else "")
            quality=[float(r["quality_vs_full_info_greedy"]) for r in complete
                     if r["quality_vs_full_info_greedy"] not in ("",None)]
            n=len(cohort)
            grouped={
                "loss_percent":loss,"mode":mode,"max_rounds":ROUND_LIMITS[mode],
                "trials":n,"native_complete":len(complete),
                "completion_rate":len(complete)/n if n else "",
                "mean_task_coverage":mean_metric("task_coverage"),
                "mean_rounds_executed":mean_metric("rounds_executed"),
                "mean_all_seed_native_stop_ms":mean_metric("native_stop_ms"),
                "mean_all_seed_sender_bytes":mean_metric("native_sender_bytes"),
                "quality_sample_count":len(quality),
                "mean_success_quality":sum(quality)/len(quality) if quality else "",
            }
            for p in PHASES:
                for u in ("sends","bytes"):
                    name=f"{p}_sender_{u}"
                    grouped[f"mean_{name}"]=mean_metric(name)
            result.append(grouped)
    return result


def write_comparison_results(args, rows, config, source_sha, losses):
    root=Path(args.output_root)
    summary=summarize_comparison(rows,losses)
    summary_path=root/"summary_p2f.csv"
    write_csv(summary_path,summary)
    figure=root/"p2f_comparison_summary.json"
    figure.write_text(json.dumps(summary,indent=2),encoding="utf-8")
    source_files=[root/"run_config_p2f.json",root/"per_seed_p2f.csv",
                  summary_path,figure]
    manifest={
        "study":"P2F_BATCH_VS_SEQUENTIAL_GLOBAL_GREEDY_NEW_NATIVE",
        "source_sha":source_sha,
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "config":config,
        "executions":len(rows),
        "summary_groups":len(summary),
        "method_count":2,
        "phase_sender_bytes":"physically emitted SEND payload, including losses",
        "paired_by":"seed, loss, scene SHA and one-time sender Cost count; vote traces intentionally differ",
        "bounds":"capacity 1, independent Bernoulli Cost/Vote loss, reliable TASK/Score/Commit, hypothetical 144 Mbps Rady timing; not observed RF",
        "sha256":{p.name:sha256_file(p) for p in source_files},
    }
    (root/"manifest_p2f.json").write_text(
        json.dumps(manifest,indent=2),encoding="utf-8",
    )
    return summary


def run_comparison(args):
    losses=validate_comparison_config(args)
    source_sha=read_source_sha()
    profile=load_rady_latency_profile(ensure_rady_dataset(args.rady_json))
    rows,config=prepare_comparison_evidence(args,source_sha,losses)
    expected=case_keys(losses,args.first_seed,args.seeds)
    dest=Path(args.output_root)/"per_seed_p2f.csv"
    with dest.open("a",newline="",encoding="utf-8") as file:
        writer=csv.DictWriter(file,fieldnames=RAW_FIELDS)
        for loss,seed,mode in expected[len(rows):]:
            scene=generate_e0_scenario(seed,100,100)
            row=run_one_comparison_case(
                scene,profile,loss/100,ROUND_LIMITS[mode],
                batch_vote_scope=("all" if mode=="batch" else "one_task"),
            )
            writer.writerow({f:row.get(f,"") for f in RAW_FIELDS})
            file.flush()
            os.fsync(file.fileno())
            rows.append(row)
            print(
                f"P2F PL={loss}% seed={seed} mode={mode} "
                f"committed={row['committed_task_count']} "
                f"rounds={row['rounds_executed']} "
                f"bytes={row['native_sender_bytes']} "
                f"stop_ms={row['native_stop_ms']:.3f}",flush=True,
            )
    validate_comparison_grid(rows,losses,args.first_seed,args.seeds)
    validate_paired_scenes_and_cost(rows,losses,args.first_seed,args.seeds)
    summary=write_comparison_results(args,rows,config,source_sha,losses)
    print(f"P2F_COMPLETE cases={len(rows)} groups={len(summary)} root={args.output_root}",
          flush=True)
    return summary


def parse_args(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal",action="store_true")
    parser.add_argument("--losses",default=",".join(f"{p/100:.2f}" for p in LOSSES))
    parser.add_argument("--seeds",type=int,default=2)
    parser.add_argument("--first-seed",type=int,default=0)
    parser.add_argument("--rady-json",type=Path,default=DEFAULT_RADY)
    parser.add_argument("--output-root",type=Path,required=True)
    parser.add_argument("--resume",action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    run_comparison(parse_args(argv))


if __name__=="__main__":
    main()
