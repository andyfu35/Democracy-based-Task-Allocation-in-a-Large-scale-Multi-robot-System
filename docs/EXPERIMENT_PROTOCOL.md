# Canonical Experiment Protocol

## 1. Research question

The paper studies a **leaderless fully decentralized communication and agreement protocol for multi-robot task allocation under unreliable wireless communication**.

The paper does **not** claim a new optimizer.

## 2. Fixed optimizer

All primary controlled methods use the same deterministic Hungarian implementation.

The allocation problem for one epoch is a static linear one-to-one assignment problem:

\[
X^*=\arg\min_X\sum_i\sum_j c_{ij}x_{ij}
\]

with

\[
\sum_jx_{ij}\le1,\qquad \sum_ix_{ij}=1.
\]

With a complete identical matrix and deterministic ordering/tie handling, every robot must compute the same optimal assignment.

## 3. Democracy protocol

For each allocation round:

1. the allocation epoch/task set is reliably disseminated;
2. each robot computes its own cost row;
3. each robot broadcasts its cost row once to the peer set;
4. robot \(i\) constructs local matrix \(\hat C_i\);
5. unknown/unreceived entries are explicitly represented as unavailable and never silently replaced by ground-truth data;
6. robot \(i\) runs Hungarian on its local feasible matrix;
7. each local assignment becomes one task-level vote per proposed robot;
8. votes are sent directly as unicasts to proposed executors;
9. task \(j\) commits to robot \(k\) only when robot \(k\) receives strict majority
   \[
   Q=\lfloor N/2\rfloor+1;
   \]
10. after quorum, the winner broadcasts one commit announcement for that task;
11. votes are unique by voter/task/round;
12. stale votes are rejected;
13. if the required assignment cannot be committed before timeout, the round fails and is retried.

## 4. Zero-loss correctness contract

At zero packet loss with complete information:

\[
\hat C_1=\hat C_2=\cdots=\hat C_N=C.
\]

Therefore:

\[
X_1=X_2=\cdots=X_N=X^*
\]

must hold.

Any nonzero optimality gap in this condition is a **contract failure**, not a performance result.

The earlier sequential per-task minimum-cost implementation is obsolete and is not the canonical paper algorithm.

## 5. Timing model

Primary empirical latency source:

M. Rady et al., “How does Wi-Fi 6 fare? An industrial outdoor robotic scenario,” Ad Hoc Networks 156, 103418, 2024, DOI 10.1016/j.adhoc.2024.103418.

The authors publish real ROS 2 application-delay observations. Their processed dataset exposes `control_delay_ms` and `control_loss` across locations and PHY configurations.

E1 pins the external evidence to:

- repository: `minarady1/wifi_for_industrial_robotics`
- commit: `1996e5bb69b9ba4d25060cbc14838ddedf65cff2`
- JSON Git blob: `11e70e685229cc26458f272b0c954487c87d7953`
- location 2: Medium range LoS (60 m)
- configuration: `ax_160mhz_6ghz` (Wi-Fi 6E ax/6/160)
- steady-state interval: 120–181 s

This pinned profile contains 121 finite ROS control-delay samples in the steady-state interval. The verified descriptive values are mean 33.593687 ms, P50 19.962509 ms, P95 64.149866 ms, P99 159.419021 ms, and maximum 531.535123 ms.

For controlled latency experiments, each successfully delivered protocol message receives an empirical latency sample:

\[
L_m\sim Bootstrap(D_{WiFi6}).
\]

Arrival:

\[
t_{arrival}=t_{send}+L_m.
\]

Packet-loss sweeps are injected independently from latency unless an experiment explicitly runs real trace replay.

## 6. Event-time accounting

The simulator must be discrete-event.

Do not estimate communication time as message count times mean latency.

Required timing boundaries:

- cost exchange start/end;
- local optimization start/end;
- vote send / arrival;
- quorum achieved time;
- commit send / arrival;
- timeout;
- retry start;
- final decision time.

For Democracy voting, quorum time is the arrival time of the Q-th valid vote.

Per run:

\[
T_{total}=T_{compute}+T_{communication}+T_{retry}.
\]

## 7. Primary controlled methods

- Ideal Full Information — reference.
- Leader-Hungarian.
- Flooding/Full-View Hungarian.
- Democracy-Hungarian — ours.

CBAA/ACBBA/DHBA are Related Work and possible secondary cross-method comparisons, not primary controlled baselines.

## 8. Formal experiment sequence

- E0: perfect-information correctness.
- E1: empirical Wi-Fi communication-time cost.
- E2: Bernoulli packet-loss robustness.
- E3: robot scalability.
- E4: task-load saturation.
- E5: Gilbert-Elliott burst loss.
- E6: message-type failure localization.
- E7: published real Wi-Fi trace replay.

## 9. Diagnostics

Allowed categories:

`data / time / state / dependency / planning / safety / runtime / contract`.

Timing-model failures belong to owner `network` / category `time` or `data` as appropriate.

Optimizer-input incompleteness must be explicit; missing costs must never be silently filled from ground truth.

## 10. Reproducibility

Every formal run stores:

- code commit SHA;
- source network dataset provenance and pinned revision;
- selected location / PHY profile;
- scenario seed;
- network sampling/replay seed;
- per-seed aggregate metrics;
- aggregate summary;
- raw per-message network event logs for designated audit seeds.

The full event stream is deterministic from the network seed and message key. Formal E1 defaults to preserving audit event logs for seed 0 while retaining aggregate metrics for all 100 seeds.


## 11. E1 zero-loss coordination timing semantics

E1 isolates latency cost; packet loss is disabled.

Primary methods:

1. **Ideal Full Information**: no network communication; reference only.
2. **Leader-Hungarian**: every non-leader unicasts one cost-row message to robot 0; the leader solves Hungarian and emits one logical wireless assignment broadcast.
3. **Full-View Hungarian**: every robot emits one logical wireless cost-row broadcast. At zero loss, every peer receives each broadcast and obtains a complete matrix.
4. **Democracy-Hungarian**: uses the same one-broadcast-per-robot cost exchange as Full-View in E1, then each robot independently forms the identical Hungarian proposal, sends task votes as direct unicasts to proposed executors, and each task winner emits one logical wireless commit broadcast after strict-majority quorum.

All network messages are concurrent discrete events. A phase completes from actual simulated arrival events, never from message count multiplied by mean latency.

For E1, one logical broadcast is counted as **one attempted wireless transmission and one payload copy**, not \(N-1\) unicasts. Because E1 has zero packet loss, one broadcast uses one trace-derived application-delay sample and becomes visible to all intended peers at that simulated arrival time. Receiver-specific loss/delivery semantics are intentionally deferred to E2.

For Democracy-Hungarian:

- robot \(i\)'s local matrix becomes ready after all required peer cost broadcasts have arrived;
- a self-vote is a zero-latency local event and is not counted as a network message;
- task quorum time is the arrival time of the \(Q\)-th valid vote;
- actionable decision time is the maximum task quorum time;
- global agreement time is the final required commit arrival.

E1 reports hardware-dependent Hungarian wall-clock time separately from trace-driven network waiting time; it does not serialize the computation of different robots, because robots are physically separate compute nodes.

The E1 empirical model does not claim to simulate additional fleet-size-dependent 802.11 MAC contention. That limitation must remain explicit. E3 may add a separately justified contention sensitivity model; no contention penalty may be invented silently.


## 12. E2 Bernoulli packet-loss semantics

E2 isolates **single-round packet-loss robustness**. It does not evaluate retry policy.

Loss sweep:

`p_loss ∈ {0, 0.1, 0.3, 0.5, 0.7, 0.9}`

The same pinned empirical latency profile as E1 is used for all successfully delivered transmissions.

### 12.1 Cost dissemination

Each robot always knows its own cost row.

Each logical cost-row broadcast is one attempted wireless transmission. For every peer receiver, delivery is sampled independently with Bernoulli probability:

`P(drop) = p_loss`

A dropped row remains absent from that receiver's local view. It must never be reconstructed, imputed, or copied from the ground-truth matrix.

If all expected peer rows arrive, a local view becomes ready at the final required arrival time. If one or more expected rows are missing, the receiver closes its cost phase at the fixed E2 phase timeout.

The phase timeout is the maximum measured delay in the pinned E1 profile:

`T_phase = 531.535123 ms`

This makes `p_loss = 0` timing-compatible with E1 while giving receivers a deterministic boundary at which absence becomes observable.

### 12.2 Partial local Hungarian optimization

For Democracy-Hungarian and Leader-Hungarian, the Hungarian optimizer receives only the robot rows visible to that decision maker.

If `K` robot rows are visible for `M` tasks, the local optimizer returns exactly

`min(K, M)`

one-to-one assignment pairs.

When `K < M`, the proposal is partial. No synthetic cost is inserted for hidden robots.

A Democracy voter casts votes only for the task pairs present in its own partial assignment. Tasks omitted by that local assignment are abstentions from that voter.

### 12.3 Voting and quorum

Votes are direct unicasts to proposed executors and use the same Bernoulli packet-loss probability `p_loss`.

The quorum denominator never shrinks with packet reception:

`Q = floor(N / 2) + 1`

A task commits only if one candidate receives at least `Q` distinct valid delivered votes.

No-quorum is an expected E2 outcome and produces a task timeout rather than an exception.

### 12.4 Commit reliability

Commit broadcasts remain reliable in E2.

This is intentional: cost loss and vote loss are the independent variables in E2. Commit loss can create duplicate-execution safety hazards and is therefore isolated for the later message-type failure experiment.

### 12.5 Controlled-method behavior

- **Ideal Full Information**: unaffected reference.
- **Leader-Hungarian**: the leader optimizes over its self row plus cost rows actually received. A partial leader assignment is allowed.
- **Full-View Hungarian**: succeeds only if every robot receives a complete matrix in that round. Otherwise the full-view coordination round times out.
- **Democracy-Hungarian**: every robot optimizes its own visible rows, casts votes from that partial proposal, and relies on strict-majority aggregation.

### 12.6 E2 metrics

Primary metrics:

- task commit rate;
- **correct executor rate (CER)**, defined as oracle-matching committed tasks divided by total tasks;
- **correctness among committed tasks**, defined as oracle-matching committed tasks divided by committed tasks;
- full-assignment success rate;
- optimal-solution rate;
- optimality gap among full successful assignments;
- task timeout rate;
- decision completion time;
- global agreement time;
- logical transmission count;
- logical payload bytes;
- lossy delivery opportunities / delivered / dropped;
- mean visible robot rows;
- safety failures.

