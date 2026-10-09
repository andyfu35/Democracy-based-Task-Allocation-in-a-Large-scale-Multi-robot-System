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
