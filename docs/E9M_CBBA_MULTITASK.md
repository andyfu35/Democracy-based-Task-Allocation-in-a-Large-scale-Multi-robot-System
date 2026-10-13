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
