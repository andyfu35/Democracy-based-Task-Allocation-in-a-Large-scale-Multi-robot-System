# Democracy-based Task Allocation in a Large-scale Multi-robot System

**Research goal:** fully decentralized multi-robot task allocation under unreliable communication, with reproducible experiments on assignment correctness, packet loss, coordination time, and alternative algorithms. **Target venue:** IEEE Robotics and Automation Letters (RA-L).

> **Measurement boundary.** All reported communication times are **simulated protocol allocation/stop time**, not Python execution time or measurements from a 100-robot wireless deployment. Sender Bytes are attempted **application-layer** payload (including dropped packets). Rady provides real application-delay traces, but the shared **144 Mbps radio service is a hypothetical model**, not verified Wi-Fi MAC/PHY or ns-3. Voting pays reliable Commit; other algorithms use different native stopping conditions.

## Research map

There are **four experiment families**. Internal development IDs are kept out of this overview and documented separately in the [historical study index](docs/EXPERIMENT_LEGACY_INDEX.md).

| Family | Scientific question | Accepted evidence |
|---|---|---|
| **[A. Correctness](#a-correctness-and-distributed-agreement)** | Does decentralized assignment preserve a controlled optimal decision, and how costly is agreement? | Perfect-information and trace-bootstrap controlled Hungarian experiments |
| **[B. Packet loss](#b-packet-loss-resilience-and-communication-traffic)** | How does packet loss affect native completion guarantees and attempted sender Bytes? | 52-rate, 100-seed robustness sweep of Voting vs original CBAA |
| **[C. Time](#c-coordination-time-and-deadline-design)** | How much delay comes from waiting and deadlines versus the radio model? | 30% Loss adaptive-deadline experiment and separate zero-loss timing control |
| **[D. Algorithms](#d-algorithm-comparison-and-task-capacity)** | How do native Voting, CBAA, Price Auction and CBBA compare under common capacity? | Five-series single-task comparison; separate capacity-four multi-task study |

### Implementation ownership

| Concern | Owning module |
|---|---|
| Task announcement and voting | [Task announcements](democracy_mrta/task_information.py), [Voting coordination](democracy_mrta/coordination.py), [multi-task Voting](democracy_mrta/voting_multitask.py) |
| Alternative allocators | [Original CBAA](democracy_mrta/cbaa.py) and [original CBBA](democracy_mrta/cbba_multitask.py) (current branch); [Price Auction (historical source branch)](https://github.com/andyfu35/Democracy-based-Task-Allocation-in-a-Large-scale-Multi-robot-System/blob/experiment/e9l-distributed-price-auction/democracy_mrta/price_auction.py) |
| Transport, loss, modeled time | [Network](democracy_mrta/network.py), [native multi-task packets](democracy_mrta/multitask_wire.py) |
| Scene / route / independent assessment | [Single-task scenes](democracy_mrta/scenario.py), [capacity-aware scenes](democracy_mrta/multitask_scenario.py), [route audit](democracy_mrta/multitask_evaluation.py) |
| Reproduction | [Experiment runners](experiments/), [canonical protocol](docs/EXPERIMENT_PROTOCOL.md), [change continuity](docs/CHANGE_CONTINUITY.md) |

**Architecture:** task announcement → each robot's local Cost / route utility → method-owned voting, bidding, auction or bundle consensus → externally audited assignment and physical message ledger. The observer **does not** inject a global solution or constitute a paid distributed termination protocol.

## A. Correctness and distributed agreement

**Scientific question:** holding the **Hungarian optimizer fixed**, does decentralized coordination preserve a correct assignment?

| Completed experiment | Formal condition | Verified finding |
|---|---|---|
| Perfect-information correctness | 5 robot/task scales × 100 Seeds, zero loss | **500/500 complete**, zero optimality gap and reference mismatches |
| Trace-sampled agreement overhead | 2,000 original records, 20 cells | At 100 robots/50 tasks, Democracy-Hungarian takes **796.2 ms** for global agreement and **201,400 B**; Leader-Hungarian **477.4 ms** and **41,600 B** |

The study establishes correctness when information is complete, but decentralized agreement adds communication. Its Hungarian-controlled results **must not be pooled** with Greedy Voting versus CBAA or CBBA optimization-quality claims.

**Original evidence:** [correctness raw](results/e0_protocol_correctness/raw/e0_corrected_20261009T141508Z.csv) / [summary](results/e0_protocol_correctness/summary.csv); [agreement raw](results/e1_latency/raw/e1_20261009T144026Z.csv) / [summary](results/e1_latency/summary.csv).

The earlier one-round lossy Hungarian Vote pilot did not receive full per-vote acceptance. It is **archived, not an outstanding requirement** for these two completed claims. [Historical study index](docs/EXPERIMENT_LEGACY_INDEX.md).

## B. Packet-loss resilience and communication traffic

**Scientific question:** under the same task scenario, how do **native protocol completion** and actual attempted sender Bytes change as packet loss rises?

**Formal setting:** 100 robots/50 tasks; 52 loss probabilities × 100 Seeds × 2 methods = **10,400 original executions**, independent per-receiver loss, original synthetic communication timing. The plot combines **two metrics from the same evidence cohort**. The Bytes axis uses logarithmic kB.

![Packet-loss sweep: Voting and original CBAA native completion and sender Bytes](docs/figures/e9e_dense/formal/primary_loss_completion_and_bytes.svg)

| Receiver loss | Voting: paid full Commit | CBAA: local certificate | Attempted sender Bytes |
|---|---:|---:|---|
| **30%** | 100/100 | 100/100 | Voting **164,750 B** vs CBAA **838,160 B**; Voting uses **80.34% fewer** |
| **55%** | 0/100 | 100/100 | Voting hit its configured guard without full Commit |
| **96%** | 0/100 | 0/100 | CBAA external observer still saw agreement, **not** locally provable termination |

**Important:** CBAA's observer consensus is not a local certificate and neither is equivalent to Voting's fully charged reliable Commit. Guard-bound outcomes are **not theoretical thresholds**. This group uses the older synthetic time model; its time cannot be combined with the later Rady+144 Mbps model.

**Evidence:** [104-row original loss source](docs/figures/e9e_dense/formal/summary_by_loss.csv) · [original source manifest](docs/figures/e9e_dense/formal/publication_manifest.json) · [combined-chart source identity](docs/figures/e9e_dense/formal/primary_loss_completion_and_bytes_manifest.json).

## C. Coordination time and deadline design

**Scientific question:** does the communication delay come mostly from waiting for late Cost / Vote packets or from modeled shared-medium packet service?

### Adaptive deadlines under 30% packet loss

**Formal setting:** robots=tasks, 5–100 in steps of 5, 100 Seeds per size; both Cost and Vote drop probabilities are **30%**. Original baseline and revised deadline policy use matched settings.

![Fixed and adaptive deadline policy with 30 percent Cost and Vote loss](docs/figures/e9i_cost30/formal/fig02_time_vote30.svg)

At **100 robots/100 tasks**, the old fixed received-plurality deadline averaged **71.918 s** versus **20.132 s** with guarded one-time Cost and adaptive Vote deadlines (**72.01% lower modeled time**). Both compared arms completed 100/100 Seeds at that size; this **does not** imply 72% less sender payload or better optimality. [20-point original source](docs/figures/e9i_cost30/formal/formal_20point_plot_data.csv) · [source manifest](docs/figures/e9i_cost30/formal/formal_publication_manifest.json).

### Radio-model sensitivity — separate control

With 100 robots, zero application-layer loss, and a **fixed 609.113 ms task wait**, the Rady-delay-only model yielded **68.143 s**, versus **68.224 s** with the *assumed* 144 Mbps shared radio (**81.722 ms** more). This is a **zero-loss control**, not an empirical 100-robot Wi-Fi result or a second curve of the 30%-Loss deadline experiment. [Source](docs/figures/e9g_wifi/formal/scaling_20points_verified.csv) · [manifest](docs/figures/e9g_wifi/formal/publication_manifest.json).

## D. Algorithm comparison and task capacity

**Scientific question:** on common task-capacity and geometry, what are the trade-offs among original assignment algorithms?

### Five-method single-task assignment

**Formal presentation cell:** robots=tasks=5–100 in steps of 5, **capacity 1**, 30% receiver loss, 100 scenario Seeds per size. The original Voting, CBAA and Price Auction curves are **frozen previously executed results** (6,000 method cases); Voting Multi-task and CBBA are **4,000 newly executed method cases**. Do not describe this as a fresh five-way rerun from one executable commit. Methods retain native packet types, local decisions and different endpoint evidence.

![Five-method capacity-one comparison: modeled stop time, sender Bytes and supported completion](docs/figures/e9n/formal/primary_five_method_time_bytes_success.svg)

| At 100 robots/100 tasks, capacity 1 | Voting | Original CBAA | Price Auction | Voting Multi-task | Original CBBA |
|---|---:|---:|---:|---:|---:|
| Modeled stop time | 20.132 s | 13.647 s | 135.828 s | 101.919 s | **12.368 s** |
| Attempted sender traffic | 255.50 kB | 2,693.04 kB | 353.94 kB | 305.39 kB | 6,488.06 kB |
| Full completion **supported in plotted input** | — | — | 78/100 | **100/100** | **100/100** |

**— means unavailable in the frozen per-size plotted source, not failed.** Auction time includes guard-censored cases. In the two new capacity-one methods, CBBA used **21.24× more Bytes** while its modeled observer stop was **8.24× shorter**. Neither quantity establishes equal paid distributed finalization or measured RF performance.

For **assignment quality**, the original Price Auction's Hungarian Cost ratios are compared with Voting and CBAA **only on the same 78 successful Auction Seeds**; these ratios are not comparable with the CBBA/Voting Multi-task path-discounted reward. [Original conditional-quality figure](docs/figures/e9l_price/formal/primary_three_algorithm_completion_and_quality.svg).

**Evidence:** [complete 4,000-row new-method audit](docs/E9N_FORMAL_100SEED.md) · [original combined 100-row source](docs/figures/e9n/formal/original_five_method_common_cap1_source.csv) · [original auction study](docs/E9L_FORMAL_100SEED.md) · [original CBAA source manifest](docs/figures/e9j_cbaa/formal/source_manifest.json).

### Multi-task assignment — separate capacity-four cohort

**Formal cell:** 25 robots, 100 tasks, maximum **4 tasks per robot**, 30% loss, 100 paired Seeds; corrected full source ZIP, route and packet ledgers independently verified.

| Capacity-four metric | Voting Multi-task | Original CBBA |
|---|---:|---:|
| Assignment complete | **100/100** | **100/100** |
| Modeled allocation/stop | 63.023 s | **6.878 s** |
| Sender payload | **116.83 kB** | 1,006.87 kB |
| Total robot travel | 1,319.76 m | **1,209.48 m** |
| Longest robot route (makespan) | **134.55 s** | 148.64 s |

Total route length and longest route duration are **different** objectives; physical route makespan is not allocation time. This capacity-four cohort is deliberately **not** a point on the capacity-one plot. [Source-verified multi-task report](docs/E9M_CORRECTED_ORIGINAL_ZIP_AUDIT_100SEED.md).

## Remaining acceptance work — a bounded closure plan

The accepted evidence already covers A/B and the **simulated** portions of C/D. **We are not opening a new backlog for every historical pilot.** See the [two-priority closure plan](docs/RESEARCH_CLOSURE_PLAN.md) for conditions and a stop rule.

| Priority | Need | Smallest useful follow-up |
|---|---|---|
| **1 — Common measurement boundary** | Current five-method time and cost curves come from different original source commits, optimization scores and **native termination conditions** | Rerun all **five original algorithms without protocol modification** at one preregistered N=T/C1, 30%-Loss cohort, reporting the **same external first-feasible-assignment event**, original native stop, original Bytes and a shared Euclidean/Hungarian audit. Start with N=25,50,100 × 100 paired Seeds (1,500 algorithm cases). |
| **2 — Validate modeled communication time** | Measured Rady application delay plus hypothetical shared 144Mbps service is not a packet-level or physical wireless validation | One bounded network timing validation (packet-level or controlled multi-host replay), preserving real unicast/broadcast size and retry effects. Needed **only if the paper claims real network latency**, not for explicitly labeled model comparisons. |

**Conditional only:** a second independently verified capacity-four scale, for example 50 robots/200 tasks, is needed **only** if we claim multi-task scaling beyond the verified 25/100 case. Otherwise freeze the current multi-task evidence. Do **not** revive historical one-round Vote controls, sender-size checks or unfinished deadline factorial studies just because their internal IDs exist.

## Reproducibility, archives and limitations

- [Historical internal study IDs, names and status](docs/EXPERIMENT_LEGACY_INDEX.md) · [Detailed historical results](docs/EXPERIMENT_RESULTS_ARCHIVE_20261012.md) · [prior README snapshot](docs/README_PRE_ABCD_20261013.md).
- [Cross-experiment audit](docs/EXPERIMENT_RESULTS_AUDIT_20261012.md) · [canonical protocol](docs/EXPERIMENT_PROTOCOL.md) · [change continuity](docs/CHANGE_CONTINUITY.md) · [bibliography](docs/references/e9g_wifi_timing.bib).
- [Original single-task source audit](docs/E9N_FORMAL_100SEED.md) · [original multi-task source audit](docs/E9M_CORRECTED_ORIGINAL_ZIP_AUDIT_100SEED.md). Original ZIPs are retained unchanged in the user's personal Library with documented SHA-256 identities.

**Comparison boundaries:** *method-native* modeled endpoint ≠ shared paid terminal guarantee; synthetic-timing loss study ≠ Rady radio-proxy experiment; capacity 1 ≠ capacity 4; aggregate historical source ≠ newly rerun paired original source. These limits are preserved in the reports. No actual 100-robot Wi-Fi deployment is claimed.
