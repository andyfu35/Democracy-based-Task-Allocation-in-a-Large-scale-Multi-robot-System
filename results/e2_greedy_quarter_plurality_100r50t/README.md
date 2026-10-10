# 100R / 50T Greedy Quarter-Plurality + Fallback Benchmark

Status: **NEW CODE COMMITTED. LOCAL REGRESSIONS AND FORMAL 100-SEED RESULTS PENDING.**

## Comparison design

This is the alternate decision rule to compare with the previously completed 51-vote strict-majority Greedy:
- Robots: 100. Tasks: 50. Seeds: 0..99 (100 paired seeds).
- Loss probability: p_cost_loss = p_vote_loss = p, independently sampled per physical Cost/Vote packet.
- p: 0.00 .. 0.70 at intervals of 0.02; 36 levels, 3,600 seed-condition simulations.
- Voting attempts max 100; each attempt selects one pending task via lowest visible active Cost.
- Reliable task announcement, reliable score/fallback announcements, reliable commit; cost rows shared once.
- Existing completed majority baseline: `results/e2_joint_loss_diagonal_100r50t/summary.csv`.
- New separate evidence root: `results/e2_greedy_quarter_plurality_100r50t/`.

## 25-percent rule

At N currently eligible robots, the announcement threshold is `floor(N / 4) + 1`.
Each candidate that meets this strict threshold after the vote window reliably announces its own FINAL tally. The highest counted score is selected; ties go to the lowest original robot ID. All see reliable announcements before one commit.

If no candidate qualifies, all active robots send reliable provisional `fallback_self_claim` announcements with their own received vote counts (including zero) and the same winner comparison produces exactly one commit. This is the safety-preserving formalization of 'no one announces => self-declared win': **no candidate may physically execute a private self-claim before winner reconciliation**.

At high loss this fallback may assign a task even without meaningful vote support. Therefore always compare **qualified announcement Commit vs fallback Commit**, along with cost and traffic. A high Full Assignment Success alone does not establish packet-loss robustness.

## Acceptance sequence

```bash
git pull
python3 -m unittest discover -s tests -v

# 3-seed smoke, three loss points, 9 seed-conditions
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 3 --cost-loss-probabilities 0,0.30,0.70 --loss-pairing diagonal --max-rounds 100 --vote-decision-rule quarter_plurality_fallback --output-root results/e2_greedy_quarter_plurality_smoke

# Formal 100-seed, 36-point diagonal sweep
LEVELS="$(python3 -c 'print(",".join(f"{i/100:.2f}" for i in range(0, 71, 2)))')"
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities "$LEVELS" --loss-pairing diagonal --max-rounds 100 --vote-decision-rule quarter_plurality_fallback --output-root results/e2_greedy_quarter_plurality_100r50t
```

## Required result inspection

`summary.csv`:
- method / vote_decision_rule and both equal numeric packet loss probabilities
- final task commit rate; all-50-task success rate; greedy correctness; Hungarian correctness
- global/Greedy cost gap only on fully completed task sets
- mean qualified score announcements, mean fallback self-claims, mean fallback committed tasks / fraction
- mean winning counted votes, number of plurality tie breaks
- mean rounds, elapsed coordination time, messages, payload bytes
- actual observed remote Vote Loss (excluding self-votes), and Cost Loss

`rounds/retirement_rounds_*.csv`:
- original robot IDs; attempted task, eligibility changes
- effective 25% announcement threshold; `quorum=0` indicating **strict-majority quorum is disabled** in this mode
- counts of qualified/fallback announcements; fallback flag, winner tally, tie flag

`events/retirement_audit_*.csv.gz`:
- each reliable `vote_score_announcement` and `fallback_self_claim` has a `announced_vote_count` field
- one reliable `commit` per task, no duplicated robot/task assignment
- all Cost/Vote delivery observations remain independent and traceable by round

## Known limitations

- Newly added score/self-claim announcements are reliable; Cost/Vote transmissions are lossy. This added reliable channel may bypass the measured packet-loss bottleneck. **Do not infer that the physical system could work at 100% packet loss.**
- Candidate announcements are assumed truthful; adversarial forged scores are out of scope.
- Stale Cost rows, real physical execution, packet loss on task/commit/claim announcements, and radio contention are not modeled.
- If actual self-claims executed immediately with no unique-winner arbitration, duplicate task execution is possible. This experiment deliberately prevents that unsafe behavior.
- Report communication overhead and cost degradation rather than focusing solely on Full Assignment Success.

The previous baseline and all old output roots remain unchanged. This ledger records the newly created code and test plan only; it does not claim a completed new measurement.
