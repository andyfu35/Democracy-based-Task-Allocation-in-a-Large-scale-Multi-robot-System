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
3. peer cost messages are transmitted;
4. robot \(i\) constructs local matrix \(\hat C_i\);
5. unknown/unreceived entries are explicitly represented as unavailable and never silently replaced by ground-truth data;
6. robot \(i\) runs Hungarian on its local feasible matrix;
7. each local assignment becomes one task-level vote per proposed robot;
8. votes are sent directly to proposed executors;
9. task \(j\) commits to robot \(k\) only when robot \(k\) receives strict majority
   \[
   Q=\lfloor N/2\rfloor+1;
   \]
10. votes are unique by voter/task/round;
11. stale votes are rejected;
12. if the required assignment cannot be committed before timeout, the round fails and is retried.

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
- raw per-message network event log;
- per-seed metrics;
- aggregate summary.
