# Democracy-based Task Allocation in a Large-scale Multi-robot System

This repository contains the reproducible benchmark and experimental record for a **leaderless, fully decentralized, quorum-based multi-robot task-allocation protocol** designed to remain useful under packet loss.

Target venue: **IEEE Robotics and Automation Letters (RA-L)**.

> Claim boundary: the **task-allocation decision process** is fully decentralized and leaderless. Task dissemination is assumed reliable in the primary protocol. Executor selection does not use a central solver, central vote counter, auctioneer, or permanent leader.

---

## 1. Protocol studied in this repository

For each allocation epoch, let the eligible robot set be \(\mathcal R\) with \(|\mathcal R|=N\).

1. **Reliable task dissemination**  
   Every eligible robot receives the same task announcement.

2. **Local cost computation**  
   Robot \(i\) independently computes its own cost \(c_{ij}\) for task \(j\).

3. **Peer cost announcement**  
   Each robot announces its cost to peers. Peer-to-peer cost messages may be lost.

4. **Independent local candidate selection**  
   Each robot selects the lowest-cost candidate visible in its own local view.

5. **Direct voting**  
   Each robot sends at most one vote per task per round directly to its selected candidate. Vote messages may be lost.

6. **Strict-majority quorum**  
   The quorum is fixed from the common eligible set:
   \[
   Q=\left\lfloor\frac{N}{2}\right\rfloor+1.
   \]
   A robot may commit only after receiving at least \(Q\) distinct votes for the same task and round.

7. **Winner announcement / commit**  
   The winner announces its commit to peers. Commit delivery may be made lossy in experiments that explicitly test commit loss.

8. **Timeout and reallocation**  
   If no valid commit is established before the deadline, the task returns to allocation in a new round.

### Protocol invariants

- One robot casts at most one vote per `(task_id, round_id)`.
- Duplicate/retransmitted votes from the same voter count once.
- Votes from stale rounds are rejected.
- Every robot uses the same fixed eligible set and therefore the same quorum.
- Strict majority implies at most one valid quorum winner per task/round.
- The primary assignment benchmark uses one-to-one allocation per epoch:
  \[
  \sum_j x_{ij}\le1,\qquad \sum_i x_{ij}\le1.
  \]

---

## 2. Experimental principles

All algorithms must be evaluated on the **same paired scenarios**.

For seed \(s\), the benchmark generates one immutable scenario:
\[
S_s=(\text{robot states},\text{task states},\text{ground-truth costs},\text{network trace}).
\]

Every algorithm receives the same scenario and, where applicable, the same communication trace.

Primary statistical protocol:

- **100 paired seeds per condition** unless an experiment explicitly says otherwise.
- Store raw per-seed records; never keep only aggregated means.
- Report **mean and 95% confidence interval** for approximately symmetric metrics.
- Report **median and IQR** for strongly skewed latency distributions when appropriate.
- Prefer paired differences against CoopMind/Democracy-based allocation when comparing methods.
- Randomness must be seed-addressable and reproducible.
- Baselines must not generate their own easier or different scenarios.

---

## 3. Common metrics

### Assignment success rate
\[
ASR=\frac{N_{\text{successfully assigned tasks}}}{N_{\text{tasks}}}.
\]

### Optimality gap
Let \(J^*\) be the centralized Hungarian oracle cost and \(J\) the evaluated method:
\[
Gap=\frac{J-J^*}{J^*}\times100\%.
\]

### Optimal solution rate
A run is counted as optimal when \(|J-J^*|<\epsilon\).

### Decision latency
\[
T_{decision}=T_{commit}-T_{task\ announcement}.
\]

### Computation time
Measured separately from simulated network delay.

### Communication overhead
Record all of:

- attempted messages
- received messages
- attempted bytes
- received bytes
- message count by type: cost / vote / commit

### Retry and timeout behavior

- mean allocation rounds per task
- timeout rate
- tasks unresolved at experiment horizon

### Safety diagnostics

These are correctness failures, not ordinary performance metrics:

- multiple valid winners
- duplicate execution
- duplicate vote counted
- stale-round vote accepted
- inconsistent quorum denominator

