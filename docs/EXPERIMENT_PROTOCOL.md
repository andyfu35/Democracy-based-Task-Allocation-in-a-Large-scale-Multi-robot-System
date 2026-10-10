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