Retry count is fixed to zero in E2.

### 12.7 Correctness boundaries

At `p_loss = 0`:

- all methods must have task commit rate 1;
- all methods must have full-assignment success 1;
- all methods must have zero optimality gap;
- Democracy timing/message behavior must reduce to the E1 zero-loss implementation.

At every loss level:

- quorum denominator remains fixed at `N`;
- no duplicate robot/task commit is permitted;
- safety failures must remain zero.

E2 assumes independent receiver-level Bernoulli delivery. Correlated burst loss is not modeled here; that is reserved for E5.


### 12.8 Correct-executor metrics

Let the deterministic complete-information Hungarian oracle assign task (j) to robot (r_j^*).

For an evaluated method, if task (j) is committed to robot (hat r_j), that commit is correct iff:

[
hat r_j = r_j^*.
]

The **Correct Executor Rate (CER)** is:

[
CER = rac{#{	ext{correct committed tasks}}}{N_T}.
]

This metric penalizes both wrong commits and uncommitted tasks.

The conditional **correctness among committed tasks** is:

[
C_{commit}
=
rac{#{	ext{correct committed tasks}}}
{#{	ext{committed tasks}}}.
]

If no task is committed, (C_{commit}) is undefined and is reported as NaN.

These metrics are required for E2 because full-assignment success alone can hide assignment-quality degradation. A method may assign every task while selecting executors that differ substantially from the complete-information Hungarian oracle.


## 12.9 E2 vote provenance and forensic acceptance gate

The formal 100-seed E2 result is **under audit**, not yet paper-accepted.
The observed 100R/50T at p_cost=p_vote=0.30 has:
- mean visible cost rows = 70.285 of 100;
- task commit rate = 0.1522;
- correct executor rate = 0.1506;
- correctness among committed = 0.98706.

These aggregate values do not determine the fraction of raw ballots matching the full-information Hungarian oracle, or whether quorum failure was caused by proposal disagreement versus vote transport loss.

The forensic audit must reuse **the same coordination state machine and same keyed network samplers**, not an independently reimplemented vote collector. It captures read-only:
- local visible robot rows by voter;
- actual local Hungarian proposal by voter, including non-network self-votes;
- final counted task/candidate vote ledger.

The audit checks that:
1. each voter local view equals its delivered cost rows plus its own row;
2. each proposed non-self vote has exactly one unicast delivery observation;
3. reconstructed delivered+self-votes equal the actual protocol counted ledgers;
4. majority reconstruction equals committed task winners;
5. audit capture does not alter protocol events, decisions, or timing.

Required outputs:
- per-voter visible-row count and raw/delivered oracle-matching ballots;
- per-task raw oracle support and raw top-candidate support;
- per-task delivered oracle support and delivered top-candidate support;
- per-task candidate raw/delivered vote counts;
- rates for (a) no majority before vote loss, (b) majority lost during vote transport, and (c) majority actually committed.

The independent Bernoulli cost/vote losses are unchanged. Cost loss of 30% does NOT imply exactly 30% incorrect local Hungarian proposals.

Audit command:

    python3 -m experiments.audit_e2_votes --robots 100 --tasks 50 --p-loss 0.3 --seeds 100

The change is instrumentation-only. Until the audit and its regression tests pass, E2's 30%-loss robustness claim is not considered validated.

The selected forensic seed also exports individual ballots, one row per voter/task
proposal: voter_id, task_id, candidate_id, oracle_robot, oracle_match,
local_visible_rows, is_self_vote, transport_delivered, transport_dropped.
This ballot table includes local self-votes that were not present in the previous
network-only event log. The output is audit evidence, not a second vote ledger.


## 12.10 Controlled E2 cost-information-loss sweep

The E2 loss sampler continues to use distinct deterministic Bernoulli packet keys for cost-row reception and vote transport.

To isolate **local-information loss**, vary the probability of *receiving a peer cost row* while fixing the vote-packet delivery loss to zero:

- `p_cost_loss = p` independently for each sender-to-receiver cost-row delivery, with each robot always retaining its own row;
- `p_vote_loss = 0` for each remote vote;
- reliable task announcement and commit as before;
- unchanged partial-row Hungarian, strict majority and no retry.

The `experiments.run_e2` CLI option `--loss-probabilities` still controls the cost-delivery loss sweep. New optional `--vote-loss-probability VALUE` fixes Democracy's vote-transport packet loss independently for the entire sweep.

**Backward-compatibility contract:** if `--vote-loss-probability` is omitted, Democracy keeps the prior `p_vote_loss = p_cost_loss` for each point. When set to `0`, cost loss alone is tested. Leader/Full-View methods do not transmit Democracy votes, so this vote override does not change their behavior.

The legacy raw/summary/events field `p_loss` identifies cost loss. The additional `p_vote_loss` field records the effective vote loss at each point, including the original default two-stage experiment. Audit and per-seed event records continue to be paired by the same seeds. Use a distinct `--output-root` for this ablation to avoid replacing formal E2 summaries.

Suggested initial analysis: fixed 100 robots / 50 tasks, 100 paired scenario/network seeds, cost loss 0% to 70% at 2-percentage-point increments, vote loss fixed 0%. Report task commit, CER and all-tasks global-optimal solution rates separately. A claimed `unusable` transition requires a stated operational criterion; for inspection one may report the first sampled loss level where task commit falls below 90%, 50% and 10%, without treating those as predefined success standards.

This sweep remains single-round and does not quantify eventual completion under retries.


## 13. Sequential Greedy voting with executor retirement (new opt-in experiment)

**Scope:** This protocol replaces Hungarian **in the new retiring-executor experiment only**. Existing E0/E1/E2 single-round Hungarian experiments and their historical results remain unchanged. The previous `simulate_democracy_hungarian_retirement` strategy remains accessible for backwards compatibility when explicitly called with `voting_strategy="hungarian"`, but the `experiments.run_e2_retirement` runner now always selects `voting_strategy="greedy_task"` and reports `democracy_greedy_retirement`.

### 13.1 Data exchange happens exactly once

For an initial N-robot, T-task static cost matrix, each robot keeps its own row and broadcasts **its complete T-task cost row once**. Each peer independently receives or loses that message with Bernoulli Cost Loss `p_cost_loss`. The result is one voter-specific local visible-robot-row set. Unknown rows remain unknown for the entire allocation run, never imputed from global truth and never retransmitted or resampled in later voting rounds.

Later rounds filter these persistent views to remove robots that have already committed; every voter still retains its own active row. These **static** views are appropriate to the present static-cost experiment. Dynamic robot locations, stale costs, or cost changes would require a separately defined refresh policy.

### 13.2 Greedy vote for ONE task per epoch

Maintain:
- `A_k`: frozen set of active, unassigned robot IDs at epoch k;
- `P_k`: ordered queue of uncommitted task IDs;
- `C_k`: already committed one-to-one assignments;
- an epoch ID (strictly increasing).

For the head task `t=P_k[0]`, each active robot i independently votes for:

    candidate(i,t) = argmin [ (cost[r,t], original_robot_id[r]) ]
                     over r in (i's visible rows intersection A_k)

Each voter always sees its own row, so at least one candidate exists. This greedy selection **does not call Hungarian** and **does not optimize or reserve other tasks**. Equal costs use the lowest original robot ID. It is an O(number-of-visible-active-robots) local scan per task.

Each voter casts **one** task-specific vote to its chosen executor. A self-vote is local and does not use wireless transmission; other votes are direct unicasts whose delivery is separately sampled by Bernoulli Vote Loss `p_vote_loss`.

The current epoch's strict majority is frozen:

    Q_k = floor(|A_k| / 2) + 1

The candidate receives the task only when at least Q_k distinct valid votes arrive. Duplicate, ineligible and stale votes continue to be rejected by the original `protocol.record_vote`; the existing `find_unique_majority` still resolves exactly one winner.

### 13.3 Commit, exit, and failed-task queue

Upon quorum, the winning executor broadcasts a **reliable commit announcement** before the next epoch. The committed task is removed from P, and the committed robot is removed from both the voter and candidate sets. It is treated as busy executing and does not participate again in this allocation run. The next task is then selected from the remaining queue, with a new Q based on the smaller active electorate.

If no candidate achieves quorum before the timeout, **no robot is retired**. The failed task moves from the queue head to its tail, and the next epoch votes on the next queued task. With only one task left, the task stays at the head for retry. New epoch IDs ensure vote transmissions and latency have distinct keyed samples. **Cost rows are not retransmitted**; only new votes can be retransmitted, and changed membership may alter the selection.

Both cases transition through the single existing owner `protocol.apply_announced_retirement_commits`, now with optional `attempted_task_id` for task-queue rotation. All voting remains in the single existing `coordination.simulate_democracy_hungarian_lossy` owner with `voting_strategy="greedy_task"`, rather than a second majority collector.

A fixed max-round limit counts **task-voting attempts, not entire 50-task allocation passes**. At least T rounds are needed to commit T tasks without any failures. For 100R/50T use `max_rounds=100` initially (50 tasks + up to 50 failed attempts) and separately report cost and failure rates. No unlimited retry.

### 13.4 Stable original identities and time

Robot/task physical IDs never change when compact active matrices shrink. Proposal IDs, packet loss keys, vote ledgers and final assignments use original IDs. A reliable commit is completed before the next round starts, and the current round's voter count is fixed until then.

The initial whole-row cost exchange follows the same original 0th-epoch E2 loss and latency keys, now with a payload sized for **all tasks**. Subsequent epochs have **no cost exchange**. Vote/commit keys include each new epoch ID; round-zero legacy keys are unchanged.

The simulator sums round-relative quorum/timeout/commit event times into elapsed assignment decision time. It **does not** simulate physical robot task motion, task-execution duration, robot rejoining, packet loss on commits, or MAC contention.

### 13.5 Comparisons, metrics, and correctness

The experiment saves a separate result family:

- method: `democracy_greedy_retirement`;
- raw rows with code SHA, seed, T, N, cost/vote loss and max-rounds;
- per-round active population, queue, attempted task, quorum, commit and time;
- a designated seed-0 per-message and per-delivery log;
- final summary by paired seeds and loss.

Two offline references MUST be kept distinct:

1. **Full-information sequential Greedy reference** (same ascending task order and no drop). Used to measure `greedy_correct_executor_rate`, `greedy_gap_percent_successful`. Zero-loss greedy voting must reproduce this reference.
2. **Full-information Hungarian global optimum** (evaluation oracle only; **never used for voter decisions**). Used to measure the legacy CER, `optimal_solution_rate`, and `optimality_gap_percent_successful`.

At zero loss, full task coverage and 100% match to the sequential Greedy reference are expected, but **zero global Hungarian gap is NOT expected or required**. An irreversible Greedy sequence can have much higher total cost than global Hungarian.

Only if all tasks commit do total-cost gaps have a valid same-task-set denominator. For incomplete allocations, report task commit rate, Greedy-reference correctness, Hungarian-reference CER, and rounds/time/message cost; the partial cost sum is not a global optimality gap.

With sequential Greedy, `first_task_vote_success` measures only the first attempted task; it MUST NOT be labeled as the original E2 full-set first-round task commit rate. Comparing an end-to-end multi-round success rate with single-round E2 directly is an **intervention comparison**, not a like-for-like one-round packet-loss robustness claim.

### 13.6 Commands and initial acceptance

```bash
git pull
python3 -m unittest discover -s tests -v
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 3 --cost-loss-probabilities 0,0.3,0.5 --vote-loss-probability 0 --max-rounds 100 --output-root results/e2_greedy_retirement_smoke
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --vote-loss-probability 0 --max-rounds 100 --output-root results/e2_greedy_retirement_100r50t
```

The formal sweep defaults to Cost Loss 0%–70% in 2-point increments; Vote Loss fixed at 0%. The old E2 output roots remain untouched. New results are NOT paper-accepted until all local tests and the first smoke establish correct voter exit, task-order rotation, stable physical IDs, no duplicate commits, no repeated cost broadcasts, and correct Greedy-vs-global-cost metrics.



### 13.7 Full Vote Loss benchmark (independent channel sensitivity)

Formal extension to the same sequential Greedy + committed-executor retirement **without changing the protocol**. Each active voter selects one cheapest visible active candidate for one pending task. The vote is a direct unicast and its loss probability may differ from the single initial cost-row exchange loss probability.

- Cost-row delivery: independent per sender/receiver, with probability p_cost_loss; each robot retains its own row.
- Vote unicast delivery: independent packet event with probability p_vote_loss. **Self-votes have no wireless transport and cannot be dropped by this parameter.**
- Reliable commit announcements and strict-majority voting over all currently unassigned/active robots are unchanged.
- A new task-voting epoch retries with distinct round keys; no cost-row rebroadcast or ground-truth imputation is permitted.
- Failed tasks move to the pending queue tail, and a successful executor retires before the next round.
- Max 100 **task-voting attempts** for 100R/50T; partial allocations remain partial and cost gaps must be NaN unless all tasks commit.

All curves use 100 robots, 50 tasks and the **same 100 scenario and network seeds**. Loss levels for line curves are 0.00–0.70 in steps of 0.02 (36 points). Required independent experiments:

| Identifier | p_cost_loss | p_vote_loss | Question | Output root |
|---|---|---|---|---|
| COST_ONLY (existing) | sweep 0–70% | fixed 0 | Fragility of voters' incomplete cost information | results/e2_greedy_retirement_100r50t |
| VOTE_ONLY | fixed 0 | sweep 0–70% | Pure vote-channel packet loss under consistent cost views | results/e2_vote_only_100r50t |
| COST30_VOTE_SWEEP | fixed 30% | sweep 0–70% | Additional vote loss under the previously selected 30% cost-row loss | results/e2_cost30_vote_sweep_100r50t |
| JOINT_DIAGONAL | sweep 0–70% | equal numeric percentage to cost loss at each point | Joint end-to-end sensitivity; cost/vote packet draws still independent | results/e2_joint_loss_diagonal_100r50t |

For a coarse **two-dimensional interaction surface**, optionally also run a full grid with each probability in {0.0,0.1,0.2,0.3,0.4,0.5,0.6,0.7}: 8*8 = 64 cells, 100 seeds each, in results/e2_joint_loss_grid_100r50t. This optional grid measures interactions; do not accidentally substitute a 36*36 full-factorial sweep (129,600 seed-condition simulations) without an explicit compute and storage budget.

The experiment CLI supports:
- `--vote-loss-probability 0.3`: existing fixed Vote Loss behavior (unchanged);
- `--vote-loss-probabilities 0,0.02,...`: NEW Vote Loss axis independent of the Cost Loss axis (mutually exclusive with fixed Vote Loss);
- `--loss-pairing grid`: Cartesian product of the two loss axes (default; also used for a single fixed cost level);
- `--loss-pairing diagonal`: one pair for each loss level, **requiring exactly identical cost and vote axes**. Without a Vote Loss axis the implementation uses the Cost Loss axis automatically; a simultaneous fixed Vote Loss is rejected.
- Missing axes, duplicate pairs, invalid probabilities and mismatched diagonal axes MUST fail with explicit diagnostic codes before running simulations.

Outputs continue to include `p_cost_loss` and `p_vote_loss` separately on raw/round/event and summary rows; the raw rows include paired seed, git SHA, timestamp, and the method `democracy_greedy_retirement`. Additionally report:
- `cost_packet_attempts`, `cost_packet_dropped`, `observed_cost_drop_rate` for actual cost deliveries in the initial epoch;
- `remote_vote_attempts`, `remote_vote_dropped`, `observed_vote_drop_rate`, `self_votes` for actual vote packets, excluding self-votes from the wireless Vote Loss denominator;
- `quorum_failed_attempts`, mean rounds/elapsed time, final task commit rate and full 50-task success rate;
- Greedy-oracle executor correctness, global Hungarian-oracle executor correctness, and **complete-assignment only** cost gap to both full-information references.

In aggregate summaries, observed packet-loss rate is **the number of dropped packets divided by attempted packets across all seeds at that condition** (not an unweighted average of per-seed loss rates). Cost and Vote Loss counts plus delivery counts must reconcile exactly with the underlying coordination observations, otherwise fail with a diagnostic.

The core figure should show `mean_task_commit_rate`, `full_assignment_success_rate`, `mean_greedy_correct_executor_rate` versus `p_vote_loss` separately for VOTE_ONLY and COST30_VOTE_SWEEP, plus a JOINT_DIAGONAL curve. Plot mean rounds, mean elapsed time, and vote drop audit as separate supporting panels. Do not label Hungarian-based CER as Greedy reference accuracy.

Do NOT conclude "30% loss is safe" from a Vote Loss-only curve with 0% Cost Loss, or from task commit rate alone. Under 100 voting attempts there is a material difference between a single task reaching quorum and all 50 tasks completing. The user must inspect full-task success and cost among completed runs.

All tests for these new sweep parameters and stage delivery accounting must pass before claiming the formal Vote Loss results were validated. The earlier 62-unit-test pass and Cost-only 100-seed scan occurred **before** this new experiment-axis code change.

### 13.8 Vote Loss reproducibility commands

After pulling and running unit tests, begin with a 3-seed two-axis smoke (cost 0/30%, vote 0/30/70%); then run three separated 100-seed sweeps:

```bash
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 3 --cost-loss-probabilities 0,0.30 --vote-loss-probabilities 0,0.30,0.70 --max-rounds 100 --output-root results/e2_vote_loss_smoke

LEVELS="$(python3 -c 'print(",".join(f"{i/100:.2f}" for i in range(0, 71, 2)))')"
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities 0 --vote-loss-probabilities "$LEVELS" --max-rounds 100 --output-root results/e2_vote_only_100r50t
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities 0.30 --vote-loss-probabilities "$LEVELS" --max-rounds 100 --output-root results/e2_cost30_vote_sweep_100r50t
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities "$LEVELS" --loss-pairing diagonal --max-rounds 100 --output-root results/e2_joint_loss_diagonal_100r50t
```

Optional 8x8 grid:

```bash
GRID="0,0.10,0.20,0.30,0.40,0.50,0.60,0.70"
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities "$GRID" --vote-loss-probabilities "$GRID" --max-rounds 100 --output-root results/e2_joint_loss_grid_100r50t
```

Separate output roots are REQUIRED to prevent overwriting the prior 100-seed Cost-only evidence and to preserve condition-specific summary.csv files. The experiment prints condition count before running, which must equal 6 for smoke, 36 for each line sweep, and 64 for the optional interaction grid.


## 14. E2 Greedy 25%-Announcement Plurality — NO fallback

### 14.1 User-authorized decision rule

The sole new voting mode is quarter_plurality. The former quarter_plurality_fallback was **removed at the user's explicit request on 2026-10-10**. A programmatic request for the removed rule must fail at coordination.validate_vote_decision_rule / contract / REMOVED_PLURALITY_FALLBACK_RULE, never silently alias to another algorithm. Historical fallback results remain archived and cannot be used as evidence of the new no-fallback algorithm.

For each task, use a **frozen** active electorate A of N currently unassigned robots. Each robot independently chooses the least-cost active executor in its own retained local Cost view. Every voter casts a single task ballot, with Vote Loss affecting only remote unicasts; its own ballot is local and reliable. Cost rows were broadcast only once and are not refreshed.

A candidate can reliably announce its actual FINAL counted votes only when its count is STRICTLY greater than 25% of the full eligible electorate:

    announcement_threshold = floor(N/4) + 1

Examples: N=100 requires 26 votes; N=99 requires 25 votes; N=4 requires 2; N=2 requires 1. The denominator is never the number of delivered votes. Recalculate the threshold only between completed task-voting epochs, after successful committed executors retire.

At the existing vote-collection deadline, each qualified candidate broadcasts its own final score with original robot/task IDs and round ID. Qualified score announcements (and subsequent commit announcements) are reliable in this simulator, and their message count, bytes and latency are charged. Everyone selects highest announced score, ties resolved by smallest original robot ID. ONE selected executor commits and is removed from future voter/candidate sets. Other robots remain eligible.

### 14.2 If nobody exceeds 25%, nobody wins

**No fallback, self-claim, self-election, provisional victory, or alternate selection is allowed.** With zero qualified candidates:
- zero score announcements and zero commit broadcasts for that task;
- zero executors retire, and the task is NOT assigned;
- the existing protocol.apply_announced_retirement_commits state owner rotates the failed task to the tail of the pending queue;
- the next task-voting attempt has a new round ID and new independent Vote Loss packet samples but unchanged incomplete Cost rows;
- if max_rounds is reached, all remaining tasks are explicitly incomplete.

This is a normal failed vote attempt, not a safety exception. protocol.resolve_unique_plurality_claims returns None for empty qualified announcements. coordination.simulate_quarter_plurality_announcement_phase then returns no event and no winner. The same coordination.simulate_democracy_hungarian_lossy owner handles the resulting task timeout; no second vote collector or new state machine is created.

In a tiny active electorate (e.g. two robots), one self-vote can genuinely satisfy the strict 25% threshold. That is a qualified announcement, NOT a fallback. The rule does not guarantee minimum global assignment cost even with zero packet loss.

### 14.3 Owners and first-failure contract

- protocol.quarter_vote_announcement_threshold: validates electorate size; computes strictly-greater-than-25% integer threshold.
- protocol.resolve_unique_plurality_claims: validates original robot IDs, vote counts, uniqueness and threshold, then uniquely resolves announced candidates or returns None.
- coordination.validate_vote_decision_rule: accepts strict_majority (unchanged default) or quarter_plurality for a single Greedy task; rejects removed quarter_plurality_fallback with REMOVED_PLURALITY_FALLBACK_RULE.
- coordination.build_quarter_plurality_claims: reads only counted candidate-local ledgers and returns ZERO or more qualified announcements.
- coordination.simulate_quarter_plurality_announcement_phase: broadcasts ONLY qualified score announcements after vote collection; if none qualify, emits no message or commit.
- coordination.simulate_democracy_hungarian_lossy: unchanged owner of vote transport/ledgers, now correctly treats an absent plurality result as a noncommit timeout. Original strict-majority behavior remains its default.
- protocol.apply_announced_retirement_commits: single owner of task rotation and successfully committed robot retirement, unchanged.
- coordination.simulate_democracy_hungarian_retirement: bounded round scheduler and stable physical IDs. New method name is democracy_greedy_quarter_plurality_retirement.
- experiments.run_e2_retirement.retirement_plurality_diagnostics: reports qualified-announcement/commit counts, **no-qualified attempts** and winner scores. Missing qualified announcements MUST match a failed attempt (PLURALITY_ANNOUNCEMENT_COMMIT_MISMATCH, category contract). No fallback metrics/transport phase exist in the new schema.

Reliable score announcements remain an explicit assumption and are not exposed to Cost/Vote Loss. It must not be claimed that the system tolerates loss of these control messages, which would require its own protocol.

### 14.4 Paired formal no-fallback experiment

Historical evidence MUST remain unchanged:
- strict-majority Greedy: results/e2_joint_loss_diagonal_100r50t;
- the now-rejected fallback-based experiment: results/e2_greedy_quarter_plurality_100r50t.

New no-fallback output root: results/e2_greedy_quarter_plurality_no_fallback_100r50t.

Run with 100 Robots / 50 Tasks, seeds 0..99, 100 seeds per point, 100 maximum INDIVIDUAL task-voting attempts, p_cost_loss = p_vote_loss (numerically equal probability, independent packet draws), 0%–70% every 2% (36 conditions, 3,600 paired runs). Keep existing local Greedy, one initial lossy Cost exchange, same Rady Wi-Fi latency sampling, task ordering and commit/retirement. Do not overwrite the old majority or archived fallback summary CSV files.

Output raw per-seed and per-round CSV, designated seed-0 message/delivery audits and summary.csv. Report committed tasks, full 50-task success, Greedy CER, external Hungarian CER, total-cost gap only if ALL tasks commit, failed/no-qualified attempts, announced score counts, winning score, tie count, mean task attempts, simulated coordination latency, traffic bytes/messages and observed physical Cost/Vote drop rates. Incomplete tasks MUST NOT be replaced by forced or fake successes.

### 14.5 Reproducibility

After git pull and full unit tests, first smoke with 3 seeds and equal Cost/Vote Loss of 0%, 30%, 70%:

    python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 3 --cost-loss-probabilities 0,0.30,0.70 --loss-pairing diagonal --max-rounds 100 --vote-decision-rule quarter_plurality --output-root results/e2_greedy_quarter_plurality_no_fallback_smoke

Only if tests/smoke pass, run formal 100-seed sweep in the same shell:

    LEVELS="$(python3 -c 'print(",".join(f"{i/100:.2f}" for i in range(0, 71, 2)))')"
    python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities "$LEVELS" --loss-pairing diagonal --max-rounds 100 --vote-decision-rule quarter_plurality --output-root results/e2_greedy_quarter_plurality_no_fallback_100r50t

Acceptance checks: no fallback event phases, no commit without a qualifying announcement, failed attempts rotate tasks without retiring any robot, zero-loss matches full-information sequential Greedy, zero duplicate assignments, all actual loss probabilities as configured, and new SHA/seeds/evidence saved separately. The new code/tests are committed but the NEW suite and formal no-fallback run remain pending local execution.


## 15. E3/E4 — Robot/task scaling (maximum 100 robots, up to 1:1)

### 15.1 Experiment matrix and unchanged voting

This experiment implements the user's requested maximum fleet size 100, with no more tasks than robots (one-to-one maximum task load). It supersedes the earlier planned 200-robot E3 point in README for this primary study, without changing any E2 protocol behavior.

Use the following primary factorial grid:
- Robot counts R: 10, 20, 40, 60, 80, 100.
- Target task-load ratios T/R: 0.10, 0.25, 0.50, 0.75, 1.00.
- Convert fractional T using ROUND HALF UP: T=floor(R*target_ratio+0.5), enforce 1 <= T <= R, and always report the actual resulting T/R.
- R=10: tasks 1,3,5,8,10; R=20: 2,5,10,15,20; R=40: 4,10,20,30,40; R=60: 6,15,30,45,60; R=80: 8,20,40,60,80; R=100: 10,25,50,75,100.
- 30 unique size cells, including the previous 100R/50T reference and requested 100R/100T full load.
- The full set of all integer 1<=T<=R<=100 would contain 5,050 size cells. Use this structured representative grid instead; full dense enumeration is explicitly out of scope.

The ONLY voting method in the scaling experiment is the existing PURE quarter_plurality rule: each active robot independently casts one Greedy vote using its locally retained incomplete Cost rows, strictly more than 25% of the entire active electorate must be received before a candidate can announce, highest score among qualified announcements wins with global robot ID tie-break, and successful executors retire. If no one qualifies, no one commits, and the task rotates to the tail of the existing pending queue. No self-claim, fallback message, alternate winner selection or new state machine.

### 15.2 Fair controlled conditions

For each R/T cell test two conditions:
- 0% Cost Loss AND 0% Vote Loss (control).
- 30% Cost Loss AND 30% Vote Loss (primary packet-loss condition).

Cost and Vote stage physical packets are independently sampled at the same numerical loss probability. As before, only the initial Cost exchange is lossy; candidate final-score announcements and commits remain modeled as reliable and incur explicit communication time and payload bytes. Use the existing Rady Wi-Fi latency dataset, unchanged greedy cost model, scenario generation and network seed scheme. Each cell uses the same seed and static cost scene under both 0% and 30% loss, but distinct R/T cells represent distinct generated scenes even with matching integer seeds. The geometry continues to be a 100x100 Euclidean world and spatial density therefore changes when the robot count changes.

100 seeds per size cell per loss condition: 30 x 2 x 100 = 6,000 seed-condition runs.

**Attempt budget must depend on T.** A fixed 100 rounds would make 100R/100T unable to complete all tasks after even one failed voting attempt. Therefore use max_rounds = 2*T for every grid cell, giving exactly one failed-attempt allowance per task (and two attempts for T=1). This matches the previous 100R/50T max-rounds=100 baseline. Raw total rounds, no-qualified failures and attempts per requested task must all be reported; 1:1 successes should not be evaluated with a secretly smaller retry ratio.

Report: per-task completion and full T-task success; correct-executor rate against full-information sequential Greedy and the offline Hungarian optimum; total-cost gap only for fully completed assignments (NaN otherwise); mean voting attempts; time/messages/bytes both absolute and PER REQUESTED TASK; Cost/Vote observed physical drop rates; actual load ratio, R, T, method, SHA, seeds and zero safety errors. A final remaining robot may be forced into a costly last task even if the overall assignment completes. Thus global gap remains a critical metric at 1:1.

### 15.3 New scaling owner and evidence boundaries

New sole experiment-dimension owner: experiments.run_e3_e4_scaling. It MUST reuse experiments.run_e2_retirement.run_retirement_experiment for every (R,T) cell. It MUST NOT introduce a second vote ledger, state machine, network sampler, optimizer or altered quorum.

Named functions by responsibility:
- validate_scaling_axes: validate ordered/distinct robot counts, ratios, loss levels, seeds, round factor. Fail when R>100 or ratios exceed 1.
- build_scaling_cells: deterministic round-half-up conversion, prevent tasks exceeding active robots and prevent duplicated integer task counts from ratio rounding.
- make_scaling_plan: immutable source SHA, grid, seed, dataset and packet/attempt policy metadata.
- prepare_scaling_output: reject output reuse unless explicitly resumed with exactly the same plan and git SHA.
- read_completed_scaling_cell: require existing raw per-seed rows, per-round CSV, per-seed-zero message audit and summary; validate method/rule/R/T/seed-loss pair/SHA/round cap before reusing any previous cell.
- build_scaling_aggregate_rows: preserve original E2 per-cell summary metrics and add actual vs planned load ratios and attempts/time/messages/bytes PER REQUESTED TASK.
- run_scaling_benchmark: execute each unique cell via existing E2 experiment owner, append complete verified rows to the root summary after each cell, and support safe resume without overwriting incomplete evidence.
- main: fixed 100-R ceiling and configurable levels/ratios/loss/seeds/output root; no change to earlier E2 CLI.

Critical diagnostic codes: INVALID_SCALING_ROBOT_LEVELS, INVALID_SCALING_LOAD_RATIOS, INVALID_SCALING_LOSS_LEVELS, INVALID_SCALING_SEEDS, INVALID_SCALING_ATTEMPT_MULTIPLIER, SCALING_TASK_COUNT_OUT_OF_RANGE, SCALING_DUPLICATE_TASK_CELL, SCALING_OUTPUT_ALREADY_EXISTS, SCALING_UNMANAGED_OUTPUT_ROOT, SCALING_RESUME_PLAN_MISMATCH, SCALING_CELL_EVIDENCE_INCOMPLETE, SCALING_CELL_PROVENANCE_MISMATCH, SCALING_PARTIAL_CELL_REQUIRES_MANUAL_REVIEW. All use a structured owner/function/category and expected/actual/details; run-level protocol failures continue to come from the existing actual owners.

### 15.4 Output and commands

The new root is results/e3_e4_scaling_100robot_cap with benchmark_plan.json, cells/R###_T###/summary.csv, per-cell raw/round/event files, and an aggregated summary.csv with one row per (R,T,loss) condition (expected 60 rows). This root must never overwrite E2 majority or pure 25% previous results. Aborted runs can be resumed using --resume with an IDENTICAL grid, git SHA, seed count, dataset, attempt factor and verified existing cell files. Incomplete partially written cells require explicit inspection/moving aside; no silent overwrites.

User Mac preflight:

    git pull
    python3 -m unittest discover -s tests -v
    python3 -m experiments.run_e3_e4_scaling --robot-levels 10,100 --load-ratios 0.5,1.0 --loss-probabilities 0,0.30 --seeds 3 --attempts-per-task 2 --output-root results/e3_e4_scaling_smoke_100cap

Expect 4 unique size cells x 2 losses x 3 seeds = 24 seed-condition simulations.

Formal default:

    python3 -m experiments.run_e3_e4_scaling --seeds 100 --output-root results/e3_e4_scaling_100robot_cap

Expect 30 cells x 2 losses x 100 seeds = 6,000 runs. On interruption, repeat the identical command with --resume. Compare the 100R/50T 30% cell against the previously validated standalone E2 result, with matching method, seed set and max_rounds=100.

The earlier 89/89 tests and 3,600-run E2 no-fallback curve were verified by the user on a PRE-scaling commit. New scaling tests and full formal scaling runs are pending Mac execution and may NOT be presented as completed results.


## 16. Greedy-only communication comparison: fixed optimizer, varying packet loss and vote rule

### 16.1 Research question and explicit scope

The user explicitly chose **communication robustness and decentralized coordination**, NOT global multi-task optimization, as the contribution of the study. The experimental objective is to quantify performance loss induced by Cost/Vote packet loss, with local Sequential Greedy held fixed, and to compare the **51% strict-majority communication protocol** with the **pure, no-fallback >25% final-score-announcement protocol**.

No Hungarian solver, global-optimum reference, additional greedy planner, new task scheduler, or new packet transport is needed in this DERIVED REPORT. Previously generated Hungarian raw/oracle fields are preserved as historical evidence in their original E2 files; this analysis ignores those columns entirely and does not modify or delete any old data. Do not conflate this with an algorithmic claim of global optimality.

The experiment is evidence-only: consume the two completed and separately stored **100R/50T, 100-seed, max_rounds=100, Cost Loss = Vote Loss 0..70% step2%** E2 raw CSVs (not just rounded summary curves):

- source A, majority: results/e2_joint_loss_diagonal_100r50t/raw/retirement_*.csv; method=democracy_greedy_retirement; voting rule=strict_majority;
- source B, current pure 25%: results/e2_greedy_quarter_plurality_no_fallback_100r50t/raw/retirement_*.csv; method=democracy_greedy_quarter_plurality_retirement; voting rule=quarter_plurality;
- **forbidden source**: results/e2_greedy_quarter_plurality_100r50t (historic rejected self-claim fallback version).

Both inputs must have exactly one raw CSV each, valid source git SHA, the SAME robot/task dimensions, complete seed×loss coverage, matching per-seed **full-information zero-loss Sequential Greedy reference cost** and fully committed/Greedy-matching 0% controls. A historical majority raw dataset may legitimately lack the later-added vote_decision_rule column; accept ONLY method=democracy_greedy_retirement as a grounded indication of that legacy rule. Reject any wrong method or explicit obsolete fallback rule.

### 16.2 Controlled condition axes and paired measurement semantics

Primary figure selection: p_cost_loss = p_vote_loss = p for p ∈ {0.00,0.10,0.20,0.30,0.40,0.50}. These six points already exist in the historical 36-level 2%-step raw runs. No re-simulation is needed and **no different random scenario should be substituted**. An extended analysis can use the entire originally tested p=0.00,0.02,...,0.70 axis; the 0% level must always be present.

For each rule separately, compare each seed/loss scenario to THE SAME seed/rule's 0% loss run. The cost-loss degradation on a fully assigned batch is:

    Delta_GreedyCost(rule, seed, p) =
        100 * [Cost(rule, seed, p) / Cost(rule, seed, 0) - 1]

By validation, Cost(rule, seed, 0) is that seed's full-information Sequential Greedy cost, and is the same across majority and pure-25% archives.

- The batch **must** have committed ALL T requested tasks before reporting a full-task-set cost delta. For any partial allocation, record cost_comparison_eligible=0 and the cost delta as NaN; do NOT compute a misleading low partial cost, infer a penalty, or erase that seed from assignment-completion statistics.
- Curves report mean cost degradation **only among fully assigned runs** AND the exact number of successful cost-eligible seeds. The selection effect when loss is high must be disclosed prominently.
- For a directly paired cross-protocol cost delta, include ONLY those same seeds where BOTH protocols fully committed. If that intersection is empty, output NaN with both_completed_count=0; do NOT substitute a zero difference or unpaired successful-only means.
- For each seed and p, record task Commit fraction, full T-task success, Greedy executor identity agreement measured against full-information per-task Sequential Greedy (with a per-requested-task denominator), agreement AMONG committed tasks separately when available, failed vote attempts, total simulated coordination milliseconds, number of logical messages and payload bytes.
- Compare elapsed time/messages/bytes both as absolute magnitudes and as per-seed changes from THAT PROTOCOL's own 0% loss run; this preserves the known very different zero-loss timing model for majority vs final-score-announcement plurality.
- Pair protocols by the SAME seed and p. Record batch success percentage-point difference (quarter - majority), counts of both completed / quarter-only completed / majority-only completed / neither completed; Greedy executor rate difference, elapsed time/message/byte difference, and cost difference ONLY over BOTH-complete seeds.
- Observed Cost/Vote packet drop rates are **aggregate number of drops / physical attempts**, not naive averaging of seed-level ratios; a zero-attempt vote stage yields NaN (no evidence), not an arbitrary claim of zero packet loss.

The new report does NOT recompute any task decisions or call solve_hungarian_assignment. It must not be mistaken for a controlled comparison of protocol delivery mechanisms beyond the model's reliable qualified-score announcements and reliable Commit assumption. Historical raw sources may have different code SHAs; require a single SHA within each source and independently verify per-seed Greedy reference costs. Source revision equality BETWEEN the two protocol implementations is not required because their formal runs were committed at different revisions, but this is an explicit limitation.

### 16.3 Reporting owner and diagnostic contract

New read-only analysis owner: experiments.compare_greedy_communication. It consumes the original E2 evidence, which remains append-only, and writes a separate derived report root without editing either input.

Named-function ownership:
- validate_comparison_configuration: data validation for requested R/T/seeds/attempt cap/strictly sorted diagonal loss axis containing p=0.
- locate_single_raw_evidence: dependency/contract validation of exactly one timestamped raw input CSV per protocol.
- validate_greedy_evidence_row: per-row data, rule, method, seed, R/T, packet loss, success/commit accounting and safety-contract validation.
- read_greedy_raw_evidence: source integrity/coverage: no duplicate seed/loss, one SHA per source, full selected seed×loss Cartesian coverage, no fallback methods.
- validate_paired_greedy_scenarios: verify equal scenario Greedy-reference costs across both inputs and all p; zero-loss batch fully complete with Greedy score 100%, cost identical to reference.
- build_greedy_per_seed_rows: compare to own rule/seed p=0, excluding partial batches from full cost gaps.
- summarize_greedy_rule_curves: per-rule mean task/full success, Greedy executor accuracy, cost delta on completed subsets with n, attempts/latency/messages/bytes and physical stage drop rates.
- summarize_paired_protocol_differences: same-seed cross-rule success disagreement and ONLY both-complete cost delta; missing shared completion stays NaN.
- write_greedy_only_comparison: immutable separated output guard, three CSVs and timestamp/source SHA/SHA256 manifest.
- compare_existing_greedy_evidence: orchestrates only these read/validation/analysis steps; it does not own physical voting, planner or Hungarian computations.

First-failure diagnostic codes with owner/function/category/expected/actual:
- INVALID_GREEDY_COMPARISON_SHAPE / validate_comparison_configuration / data
- INVALID_GREEDY_COMPARISON_LOSS_AXIS / validate_comparison_configuration / data
- MISSING_GREEDY_RAW_EVIDENCE / locate_single_raw_evidence / dependency
- AMBIGUOUS_GREEDY_RAW_EVIDENCE / locate_single_raw_evidence / contract
- MISSING_GREEDY_RAW_COLUMNS / read_greedy_raw_evidence / dependency
- INVALID_GREEDY_RAW_VALUE / validate_greedy_evidence_row / data
- GREEDY_RAW_CONTRACT_MISMATCH / validate_greedy_evidence_row / contract
- DUPLICATE_GREEDY_SEED_CONDITION / read_greedy_raw_evidence / contract
- GREEDY_SEED_LOSS_COVERAGE_MISMATCH / read_greedy_raw_evidence / contract
- PAIRED_GREEDY_SCENE_MISMATCH / validate_paired_greedy_scenarios / contract
- ZERO_LOSS_GREEDY_BASELINE_MISMATCH / validate_paired_greedy_scenarios / contract
- GREEDY_ANALYSIS_SOURCE_OUTPUT_COLLISION / write_greedy_only_comparison / state
- GREEDY_ANALYSIS_OUTPUT_EXISTS / write_greedy_only_comparison / state

No voting, cost exchange, packet sampling, membership/retirement, optimizer or runtime execution owner is modified; no new wrapper, hidden fallback, or second state machine.

### 16.4 Outputs, acceptance and Mac commands

New derived report root: results/e2_greedy_only_communication_comparison. Expected generated outputs:
- greedy_per_seed.csv: 2 protocols × 100 seeds × 6 selected loss points = 1,200 rows for the primary axis (with a full-completion indicator and NaN full cost for failures).
- greedy_rule_curve.csv: 2 × 6 = 12 aggregate rows.
- greedy_protocol_delta.csv: 6 paired condition rows.
- manifest.json: exact inputs, source git SHAs, source raw SHA256 hashes, analysis git SHA, UTC time, selected seeds/loss axis and statistical limitations.

Preflight and primary comparison (from Mac checkout where BOTH previous E2 raw archives already exist):

    git pull
    python3 -m unittest discover -s tests -v
    python3 -m experiments.compare_greedy_communication

Extended full 36-point Greedy-only curves can be generated to a DISTINCT new root by providing an explicit 2% axis, leaving the primary report unchanged:

    LEVELS="$(python3 -c 'print(",".join(f"{i/100:.2f}" for i in range(0, 71, 2)))')"
    python3 -m experiments.compare_greedy_communication --loss-probabilities "$LEVELS" --output-root results/e2_greedy_only_communication_comparison_36point

Acceptance requires exact source SHA/seed/scene matching, zero baseline cost differences at p0, no references to Hungarian in any GENERATED CSV column, all 0% scenario controls valid, no incomplete allocation included in a full-batch cost mean, and counts of paired successes reconciling to seeds for every p. Historical raw E2 roots and E3/E4 6,000-run scaling results must remain untouched.

Status when authored: source and regression tests committed; actual run on user's Mac pending. Do not claim the newly derived report has been generated until its files and console results are observed.


## 17. Literature-grounded packet-loss defense baseline — vote-copy redundancy (NO ACK)

### 17.1 Scientific comparison, published baselines, scope

User-requested priority: compare our decentralized packet-loss-resilient task allocation against OTHER established communication/reliability and decentralized MRTA techniques. Preserve the unchanged Sequential Greedy optimizer and compare complete-task success, assignment accuracy relative to 0%-loss Greedy, physical traffic bytes, time and safety.

Sources used for study design:
- IEEE Technology Navigator, Automatic repeat request (https://technav.ieee.org/topic/automatic-repeat-request/). Genuine ARQ uses receiver acknowledgement and retransmission feedback; this initial baseline has NO ACK and is NOT ARQ.
- Retransmission or Redundancy: Transmission Reliability in Wireless Sensor Networks, IEEE 2007, DOI 10.1109/MOBHOC.2007.4428620. Published reliability/energy tradeoff motivation, NOT an identical published algorithm implementation.
- Choi, Brunet, How, Consensus-Based Decentralized Auctions for Robust Task Allocation, IEEE Transactions on Robotics 25(4), 2009, DOI 10.1109/TRO.2009.2022423 (CBAA and CBBA, separate distributed assignment algorithms).
- MIT Aerospace Controls Lab official CBBA/ACBBA overview https://acl.mit.edu/projects/consensus-based-bundle-algorithm; Rantanen et al., Performance of the Asynchronous Consensus Based Bundle Algorithm in Lossy Network Environments, IEEE SAM 2018, DOI 10.1109/SAM.2018.8448984.

This initial code change implements ONE narrow and correctly labeled external reliability-control mechanism: FIXED OPEN-LOOP REDUNDANT REMOTE VOTE TRANSMISSION. It is neither ARQ, coded redundancy, CBAA, CBBA nor ACBBA. Future separate blocks should implement real ACK/retry and faithfully reproduce published CBAA/CBBA/ACBBA including their consensus/deconfliction and duplicate-allocation behavior, with separate owners/tests.

### 17.2 Exact transport policy and unchanged election semantics

Add opt-in vote_repetitions = K where K is an actual integer in {1, 2, 3}. K=1 is the historical default, preserving the EXACT original first physical Vote key and all existing per-seed Cost/Vote Bernoulli draws.

For each remote Greedy Vote:
- K=1 emits one physical unicast, as before.
- K=2 or 3 sends K unconditional packet copies at send_time + copy_index * phase_timeout_ms. There is no ACK and copies are sent even when an earlier copy was delivered.
- Each copy uses independent Bernoulli Vote Loss and a separately keyed empirical latency sample. Physical event and delivery observation include transmission_index (0..K-1). Every copy is charged in logical_message_count, payload_bytes and remote_vote_attempts, including copies that are dropped or redundant.
- Select the EARLIEST delivered physical copy and feed exactly one logical Vote to protocol.record_vote. Never count another packet copy as an extra voter. Local self-votes are never transmitted or repeated.
- Vote decisions at K>1 wait for the physically scheduled copies to complete. For the 25% final-score announcement, the vote collection deadline is max(cost_ready_times)+K*phase_timeout_ms. Strict majority also waits for scheduled copies before final Commit. This intentionally charges a conservative sequential slot delay. The model does NOT simulate collision, byte-rate or MAC scheduling.
- Initial Cost rows are broadcast ONCE with original independent Cost Loss and never resent. Hence this first baseline defends against VOTE LOSS only. Later Cost Loss recovery is its own separate concern. Reliable qualified final-score announcements and Commit assumptions remain unchanged.
- Neither the decision threshold, local Greedy, task queue rotation, robot retirement, nor the forbidden self-claim fallback is altered. 25% means strictly greater than 25% of the whole active electorate, not physical packet-copy count.
- A single remote vote delivery probability with independent copy loss p is 1-p^K, but full-task success also depends on missing Cost rows, candidate-vote disagreement and finite voting attempts; never infer whole-team performance from that packet formula alone.

### 17.3 One owner per concern / diagnostic contract

- network.validate_vote_repetitions: data / INVALID_VOTE_REPETITIONS; K must be an integer in 1..3.
- coordination._unicast_event and coordination._lossy_unicast_delivery: original physical transport owner functions, now accept/record optional transmission_index=0; index 0 retains original keyed samples, indices >0 get unique copy-suffixed keys.
- coordination.transmit_repeated_remote_vote: one named FIXED-COPY physical Vote sender function; return K physical events, K physical delivery observations and earliest successful observation (or None). It neither records votes nor chooses winners.
- coordination.simulate_democracy_hungarian_lossy: unchanged owner of vote ledger/threshold/Commit; consumes only earliest delivered remote copy as one voter and enforces end-of-copy decision time at K>1.
- coordination.simulate_democracy_hungarian_retirement: unchanged task queue and executor retirement owner; forwards validated K; one-to-one and failed-round task rotation preserved.
- experiments.run_e2_retirement.retirement_transport_stage_metrics: original physical packet counter, now computes self-votes from DISTINCT (round, sender, receiver, task) remote ballot identities and checks each has copy indices EXACTLY [0..K-1]. Contract / REPEATED_VOTE_PHYSICAL_COPIES_MISMATCH with expected, actual and details.
- experiments.run_e2_retirement.run_retirement_experiment, retirement_result_row, retirement_round_rows, summarize_retirement_results and write_retirement_audit_events: existing data-evidence owners; add vote_repetitions to new raw/round/summary/audit records and transmission_index to compressed seed-0 message/delivery events. Expose --vote-repetitions {1,2,3}, default=1. Refuse known archived output directories for K>1.
- tests/test_vote_repetition_baseline.py: K input bounds, 1-copy deterministic parity, first physical votes all lost but second copy reaches old majority, no duplicate voter, higher physical messages/bytes/time at 0% loss, no emergency Commit when all copies lost, unchanged retirement and Cost exchange, nonnegative self-votes and physical copy audit.

This is a bounded physical vote-transport concern. No second coordinator, voting state machine, optimizer, or safety workaround was added. All historical E2/E3/E4 entry points default to K=1.

### 17.4 Paired experiment and commands

Compare 100 Robots / 50 Tasks, Cost Loss=Vote Loss=p (independent draws), 100 seeds at each condition, max 100 individual task attempts, same original per-seed scene, optimizer and physical network model:

A: old 51% strict-majority with K=1 (historical E2, already recorded).
B: strict-majority with K=2 redundant Vote copies (NEW).
C: strict-majority with K=3 redundant Vote copies (NEW).
D: pure >25% final-score Greedy with K=1 and NO fallback (historical E2, already recorded).
Optional E: pure >25% with K=2 (transport ablation, not necessary for first formal comparison).

First execute all unit tests and three-seed smoke at p = 0,0.30,0.50 into NEW separate results:

    git pull
    python3 -m unittest discover -s tests -v
    python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 3 --cost-loss-probabilities 0,0.30,0.50 --loss-pairing diagonal --max-rounds 100 --vote-decision-rule strict_majority --vote-repetitions 2 --output-root results/e2_repeat2_majority_smoke
    python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 3 --cost-loss-probabilities 0,0.30,0.50 --loss-pairing diagonal --max-rounds 100 --vote-decision-rule strict_majority --vote-repetitions 3 --output-root results/e2_repeat3_majority_smoke

After tests and smoke PASS, run the two 100-seed × 36-level (0..0.70 every 0.02) formal baselines into separate NEW directories. 3,600 runs per additional K:

    LEVELS="$(python3 -c 'print(",".join(f"{i/100:.2f}" for i in range(0, 71, 2)))')"
    python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities "$LEVELS" --loss-pairing diagonal --max-rounds 100 --vote-decision-rule strict_majority --vote-repetitions 2 --output-root results/e2_repeat2_majority_100r50t
    python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities "$LEVELS" --loss-pairing diagonal --max-rounds 100 --vote-decision-rule strict_majority --vote-repetitions 3 --output-root results/e2_repeat3_majority_100r50t

Primary plots: full assignment success and committed task fraction versus p; physical vote packets/bytes, simulated end-to-end coordinator time versus p; Greedy executor agreement and complete-task cost gap versus each seed's 0%-loss Greedy (report complete-case sample n); actual physical vote drop rate and per-copy audit; safety errors / duplicate assignment must remain zero.

The legacy E2 experiment runner still computes a Hungarian oracle for backward-compatible existing raw columns; this is NOT an optimized method or comparison metric in this baseline analysis. Keep the Greedy-only primary plots/claims. Do not overwrite any historical E2/E3/E4 evidence or mislabel redundancy as ARQ or published CBBA.

### 17.5 Limitations, verification and next steps

This fixed K-copy scheme assumes independent Bernoulli losses, ignores shared airtime/collision and correlated outages, and does not repair initial Cost packet loss or test loss of reliably modeled announcement/Commit messages. It is a fundamental communications-control baseline, not yet a fair published MRTA algorithm-to-algorithm comparison. Next separately implement true ACBBA/CBAA if feasible under a validated 1 robot : 1 task policy and a distributed winner/conflict state model, keeping score/travel costs and communication accounting comparable.

Source and new tests are committed, but tests and K>1 experiments have NOT yet been run on the user's Mac. The last 111/111 test pass was for the previous code revision. Do not claim any new packet-loss success rates until evidence is observed.


## 18. External published-family baseline: synchronous single-assignment CBAA (E8)

### 18.1 Source fidelity, research scope and explicit adaptations

Published source: Han-Lim Choi, Luc Brunet and Jonathan P. How, "Consensus-Based Decentralized Auctions for Robust Task Allocation," IEEE Transactions on Robotics 25(4), 912–926 (2009), DOI https://doi.org/10.1109/TRO.2009.2022423, publicly archived MIT https://dspace.mit.edu/entities/publication/b0bf0a05-be3b-433b-9f4b-ce314ed5178b . CBAA Section III comprises an iterative **single-assignment auction** (each robot chooses at most ONE task for which its own score beats known winning bids) followed by a **bid maximum-consensus** process through neighbor communication; a robot releases its currently claimed task when outbid. CBBA in Section IV builds multi-task bundles and has different conflict-handling and timestamp logic: this baseline DOES NOT implement or claim to be CBBA/ACBBA.

This standalone CBAA implementation uses the published two-phase mechanism, with transparently documented engineering restrictions/adaptations:
- synchronous iteration barriers with a COMPLETE communication topology; there is no simulated asynchrony or sparse topology in this first milestone;
- score=c_ij=1/(1+Euclidean distance cost_ij)>0, a strictly decreasing nonnegative-cost utility. No Hungarian, own 25% election, own Greedy one-task voting, global optimal assignment, or global bid normalization drives the CBAA decisions. Any difference in cost vs sequential Greedy may reflect a different assignment optimizer, not packet-loss performance;
- deterministic tie-breaking by lower task ID (own task choice) and lower robot ID (equal winning scores). A winner-origin ID accompanies each winning-bid vector entry so a relay cannot wrongly claim to be the original winning bidder. This extra metadata is explicit, and message length includes it: one broadcast payload APP_HEADER_BYTES + Nt*(FLOAT64_BYTES + ID_BYTES);
- every robot broadcasts its entire bid and winner-origin vector once per iteration; independently sampled Bernoulli physical loss at EACH receiver for every one of the other N-1 nodes; local self information is always available;
- phase delay sampled from the exact same pinned Rady Wi-Fi empirical-delay profile as E2, and each iteration is fixed at one profile-maximum phase timeout. A physically delivered packet arriving after this deadline is accounted as late but NOT ingested. The initial test uses a fixed number of iterations; **there is currently NO decentralised network-wide stop-detection protocol** and no hidden global inspector used to terminate the iteration loop early. Fixed-budget time/message overhead is a deliberate conservative study control, not a claim of optimized CBAA runtime;
- **no centralized rescue, arbitration or reliable final Commit**. Only a separate external evaluation observer, AFTER the fixed iteration budget, can assess whether ALL local nodes agree on task winning bid and owner, and whether exactly that agent has an unconflicted local task claim. If beliefs disagree, the task is UNCONFIRMED; if multiple robots claim it, the task is in a raw split-brain conflict. No global observer winner is broadcast or fed back into any robot. Observer agreement is NOT equivalent to an actual distributed Commit or physical task execution;
- CBAA consensus-message loss probability p is numerically compared with the old E2 Cost Loss = Vote Loss = p, but CBAA has ONE physical consensus-packet stage per iteration, while old E2 has a one-time Cost and repeated Vote stage with reliably modeled Commit. These are NOT equivalent packet-message workload or reliable control-message assumptions. Do NOT ascribe all differences to a single "packet-loss algorithm" without reporting message semantics and byte/time accounting.

This is explicitly a synchronous single-assignment CBAA **reference implementation** rather than an exact reproduction of the original paper's asynchronous network scheduling, termination control or multi-assignment CBBA. It is the FIRST bounded source-based baseline. Actual CBAA zero-loss convergence must pass tests and a 100R/50T smoke before the results may be used as a paper headline. A later bounded concern can add a proper distributed termination protocol, direct sparse/burst networks, or separate CBBA/ACBBA owners.

### 18.2 Exact source/owner/function and data lifecycle

New CBAA auction-consensus owner: democracy_mrta.cbaa. It holds only the CBAA local state; the original democracy_mrta.coordination multi-round Vote quorum/quarter-plurality membership state machine is untouched.

- CBAALocalState(robot_id, assigned_task, winning_bids, winning_robots): local ONLY. x_i is at most one task, y_i is per-task max known bid and origin; starts empty.
- validate_cbaa_configuration: check original optimizer.validate_cost_matrix and network.validate_packet_loss_probability owners first; then CBAA score's nonnegative costs, exact integer max_iterations>=1 and valid positive finite phase_timeout_ms. New first-failure data/CBAA_NEGATIVE_COST, data/CBAA_INVALID_ITERATION_BUDGET and time/CBAA_INVALID_PHASE_TIMEOUT.
- initial_cbaa_states: initialize independent per-agent state at no assignments / zero bids / None owners.
- cbaa_score: locally transform Euclidean cost to positive descending reward, independent of other agents' private costs.
- cbaa_bid_outbids: deterministic max bid / lower origin-ID tie-break, called by both CBAA auction and CBAA consensus phases; no centrally assumed winning agent.
- cbaa_auction_phase: published Phase 1 owner; agents with assigned tasks keep them; unassigned agents only bid for tasks where their own reward beats stored bid, then choose their own maximum reward / lower task ID.
- exchange_cbaa_consensus_packets: physical CBAA one-broadcast-per-agent transport stage, reuse existing coordination._broadcast_event and _lossy_broadcast_deliveries so sender message count, one-sender latency and per-receiver drops are charged consistently with E2. Returns each receiver's OWN received local-state snapshots, N sent broadcasts, N*(N-1) physical reception opportunities, bytes, physical drops and late arrivals, plus seed-0 audit when requested. No global winner selection inside it. A delivered packet without an arrival time fails contract/CBAA_DELIVERED_PACKET_WITHOUT_TIME.
- cbaa_consensus_phase: published Phase 2 owner; per agent update each bid entry with maximum from RECEIVED neighbors and itself, propagate real winner origin metadata, release its own assignment if outbid.
- audit_cbaa_local_agreement: EXTERNAL observer after protocol, not called by agents to elect or Commit. Reports ALL local task claims, per-task conflicts, unanimous winner origin+score confirmation and still-unconfirmed tasks. Never arbitrates a split-brain task or creates a new valid robot allocation.
- simulate_cbaa: runs original CBAA two named phases for exactly max_iterations, counts physical broadcasts/bytes/delivery attempts/late messages and performs one post-hoc read-only audit. Safety/CBAA_DUPLICATE_OBSERVER_AGREEMENT guards an impossible duplicate robot in observer-confirmed pairs. Never calls solve_hungarian_assignment, the Greedy task-vote engine, or the 25% Commit/score owner.

New independent experiment/evidence owner: experiments.run_cbaa_baseline:
- validate_cbaa_benchmark_axes: data / INVALID_CBAA_BENCHMARK_AXES, INVALID_CBAA_LOSS_AXIS. Current user-approved R<=100, T<=R, seeds>=1, iterations>=1, increasing loss levels.
- prepare_cbaa_output: state / CBAA_OUTPUT_SOURCE_COLLISION or CBAA_OUTPUT_ALREADY_EXISTS. Never overwrite historical E2 strict/25%, K2/K3 or E3/E4 raw. Permit dedicated ledger README-only output. Partial abort requires manual new output path instead of overwriting.
- cbaa_result_row: per seed and p, include ALL raw local claims, conflicts, observer confirmed tasks, unconfirmed tasks, task agreement, physical packets/drops, bytes, elapsed time, fixed iterations, SHA, Greedy offline reference for evaluation only, timestamp.
- cbaa_full_batch_cost: only FULL observer agreed task batches receive total cost. Missing/conflicted batches have NaN cost, never bogus cheap partial assignment; this is POST-HOC evaluation, not a CBAA decision.
- summarize_cbaa_conditions: per-p results with full-agreement sample count, task agreement, conflicts, completed-only cost, actual physical drops/attempts, bytes and time.
- write_cbaa_seed_zero_audit: compressed seed-0 per-sender broadcasts, per-receiver physical deliveries and each final local CBAA bid/owner vector, with NO fake consensus Commit.
- run_cbaa_baseline: independent benchmarking orchestration; same generate_e0_scenario cost rows/seed, same pinned Rady Wi-Fi latency sampler, independent Bernoulli loss per physical consensus reception, source git SHA, deterministic seed and separate output root.
- main: CLI only.

No existing Vote owner, quorum, runner, optimizer, packet-loss keyed behavior, E2/E3/E4 historical data or K-copy baseline is modified in this first CBAA block.

### 18.3 Study design and acceptance

**Primary current acceptance is algorithm correctness, not best-performance claims.** First run all existing/new unit tests, then small realistic CBAA smoke on Mac:

    git pull
    python3 -m unittest discover -s tests -v
    python3 -m experiments.run_cbaa_baseline --robots 10 --tasks 5 --seeds 3 --loss-probabilities 0,0.30,0.50 --max-iterations 20 --output-root results/e8_cbaa_single_assignment_smoke

Expected one new root with:
- raw/cbaa_<UTC>.csv — 3 seeds x 3 p = 9 rows; no Hungarian metrics/solver calls, no fabricated Commit;
- summary.csv — one line per p, complete-only batch cost count and full observer agreement, task consensus, local split-brain metrics, packet/byte/time;
- events/cbaa_audit_<UTC>.csv.gz — all physical consensus-broadcast send/reception events for seed 0, and final local winner bid and ID vectors;
- manifest.json — original publication DOI, pinned Rady dataset and Git SHA, exact R/T/seeds/max_iterations/loss axis/timeout, score and adaptation disclosures.

After SMALL smoke and unit suite pass, run a 100R/50T 3-seed pilot into a DIFFERENT evidence root; confirm p=0 achieves whole-team observer agreement, no hidden global arbitration, and physical drop ~p for finite samples:

    python3 -m experiments.run_cbaa_baseline --robots 100 --tasks 50 --seeds 3 --loss-probabilities 0,0.30,0.50 --max-iterations 20 --output-root results/e8_cbaa_100r50t_pilot

If 0%-loss full observer agreement fails, treat as a convergence/iteration-budget contract or algorithm bug to investigate BEFORE formal comparison; do NOT accept a fragmented CBAA method in a paper comparison or quietly promote post-hoc observer assignments to authoritative Commit. If p>0 creates duplicated local claims, report them directly as failure/unsafe convergence, do not censor them by selecting one global winning robot.

Only after validating CBAA's 0%-loss convergence, independent loss protocol, message byte/time policy, and distributed stopping fairness should we design and launch formal 100 seeds x 36 p levels and compare with the already user-completed Greedy 51%, Greedy 25%, and Vote K2/K3 baselines. Unlike previous fixed-Greedy-only ablations, an algorithm-level CBAA comparison MUST disclose that the CBAA local auction optimizes a distinct task-selection objective and its packet semantics differ from the original E2 Cost+Vote model.

### 18.4 Verification limits / next concern

User already completed prior 51%-majority K1, K2, K3 and pure 25% K1 100R/50T, 36 levels, 100 seeds each; new CBAA code/tests have only been committed through GitHub, not executed on the user's Mac as of this change. There is currently no proof of zero-loss full agreement at 100R/50T and no actual new CBAA baseline numerical results. The fixed iteration budget deliberately does not include an implementable fully distributed "all agents stopped" detection; a subsequent bounded change and its own continuity record are required before claiming general fair latency comparisons with the old E2 termination model or published original's asynchronous scheduling. Published CBBA/ACBBA faithfully implemented as separate standalone algorithms remains subsequent work.


## 19. E9A observed sent-Bytes communication calibration — NOT hard-capped

### 19.1 Goal, fairness and boundaries

After the user's Mac verified CBAA at 100R/50T, 3 seeds, p=0/.30/.50 (135/135 tests), they requested a communication-matched rather than arbitrarily 20-round or one-round comparison against the previously completed Greedy pure25 protocol. Existing CBAA 20 fixed rounds generate 2000 physical broadcast SEND events, 1,232,000 sender-accounted payload Bytes, and 198,000 per-receiver delivery opportunities. The user-approved initial change is one bounded READ-ONLY analysis, not a global refactoring of either runtime.

Owner experiments.compare_cbaa_budget reads existing E2 pure25 RAW data and independently executed CBAA raw for different iteration budgets, without running the model again or modifying source CSVs. It never chooses task winners or changes CBAA bids, Greedy votes, network delivery, task queue, timeout, or safety. The historical p0 Greedy run is the baseline for choosing a *nearby CBAA transmission budget*.

### 19.2 What equal/near observed payload means

Primary unit: application payload Bytes transmitted by sender. A broadcast is counted ONCE at sender even if it offers N-1 independent recipient delivery opportunities. Vote unicasts are counted once per actual physical send. Message counts, receiver opportunities and simulated elapsed time are separately reported, never mistaken for transmitted Bytes. Greedy pure25 payload includes one-time Cost exchange, remote Vote packets, qualified-score announcements and reliably modeled Commit packets. CBAA sends one vector with task bids plus original winning robot IDs each round: R*K*(16+12*T) Bytes across K iterations (in current model).

Same seed, robots, tasks and p are required across sources; every source must report the same offline full-information Greedy scenario reference cost per seed, and Greedy p=0 must successfully allocate every task and match its full-information Greedy oracle. Greedy uses independent Cost and Vote losses at equal numeric p, while CBAA uses one consensus-vector per-receiver loss stage at p. Greedy's reliable Commit/score announcements vs CBAA's post-hoc observer agreement are NOT interchangeable. Neither simulator models MAC channel contention, retry airtime or radio bandwidth. The resulting E9A analysis is observed traffic calibration, NOT a controlled equal-hard-budget intervention.

Selection rule (prevents outcome cherry-picking):
- Compute mean sender payload bytes of pure25 Greedy p=0 over selected paired scenario seeds.
- Compute mean CBAA p=0 sender payload bytes for each available integer max_iterations K. This does not inspect any CBAA success/metric or p>0 result.
- Choose the K with smallest absolute fractional difference to Greedy p=0 sent bytes; tie-break by smaller K.
- Require the closest candidate to be within +/-10% by default, else explicitly UNMATCHED. No made-up fractional round or selective success conditioning.
- Independently test actual mean byte ratios at EACH later loss p, and report how many individual paired seeds are within the same tolerance. A p=0 match is NOT presumed matched at p=.30/.50.
- Keep all failed/incomplete runs and CBAA split-brain/unconfirmed tasks in success-rate denominators; never treat a partial task set as a cheap full allocation. No retrospectively invented budget-abort state.

### 19.3 One named concern per function and diagnostics

New owner experiments.compare_cbaa_budget:
- validate_budget_calibration_config: typed R,T,seeds,max_rounds, sorted unique p including 0, tolerance and distinct source roots. data / INVALID_BUDGET_CALIBRATION_SHAPE and INVALID_BUDGET_CALIBRATION_GRID.
- locate_budget_source_file: exactly one timestamped raw CSV per historical Greedy and CBAA source; dependency / MISSING_BUDGET_SOURCE_CSV, contract / AMBIGUOUS_BUDGET_SOURCE_CSV.
- validate_budget_source_row: original algorithm identity, no rejected fallback, valid source dimensions/physical messages/sent bytes/observed outcome, exact CBAA send+receive arithmetic. data / INVALID_BUDGET_SOURCE_VALUE, contract / BUDGET_SOURCE_CONTRACT_MISMATCH.
- read_budget_source: exact requested seed-loss coverage, one source revision and one CBAA max_iterations per root (while permitting extra historical seeds). dependency / MISSING_BUDGET_SOURCE_COLUMNS; contract / DUPLICATE_BUDGET_SEED_LOSS and BUDGET_SOURCE_COVERAGE_MISMATCH.
- validate_paired_budget_scenes: same offline Greedy scenario cost across original sources and zero-loss original task/Greedy correctness. contract / BUDGET_PAIRED_SCENARIO_MISMATCH and BUDGET_ZERO_LOSS_GREEDY_FAILURE.
- calibrate_cbaa_send_budget: p=0 traffic-only nearest K, never CBAA outcome-based. contract / BUDGET_ZERO_TRANSMISSION_REFERENCE.
- build_budget_observation_rows: per-seed per-loss per-CBAA-budget observed Greedy and CBAA full success, task/observer coverage, actual packet sender bytes, messages/time, split-brain and per-recipient physical loss (observation only).
- write_budget_calibration: immutable output root, new budget_options.csv, budget_per_seed.csv, budget_curve.csv and manifest.json (source Git SHA, SHA256, analysis SHA, calibration rule and limitations). state / BUDGET_REPORT_SOURCE_COLLISION, BUDGET_REPORT_ALREADY_EXISTS.
- compare_cbaa_communication_budget: read-only orchestration, rejects duplicate CBAA K across roots. contract / DUPLICATE_CBAA_BUDGET_CONFIGURATION. Always prints OBSERVED_SEND_BYTE_CALIBRATION_ONLY_NOT_HARD_CAPPED.
- main: experimental CLI, 3 seeds, p=0/.30/.50, 100R/50T, tolerance=.10 by default.

New tests/test_cbaa_budget_comparison.py uses synthetic 2R2T/3 seeds data, checks selection by p0 traffic even when that configuration has LOWER success, raw immutable SHA256, p-specific mismatch, source columns and key coverage, physical send/receive counts, no output overwrite, collision guard, duplicate CBAA budgets and original p0 Greedy correctness. Existing E2/CBAA protocol owners, their original runner code, historical 100-seed evidence and canonical §13-18 are not modified.

### 19.4 Reproducible Mac E9A pilot commands

First, from project root where the original 100R/50T pure25 RAW and CBAA 20-round pilot exist:

    git pull
    python3 -m unittest discover -s tests -v
    python3 -m experiments.compare_cbaa_budget --cbaa-roots results/e8_cbaa_100r50t_pilot --output-root results/e9_cbaa_budget_calibration_20only

That is an intentional preliminary single-choice traffic comparison, NOT proof of a near-budget match.

Then reuse the existing CBAA runner at different integer budgets without changing its algorithm:

    for K in 1 2 3 4 5 8 10; do
      python3 -m experiments.run_cbaa_baseline --robots 100 --tasks 50 --seeds 3 --loss-probabilities 0,0.30,0.50 --max-iterations "$K" --output-root "$(printf 'results/e8_cbaa_budget%s_100r50t_smoke' "$K")" || break
    done

Then run a NEW E9A report root with all 7 new K sources and the original 20-round pilot:

    python3 -m experiments.compare_cbaa_budget --robots 100 --tasks 50 --seeds 3 --loss-probabilities 0,0.30,0.50 --tolerance 0.10 --cbaa-roots results/e8_cbaa_budget1_100r50t_smoke results/e8_cbaa_budget2_100r50t_smoke results/e8_cbaa_budget3_100r50t_smoke results/e8_cbaa_budget4_100r50t_smoke results/e8_cbaa_budget5_100r50t_smoke results/e8_cbaa_budget8_100r50t_smoke results/e8_cbaa_budget10_100r50t_smoke results/e8_cbaa_100r50t_pilot --output-root results/e9_cbaa_budget_calibration_3seed

Never run those into existing source roots or overwrite past reports. Read budget_options.csv for the p0-only selected K and its traffic mismatch; budget_curve.csv for ALL curves and observed near-budget flags; budget_per_seed.csv for individual outcome/byte cost, and manifest.json for immutable SHA provenance. Do not present K20 or a mismatched K as an equal-resource experimental result.

### 19.5 Future separate E9B hard-cap concern

E9B must implement actual sender-side byte budgeting BEFORE physical transmission in the real original network/coordination owners (without creating a second voting state machine), with recorded budget-exhaustion/incomplete-task semantics and consistent accounting for BOTH algorithms. E9A cannot approximate runtime-aborted assignments from completed historical runs. Proper identical channel/reliable-control assumptions, bandwidth, and distributed stop/deadline handling also remain separate future concerns. No formal paper-level equal-budget success superiority is established by E9A.