All safety failures must include the first failing **owner / function / category / code**.

---

# 4. Paper experiment roadmap

The roadmap is intentionally ordered. We complete and validate one experiment before implementing the next.

## E0 — Protocol Correctness Preflight

**Purpose:** prove that the implementation matches the protocol before comparing algorithms.

Primary condition:

- packet loss = 0%
- multiple robot/task sizes
- 100 paired seeds per size

Checks:

- zero multiple-winner events
- zero duplicate execution
- zero duplicate-vote counting
- zero stale-round acceptance
- deterministic replay from the same seed
- initial optimality gap against centralized Hungarian oracle

**Paper role:** engineering validation / supplementary unless a protocol property becomes a main result.

### E0 result record

Status: **LOCAL FORMAL RUN COMPLETE — RAW DATA PENDING GIT COMMIT**

Implementation state through: `7082518a798c840e6c76d785035379864dd1f97b`  
README result record: `pending current commit`  
Date: `2026-10-09`  
Local raw data: `results/e0_protocol_correctness/raw/e0_20261009T130507Z.csv`  
Local summary: `results/e0_protocol_correctness/summary.csv`  
Figures: `results/e0_protocol_correctness/figures/`

Local verification:

- unit tests: **5/5 passed**
- total scenarios: **500**
- assignment success rate: **1.000000 in every tested condition**
- safety failures: **0**
- deterministic replay failures: **0**

| Robots | Tasks | Seeds | Mean optimality gap | 95% CI half-width | ASR | Safety failures | Replay failures |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 5 | 100 | 4.097006% | +/-1.252083% | 1.000000 | 0 | 0 |
| 25 | 10 | 100 | 5.062453% | +/-1.086419% | 1.000000 | 0 | 0 |
| 50 | 30 | 100 | 11.313390% | +/-1.436862% | 1.000000 | 0 | 0 |
| 100 | 50 | 100 | 8.626984% | +/-0.849275% | 1.000000 | 0 | 0 |
| 100 | 100 | 100 | **35.119499%** | +/-1.524564% | 1.000000 | 0 | 0 |

**Interpretation / notes:**  
E0 passes the protocol-correctness objective: every tested task was assigned, no recorded safety invariant failed, and deterministic replay passed. However, the current deterministic task-order sequential allocation is **not near-optimal at high assignment saturation**. The 100-robot / 100-task condition is 35.12% above the centralized Hungarian oracle on average even with 0% packet loss. This is therefore an algorithmic-quality finding, not a packet-loss or protocol-safety failure.

Before claiming near-optimality in the paper, the allocation proposal stage must be reconsidered or the paper claim must explicitly accept this nominal-quality trade-off. The canonical protocol is **not changed by this result record**.

---

## E1 — Nominal Performance, 0% Packet Loss

**Purpose:** measure assignment quality and cost when communication is ideal.

Methods:

- Centralized Hungarian — oracle/reference
- Greedy — simple reference
- CBAA — classical decentralized auction
- ACBBA — asynchronous consensus/bundle baseline
- DHBA — decentralized Hungarian-based baseline
- Democracy-based allocation — ours

Primary measurements:

- optimality gap
- optimal solution rate
- decision latency
- computation time
- messages and bytes

### E1 result record

Status: **PLANNED**

Commit: `TBD`  
Raw data: `results/e1_nominal/raw/`  
Summary: `results/e1_nominal/summary.csv`

| Method | Gap (%) | Optimal rate | Decision latency | Messages | Bytes |
|---|---:|---:|---:|---:|---:|
| Hungarian | TBD | TBD | TBD | TBD | TBD |
| Greedy | TBD | TBD | TBD | TBD | TBD |
| CBAA | TBD | TBD | TBD | TBD | TBD |
| ACBBA | TBD | TBD | TBD | TBD | TBD |
| DHBA | TBD | TBD | TBD | TBD | TBD |
| Ours | TBD | TBD | TBD | TBD | TBD |

**Interpretation / notes:**  
_TBD._

---

