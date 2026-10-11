# E9A — observed CBAA vs pure25 Greedy communication-budget calibration

**STATUS: code/tests/spec committed; E9A tests and matched-budget Mac experiments are NOT YET RUN.** Source history is immutable. Do not confuse this observational E9A report with true end-to-end capped-resource operation.

## Purpose

We completed genuine 100R/50T Greedy pure25 no-fallback and 51%-majority K1/K2/K3 100-seed 36-loss-point experiments. We then validated CBAA with 135/135 unit tests and 10R/5T + 100R/50T three-seed pilots at p=0,30,50%. But the pilot CBAA used 20 whole-vector broadcast iterations, i.e. 1,232,000 application send Bytes, not necessarily the same amount of communication as pure25 Greedy. E9A does not fabricate a CBAA failure by forcing K=1, nor take arbitrary 20 rounds as a controlled equivalent.

This study compares actual sender-payload bytes and success/observer agreement using exact paired seeds, sizes and nominal loss points. Read-only source of Greedy: results/e2_greedy_quarter_plurality_no_fallback_100r50t/raw/retirement_*.csv. CBAA source: the already existing results/e8_cbaa_100r50t_pilot/raw/cbaa_*.csv plus newly generated optional budgets K=1,2,3,4,5,8,10. No new Greedy simulations. The Greedy p0 mean SEND Bytes, and ONLY that number, picks the nearest CBAA K; zero-loss and higher-loss CBAA success never affect K selection. The report flags if closest budget deviates by >10%, and separately flags actual mismatch at each p, including counts of close same-seed pairs.

### First Mac preflight

    git pull
    python3 -m unittest discover -s tests -v
    python3 -m experiments.compare_cbaa_budget --cbaa-roots results/e8_cbaa_100r50t_pilot --output-root results/e9_cbaa_budget_calibration_20only

The initial single K=20 report is a schema/provenance preflight and is expected to be unmatched if byte counts differ. Do NOT overwrite that report root.

### Generate CBAA communication budget choices (ONLY 3 seeds)

    for K in 1 2 3 4 5 8 10; do
      python3 -m experiments.run_cbaa_baseline --robots 100 --tasks 50 --seeds 3 --loss-probabilities 0,0.30,0.50 --max-iterations "$K" --output-root "$(printf 'results/e8_cbaa_budget%s_100r50t_smoke' "$K")" || break
    done

### Calibrate all choices together (NEW output root)

    python3 -m experiments.compare_cbaa_budget --robots 100 --tasks 50 --seeds 3 --loss-probabilities 0,0.30,0.50 --tolerance 0.10 --cbaa-roots results/e8_cbaa_budget1_100r50t_smoke results/e8_cbaa_budget2_100r50t_smoke results/e8_cbaa_budget3_100r50t_smoke results/e8_cbaa_budget4_100r50t_smoke results/e8_cbaa_budget5_100r50t_smoke results/e8_cbaa_budget8_100r50t_smoke results/e8_cbaa_budget10_100r50t_smoke results/e8_cbaa_100r50t_pilot --output-root results/e9_cbaa_budget_calibration_3seed

Evidence files:
- budget_options.csv: each candidate CBAA K's p0 bytes vs pure25 p0 bytes; chosen K is selected BY BYTES ONLY, not by success or a high-loss point.
- budget_per_seed.csv: same seed/p, Greedy full Commit and task count vs CBAA post hoc observer full-agreement and task counts, separate packet/message/bytes/time metrics and source-informed mean ratio.
- budget_curve.csv: mean CBAA vs Greedy full agreement/Commit and actual sending costs for each K/p; number of seed-level near-byte pairs and observed mean-byte match.
- manifest.json: original CSV SHA256, original SHA/git revision, analysis revision, iteration budget set, tolerance and strong scientific limitations.

**Explicit limitations:** E9A does NOT impose a hard communication cap during either algorithm, does NOT compute hypothetical partial assignments from old complete E2 runs, does NOT equalize lossy Cost+Vote+reliable-Commit to CBAA bid consensus, and does NOT model Wi-Fi channel airtime/collision. A near SEND-Bytes match is only a preliminary calibration. A later E9B runtime task must stop physical transmission BEFORE exceeding a real shared byte budget and properly report failed/incomplete tasks. Do not claim equal-budget statistical superiority from these data. Full canonical protocol: docs/EXPERIMENT_PROTOCOL.md Section 19, internal change record: docs/CHANGE_CONTINUITY.md.
