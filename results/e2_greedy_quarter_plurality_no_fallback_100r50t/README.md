# E2 Greedy 25% Qualified Plurality — NO fallback

**Status: NEW SOURCE / TESTS COMMITTED; NO LOCAL NO-FALLBACK TEST OR FORMAL SWEEP YET CONFIRMED.**

This is the ONLY current intended new experiment for pure quarter-plurality voting:
- Greedy, sequential task-by-task assignment with robot retirement only after Commit.
- Strict threshold: more than 25% of ALL still-active voters (100 robots -> at least 26 received ballots).
- Multiple qualified candidates publish final vote tallies (reliable score announcements), highest tally wins, original ID breaks ties, unique reliable Commit.
- **No qualifying candidate: no announcement, no commit, no executor retired; move pending task to queue tail and try the next task with fresh vote packet sampling.**
- **Zero extra fallback/self-claim messages**. Do not assign a task solely to keep coverage artificially high.
- The one-time incomplete Cost-row snapshot never gets repaired during the run.

## Formal experiment

100 Robots × 50 Tasks, 100 paired seeds, 36 loss levels 0%..70% every 2%, p_cost_loss=p_vote_loss (numerically equal, independent physical packet sampling), maximum 100 individual task-voting attempts, Rady Wi-Fi latency sampling, unchanged task order and Greedy cost rule. Final 3,600 runs generate summary.csv, timestamped raw per-seed rows, per-round membership/threshold/attempt audit, and seed-0 message/delivery record.

Baseline controls, preserved:
- strict majority: results/e2_joint_loss_diagonal_100r50t (previous formal result);
- rejected fallback experiment: results/e2_greedy_quarter_plurality_100r50t (archived; NEVER use its 100% full success as pure plurality performance).

## Execution (Mac repository root)

    git pull
    python3 -m unittest discover -s tests -v

    python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 3 --cost-loss-probabilities 0,0.30,0.70 --loss-pairing diagonal --max-rounds 100 --vote-decision-rule quarter_plurality --output-root results/e2_greedy_quarter_plurality_no_fallback_smoke

    LEVELS="$(python3 -c 'print(",".join(f"{i/100:.2f}" for i in range(0, 71, 2)))')"
    python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities "$LEVELS" --loss-pairing diagonal --max-rounds 100 --vote-decision-rule quarter_plurality --output-root results/e2_greedy_quarter_plurality_no_fallback_100r50t

## Evidence and acceptance

- Every new output row has vote_decision_rule=quarter_plurality, git SHA, seed, Cost and Vote loss values. The CLI prints 36 conditions and 3600 seed-conditions.
- At zero loss, all tasks should commit and match the full-information sequential Greedy reference (not necessarily global Hungarian).
- If no candidate qualifies, qualified announcement count=0, no commit, and the task stays pending. The per-round CSV reports no_qualified_announcement=1 and increments the attempt count. The new summary reports mean_no_qualified_announcement_attempts/rate rather than any fallback fields.
- Every actual received qualified announcement contains candidate's own announced_vote_count, and the final winner must have the highest count (ties original ID); one unique Commit.
- At sufficiently high loss, task commit and full-assignment success are allowed to DECREASE; do not force completion.
- Only report total-cost gap when ALL tasks commit; incomplete runs have NaN gap.
- Verify actual Cost and Vote drop rates separately, and count self-votes only as local votes (not network transmissions).
- Track mean rounds, elapsed simulated coordination time, message count/bytes and ties alongside success.
- Result roots for completed majority / archived rejected fallback remain untouched.

## Limitations

Reliable qualified score and final Commit announcements are still modeling assumptions; a future experiment should test announcement loss separately. There is no real task execution, robot return, MAC contention, burst packet loss, or Cost update. A no-qualified timeout is not a safety violation and is an expected result at high loss.

Canonical rules: docs/EXPERIMENT_PROTOCOL.md Section 14. Continuity and first failing diagnostic boundaries: docs/CHANGE_CONTINUITY.md.