## E2 — Bernoulli Packet-Loss Robustness — Main Experiment

**Purpose:** test the primary claim that performance degrades gracefully as unreliable peer communication increases.

Packet-loss sweep:
\[
p_{loss}\in\{0,0.1,0.3,0.5,0.7,0.9\}.
\]

Primary decentralized methods:

- CBAA
- ACBBA
- DHBA
- Democracy-based allocation

Hungarian is retained as a centralized oracle/reference, not treated as a lossy distributed protocol.

Primary plots:

- packet loss vs assignment success rate
- packet loss vs optimality gap
- packet loss vs decision latency
- packet loss vs transmitted bytes
- packet loss vs retries / timeout rate

### E2 result record

Status: **PLANNED**

Commit: `TBD`  
Raw data: `results/e2_packet_loss/raw/`  
Summary: `results/e2_packet_loss/summary.csv`

| Loss | CBAA ASR | ACBBA ASR | DHBA ASR | Ours ASR |
|---:|---:|---:|---:|---:|
| 0% | TBD | TBD | TBD | TBD |
| 10% | TBD | TBD | TBD | TBD |
| 30% | TBD | TBD | TBD | TBD |
| 50% | TBD | TBD | TBD | TBD |
| 70% | TBD | TBD | TBD | TBD |
| 90% | TBD | TBD | TBD | TBD |

**Interpretation / notes:**  
_TBD._

---

## E3 — Loss-Source Analysis

**Purpose:** separate the effect of losing different protocol messages.

Conditions:

1. cost-message loss only
2. vote-message loss only
3. commit-message loss only
4. all peer messages lossy

Measure:

- assignment success rate
- optimality gap
- retry count
- timeout rate
- safety diagnostics

This experiment replaces a large artificial “remove voting” ablation. The research question is **which communication failure damages which protocol property**.

### E3 result record

Status: **PLANNED**

Commit: `TBD`  
Raw data: `results/e3_loss_source/raw/`  
Summary: `results/e3_loss_source/summary.csv`

| Loss source | ASR | Gap (%) | Retries | Timeout rate | Safety failures |
|---|---:|---:|---:|---:|---:|
| Cost only | TBD | TBD | TBD | TBD | TBD |
| Vote only | TBD | TBD | TBD | TBD | TBD |
| Commit only | TBD | TBD | TBD | TBD | TBD |
| All peer messages | TBD | TBD | TBD | TBD | TBD |

**Interpretation / notes:**  
_TBD._

---

## E4 — Robot Scalability

**Purpose:** support or reject the scalability claim.

Primary sweep:
\[
N_R\in\{10,25,50,100,200\}.
\]

Primary network condition:

- Bernoulli packet loss = 30%

Use a controlled task/robot ratio defined in the experiment config.

Compare:

- CBAA
- ACBBA
- DHBA
- Democracy-based allocation

Measure:

- decision latency
- computation time
- messages / bytes
- optimality gap
- assignment success rate

### E4 result record

Status: **PLANNED**

Commit: `TBD`  
Raw data: `results/e4_robot_scalability/raw/`  
Summary: `results/e4_robot_scalability/summary.csv`

| Robots | Method | Gap (%) | ASR | Decision latency | Bytes |
|---:|---|---:|---:|---:|---:|
| 10 | TBD | TBD | TBD | TBD | TBD |
| 25 | TBD | TBD | TBD | TBD | TBD |
| 50 | TBD | TBD | TBD | TBD | TBD |
| 100 | TBD | TBD | TBD | TBD | TBD |
| 200 | TBD | TBD | TBD | TBD | TBD |

**Interpretation / notes:**  
_TBD._

---

## E5 — Task-Load Scalability

**Purpose:** measure performance as task workload increases with fleet size fixed.

Primary condition:

- robots = 100
- Bernoulli packet loss = 30%

Task sweep:
\[
N_T\in\{5,10,20,30,50,75,100\}.
\]

Compare the same decentralized methods as E4.

### E5 result record

Status: **PLANNED**

Commit: `TBD`  
Raw data: `results/e5_task_load/raw/`  
Summary: `results/e5_task_load/summary.csv`

