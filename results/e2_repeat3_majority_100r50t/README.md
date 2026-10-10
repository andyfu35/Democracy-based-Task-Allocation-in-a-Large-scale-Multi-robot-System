# E2 External Vote-Redundancy Control — 3 physical copies

**STATUS: NEW SOURCE COMMITTED; UNIT TESTS AND 100-SEED FORMAL RUN PENDING USER MAC EXECUTION. NO RESULTS CLAIMED.**

This is the **51%-strict majority + K=3 fixed open-loop remote Vote transmissions** control, using the original Greedy and the same 100R/50T geometry, one initial Cost broadcast, independent per-copy Bernoulli Vote Loss and 100 task-vote attempts. It sends each remote ballot exactly 3 times without ACK or early cancellation. A self-vote stays local, and each voter can contribute at most one counted logical Vote to the original candidate ledger.

It is NOT actual ARQ, CBBA, ACBBA, FEC or a published algorithm reproduction. Its only novelty relative to the historical 51%-majority experiment is an explicitly charged reliability control: redundant Vote packets at spacing phase_timeout_ms, extra bytes/messages, copy-specific packet loss, and a decision deadline after all scheduled copies. Initial Cost packets are NOT repeated or repaired. Qualified score and Commit channel reliability assumptions are preserved.

Run after tests + 3-seed smoke:

    git pull
    python3 -m unittest discover -s tests -v
    LEVELS="$(python3 -c 'print(",".join(f"{i/100:.2f}" for i in range(0, 71, 2)))')"
    python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities "$LEVELS" --loss-pairing diagonal --max-rounds 100 --vote-decision-rule strict_majority --vote-repetitions 3 --output-root results/e2_repeat3_majority_100r50t

Expected: 36 probability points × 100 seeds = 3,600 source simulations in this root, each with both p_cost_loss and p_vote_loss, original Greedy reference, exact vote_repetitions=3, original task/robot identity, physical per-copy transmitted events, delivery audit, drop counts, payload bytes, elapsed simulated coordination ms and source git SHA.

Compare with existing archived 51%-majority K=1 and pure 25%-announcement K=1:
- full assignment success rate, mean task Commit rate and Greedy matching executor rate;
- complete-case-only Greedy cost gap (NaN for incomplete batches);
- PHY Vote attempts and transmitted bytes; physical packet delivery attempt counts vs local logical self-votes;
- total coordination latency, duplicate safety failures and no invalid fallback event phases.
 
This is a first reliability CONTROL, not yet the final fair head-to-head against published CBAA/CBBA/ACBBA. The full proposal, physical copy accounting rules and references are in docs/EXPERIMENT_PROTOCOL.md §17. A clear subsequent change must implement CBAA/CBBA/ACBBA separately with faithful consensus state and lossy-message semantics.

**Evidence integrity:** do not overwrite or combine this result with historical 51%-majority K=1, pure 25% K=1 or the rejected 25% fallback. Keep all timestamped raw CSVs and formal summary.csv for analysis. Do not report any new rate without actually running this experiment on the Mac.
