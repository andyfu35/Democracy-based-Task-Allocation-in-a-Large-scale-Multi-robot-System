# E9M: Genuine multi-task CBBA versus Voting

Status as of 2026-10-13: **IMPLEMENTATION CANDIDATE COMMITTED; MAC NATIVE INTEGRATION NOT YET VERIFIED.** Run the in-repository tests and 3-seed smoke locally first. No CI. No formal E9M data exists yet.

Reference: Choi / Brunet / How (2009), Consensus-Based Decentralized Auctions for Robust Task Allocation, IEEE T-RO, DOI 10.1109/TRO.2009.2022423, MIT CBBA project https://acl.mit.edu/projects/consensus-based-bundle-algorithm. CBBA is multi-task bundle/path and original winner/bid/timestamp consensus, not four independent CBAA votes.

## Preregistered first cell

25 Robots, 100 Tasks, maximum capacity 4 tasks per robot, world 100m x 100m, 100 paired seeds 0..99. Same scenario and objective for both algorithms; 0% loss smoke before 30% receiver loss formal. N=T from E9I/J/L is NOT a valid old numerical baseline for T=4R. E9K paid CBAA is a team-authored protocol change and NEVER participates as an algorithm.

Same path-dependent score for all methods: sum per visited task of 100 * 0.999 ** traveled_distance_until_this_task_in_meters. Robot speed 1m/s, task service 0, open task routes, actual best insertion position. The values 100 and 0.999 are benchmark assumptions, not literature-prescribed parameters. Evaluate task coverage, unique task assignment, capacity, path route distance, max route duration, discounted reward, native application SEND/Bytes, model elapsed allocation, local certificates, observer agreement and round safety guard, with failed seeds included.

CBBA: maintain independent bundle-build order and execution path, greedy best path insertion, full winner + bid + freshness timestamps, faithful Choi 2009 multi-task conflict-resolution decision table and reset full dependent bundle suffix on losing a task. Native consensus repeats naturally. Real serialized packets <=1200B, fragment larger peer snapshots and accept only complete matching-round physical packets. p=0.30 independent per receiver for native CBBA consensus; reliable external Task announcement.

Voting Multi-task: explicitly our capacity-aware Voting extension, never claim this was old published one-task Voting unchanged. Each task epoch has dynamic best insertion Cost, physically received Cost/Vote under p=.30 independently, plurality of received votes, reliable physically charged Score and Commit and consistent capacity/path updates. Tasks and robots start from the same seed scene and 100/0.999 reward. Both algorithms must never silently assign tasks via an omniscient simulated observer.

Transport uses sampled Rady ROS residual and assumed E9G 144Mbps shared medium only. Packet lengths and actual original SEND count must be charged. This is NOT ns-3 or real Wi-Fi. CBBA optimistic observer stopping cannot be equated with Voting reliable Commit; record separately. Fixed max rounds160 is a safety guard, not imposed K rounds. If E9M p30 does not converge, count guard failures instead of retuning the archived method.

Original repo true owners scenario.generate_e0_scenario and optimizer.validate_cost_matrix reject tasks>robots; preserve them unchanged. New true owners: democracy_mrta.multitask_scenario, democracy_mrta.cbba_multitask, democracy_mrta.voting_multitask, democracy_mrta.multitask_evaluation, and experiments.run_e9m_multitask; extend existing network timing owner only if truly necessary. Every substantive owner change MUST update docs/CHANGE_CONTINUITY.md in the same commit, and canonical §48 when scope/spec changes.

## Mac start: pull and test E9M source

From the voting repository root:

    git fetch origin experiment/e9m-cbba-multitask
    git switch experiment/e9m-cbba-multitask
    git pull --ff-only
    git status --short

Run these native owner tests and smoke commands locally before the formal 100 seeds:

    python3 -m pip install -r requirements.txt
    python3 -m compileall -q democracy_mrta experiments tests
    python3 -m unittest discover -s tests -p 'test_e9m_*.py' -v

    python3 -m experiments.run_e9m_multitask --robots 25 --tasks 100 --capacity 4 --seeds 3 --loss 0.0 --max-rounds 160 --methods voting_multitask,cbba --output-root "results/e9m_zero_loss_smoke_$(date +%Y%m%d_%H%M%S)"

    python3 -m experiments.run_e9m_multitask --robots 25 --tasks 100 --capacity 4 --seeds 3 --loss 0.30 --max-rounds 160 --methods voting_multitask,cbba --output-root "results/e9m_loss30_smoke_$(date +%Y%m%d_%H%M%S)"