| Tasks | Method | Gap (%) | ASR | Decision latency | Bytes |
|---:|---|---:|---:|---:|---:|
| 5 | TBD | TBD | TBD | TBD | TBD |
| 10 | TBD | TBD | TBD | TBD | TBD |
| 20 | TBD | TBD | TBD | TBD | TBD |
| 30 | TBD | TBD | TBD | TBD | TBD |
| 50 | TBD | TBD | TBD | TBD | TBD |
| 75 | TBD | TBD | TBD | TBD | TBD |
| 100 | TBD | TBD | TBD | TBD | TBD |

**Interpretation / notes:**  
_TBD._

---

## E6 — Bursty Communication Loss

**Purpose:** test whether conclusions from independent Bernoulli loss remain valid under bursty communication failures.

Primary model:

- Gilbert-Elliott two-state channel
- Good and Bad states with experiment-controlled transition probabilities and loss rates

Compare the strongest decentralized baselines from E2 against Democracy-based allocation.

Measure the same core metrics as E2.

### E6 result record

Status: **PLANNED**

Commit: `TBD`  
Raw data: `results/e6_burst_loss/raw/`  
Summary: `results/e6_burst_loss/summary.csv`

| Method | Channel config | ASR | Gap (%) | Latency | Bytes |
|---|---|---:|---:|---:|---:|
| TBD | TBD | TBD | TBD | TBD | TBD |

**Interpretation / notes:**  
_TBD._

---

# 5. Result-storage policy

Raw experimental evidence is never overwritten.

Recommended layout:

```text
results/
  e0_protocol_correctness/
    raw/
    summary.csv
    figures/
  e1_nominal/
    raw/
    summary.csv
    figures/
  e2_packet_loss/
    raw/
    summary.csv
    figures/
  e3_loss_source/
  e4_robot_scalability/
  e5_task_load/
  e6_burst_loss/
```

Each formal run should save:

- git commit SHA
- experiment configuration
- seed list
- algorithm/version identifier
- per-seed raw metrics
- aggregated summary
- environment information
- runtime timestamp

The tables in this README are the **paper-facing experiment ledger**. Formal results should be copied here only from committed raw/summary data.

---

# 6. Planned implementation order

- [x] E0 — protocol correctness implementation and local 100-seed run (raw data git commit pending)
- [ ] E1 — nominal comparison
- [ ] E2 — Bernoulli packet-loss robustness
- [ ] E3 — loss-source analysis
- [ ] E4 — robot scalability
- [ ] E5 — task-load scalability
- [ ] E6 — burst-loss robustness

Do not start the next experiment until the previous experiment has:

1. reproducible code,
2. tests,
3. raw output,
4. summary output,
5. README result update,
6. continuity record.

---

# 7. Baseline literature to reproduce faithfully

External algorithms must be implemented from their canonical publications rather than from ad-hoc approximations.

Priority baselines:

1. **CBAA / CBBA family** — consensus-based decentralized auctions.
2. **ACBBA** — asynchronous consensus-based bundle allocation.
3. **DHBA** — decentralized Hungarian-based task allocation.
4. **Centralized Hungarian** — oracle/reference.
5. **Greedy** — transparent simple baseline.

A literature note and exact implementation assumptions will be added before each external baseline is coded.

---

# 8. Current status

Repository initialized for the RA-L experimental campaign.

**E0 implementation and local 100-seed run are complete.** The locally generated raw CSV and summary still need to be committed from the machine that ran the experiment.

Local run sequence:

```bash
git pull
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m experiments.run_e0 --seeds 100
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

After the run, preserve:

- `results/e0_protocol_correctness/raw/e0_<timestamp>.csv`
- `results/e0_protocol_correctness/summary.csv`

and copy the formal summary into the E0 result record above.

**Decision gate before E1:** E0 revealed a 35.12% nominal optimality gap at 100 robots / 100 tasks. Do not silently change the canonical protocol. Decide whether to preserve sequential per-task voting as the paper algorithm or redesign the proposal stage to account for the complete multi-task assignment before implementing external baselines.