Full paired 100seed run only if the above tests and smoke PASS, without hiding any failed/guard-censored seeds:

    set -o pipefail
    export E9M_ROOT="results/e9m_25r100t_loss30_100seed_$(date +%Y%m%d_%H%M%S)"
    python3 -m experiments.run_e9m_multitask --robots 25 --tasks 100 --capacity 4 --seeds 100 --loss 0.30 --max-rounds 160 --methods voting_multitask,cbba --output-root "$E9M_ROOT" 2>&1 | tee "$E9M_ROOT.log"
    zip -r "$HOME/Downloads/e9m_25r100t_loss30_100seed.zip" "$E9M_ROOT" "$E9M_ROOT.log"

Expected user-run files after implementation: per_seed_e9m.csv, summary_e9m.csv, manifest.json with executed Git SHA, config/seed, original raw SHA, start-time/OS/Python, all methods and exact per-class packet counts. Reject existing output directories and invalid contracts; do not copy old E9I/E9J/E9K/E9L one-task results into this experiment. 10R40T, 50R200T, 100R400T remain future scaling cells, not the first experiment.


## Transport correction after preliminary Mac 100-seed smoke (2026-10-13)

First executed source f347e26 ran 100/100 for each method and logged full task coverage, but source audit found Voting remote ballots were broadcast and local self ballots were incorrectly SEND-charged. Those original log/CSV/manifest outputs must be preserved unchanged for audit, **not used as final communication/time baseline**. Corrected source: remote Vote unicast (candidate only); local self-vote zero physical sender packet; Cost, Score and Commit remain unchanged broadcasts. Run local `test_e9m_*.py`, loss0 3-seed and loss30 3-seed again after git pull, then rerun formal loss30 100 seeds in a fresh directory. Prior f347e26 remains traceable by commit SHA. Do not overlay the old output root or use the old ZIP as corrected evidence.


## One combined five-algorithm comparison figure (E9I/J/L + E9M)

New bounded source-verified **presentation-only** owner: `experiments.plot_e9m_unified_comparison`. Do not rerun E9I/J/L just to plot: use the existing published immutable 20-point original three-algorithm CSV and a **NEW corrected** E9M 100-seed output root. The figure includes five algorithms on ONE SVG, arranged into two clearly different workloads:

- **A: legacy N=T, capacity1:** E9I Voting, E9J original CBAA, E9L distributed Price Auction. All-seed modeled time and sender Bytes vs N=5..100; available E9L per-size completion counts; E9I/J per-N completion is omitted when unsupported by plotted source.
- **B: E9M R=25/T=100, capacity4:** voting_multitask and CBBA, 100 paired Seeds. Modeled time, sender Bytes, completion rates. Quality metrics (total distance, makespan, discounted reward) remain in the original raw and in the new chart's verified source summary; they are NOT plotted as comparable to legacy Hungarian-relative one-task Cost.

No cross-family absolute speed ranking or single joint best method. All protocol endpoints and modeled radio limitations remain explicit. The original old E9M `f347e26` execution is **not accepted**: source must be descendant of commit `638081b9c040cde5a796a4de83fc3b025fe10b48` (Vote unicast and free local ballots). The presentation verifies original E9L Git-blob identity, E9M raw/summary SHA256s, manifest/preregistered R25T100 C4 p30, every seed0..99 and method exactly once, raw per-phase network ledgers and complete task routes on successful records. Existing source files are never modified.

After Git pull, run these in the Mac repository root **ONLY after the corrected formal 100-seed E9M run is complete**:

```bash
# Set the exact successful corrected result directory; do NOT use old f347e26.
E9M_ROOT="results/e9m_fixed_25r100t_loss30_100seed_<YOUR_TIMESTAMP>"

PLOT_ROOT="results/e9m_unified_$(date +%Y%m%d_%H%M%S)"
python3 -m unittest discover -s tests -p 'test_e9m_unified_comparison.py' -v

python3 -m experiments.plot_e9m_unified_comparison \
  --e9m-root "$E9M_ROOT" \
  --output-root "$PLOT_ROOT"

zip -r "$HOME/Downloads/e9m_unified_evidence.zip" "$E9M_ROOT" "$PLOT_ROOT"
```

This writes one source-attested `unified_method_time_bytes_success.svg`, one `unified_method_comparison_source.csv` with 5 rows and cohort boundaries, and one SHA provenance `unified_method_manifest.json`. Keep old original ZIPs. Send this ZIP back for source audit; **only then** replace the existing E9L main time/Bytes image with the unified chart in README (keep total README plots small). No CI.
