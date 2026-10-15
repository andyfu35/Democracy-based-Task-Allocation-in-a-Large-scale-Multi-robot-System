# Democracy-based Task Allocation in a Large-scale Multi-robot System

**Language:** **English** | [繁體中文](README.zh-TW.md)

**Research goal:** fully decentralized multi-robot task allocation under unreliable communication, with reproducible experiments on assignment correctness, packet loss, coordination time, and alternative algorithms. **Target venue:** IEEE Robotics and Automation Letters (RA-L).

> **Measurement boundary.** All reported communication times are **simulated protocol allocation/stop time**, not Python execution time or measurements from a 100-robot wireless deployment. Sender Bytes are attempted **application-layer** payload (including dropped packets). Rady provides real application-delay traces, but the shared **144 Mbps radio service is a hypothetical model**, not verified Wi-Fi MAC/PHY or ns-3. Voting pays reliable Commit; other algorithms use different native stopping conditions.

## Research map

There are **four experiment families**. Internal development IDs are kept out of this overview and documented separately in the [historical study index](docs/EXPERIMENT_LEGACY_INDEX.md).

| Family | Scientific question | Accepted evidence |
|---|---|---|
| **[A. Correctness](#a-correctness-and-distributed-agreement)** | Does decentralized assignment preserve a controlled optimal decision, and how costly is agreement? | Perfect-information and trace-bootstrap controlled Hungarian experiments |
| **[B. Packet loss](#b-packet-loss-resilience-and-communication-traffic)** | How does packet loss affect single-round versus iterative assignment success, Bytes, modeled stop time and assignment cost? | P2D/P2E two four-panel 100-seed comparisons, 0–90% loss |
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

**Current 100-seed primary comparison (2026-10-15).** The native P2D/P2E studies use **100 robots, 100 tasks, capacity 1**, receiver packet loss 0–90% in 10% increments, and the same **100 paired seeds** per loss level. We compare **Proposed (Single-Round)** versus **Centralized (One-Shot)** as one-decision methods, and **Proposed (Multi-Round)** versus **native CBAA / CBBA** with the same Centralized result retained as a one-shot reference. There are **5,000 unique method × loss × seed cases**: 2,000 new P2E Proposed, 1,000 new P2D Centralized, and 2,000 original SHA-verified P2 CBAA/CBBA runs reused without rerunning. The 1,000 additional P2D historical Proposed rows exactly match the P2E Multi-Round results and are **not double-counted**. Independent P2D/P2E audit: **73,463 checks, 0 errors**.

### Figure 1 — One-shot decision comparison

![Figure 1: One-shot methods, terminal conflict-free task coverage, emitted application Bytes, modeled stop and cost increase](docs/figures/p2de/formal/figure1_one_shot_curve.svg)

**Proposed (Single-Round)** permits only one voting/decision epoch; **Centralized (One-Shot)** has one lossy Cost unicast per remote robot and one coordinator decision, with **no Cost retransmission**. At PL0 both deliver complete assignments in 100/100 seeds. At PL10, their **mean conflict-free terminal task coverage** is **96.36%** and **90.29%**, despite strict native full-completion counts of only **1/100** and **0/100**. At PL90, coverage remains **62.11%** for Proposed Single-Round and **10.54%** for Centralized. Incomplete runs are measured as partial progress, not misreported as full success. Their different packet topologies mean *one-shot* is a decision-budget grouping, **not equal packet counts or equivalent end-to-end reliability**.

### Figure 2 — Iterative coordination with Centralized reference

![Figure 2: Proposed Multi-Round, CBAA, CBBA and one-shot Centralized reference across packet loss](docs/figures/p2de/formal/figure2_iterative_curve.svg)

Proposed Multi-Round makes new allocation/voting decisions (up to 300 native epochs), **not retransmissions of the original lost Cost frames**; CBAA and CBBA retain their native consensus and stopping rules (guard 160). Centralized is repeated in this plot only as a **one-shot reference**, not as an iterative consensus method. All curves connect **measured loss-grid points**, without smoothing or altered values. CBBA retains **95.16%** conflict-free observed coverage at PL80 and **71.90%** at PL90, even though its native full-completion rate there is 0/100. Those CBBA snapshots are **not a paid Commit or convergence certificate**.

| 90% packet loss · 100 seeds | Proposed Single-Round | **Proposed Multi-Round** | CBAA | CBBA | Centralized One-Shot |
|---|---:|---:|---:|---:|---:|
| **Terminal conflict-free task coverage (%)** | 62.11% | **100.00%** | 100.00% | 71.90%¹ | 10.54% |
| **Native full assignment success (strict)** | 0/100 | **100/100** | 100/100 | 0/100 | 0/100 |
| **Attempted sender payload (decimal kB)** | 99.42 | **105.67** | 14,135.60 | 56,343.95 | 84.43 |
| **Modeled native stop (s), all seeds** | 2.05 | **4.49** | 71.38 | 112.53 | 0.88 |
| **Cost increase (%) vs full-info Global Greedy** | — | **+5.04%** | 0.00% | — | — |

¹ CBBA coverage measures non-conflicting **final observer proposals**, not globally accepted Commit-backed assignments. Conflicting task claims are excluded, rather than resolving them without evidence.

In this **specific model and native guard budget**, CBAA maintains 100/100 native success at 90% loss, whereas CBBA has 0/100 at 80% and 90%; this is an empirical result, **not a theoretical packet-loss threshold**. Proposed Multi-Round and CBAA both fully finish at PL90, but Proposed uses **about 134× less** attempted sender application payload and has **about 15.9× shorter modeled native stop**; its native assignment cost is about **5.04% above** same-seed full-information Global Greedy. A shorter stop after failure (especially Centralized) **must not be read as faster successful completion**.

**Figure definitions and fair cost baseline.** The panels show **(a) mean terminal conflict-free task assignment coverage (%) across all 100 seeds**, **(b) attempted sender application payload (kB = 1,000 B, including lost SENDs)**, **(c) modeled native stop time (s, all seeds including failures)**, and **(d) native-success-only allocation cost increase (%)**. Cost is computed **per successful seed** as `100 × (actual Euclidean allocation cost / same-seed offline full-information Global Greedy cost − 1)`, then averaged over that method's successful seeds. The **black dashed 0% line** is the **same Full-Info Global Greedy reference for every method**, *not* each algorithm's own PL0 normalizer and *not* Hungarian optimum. Values below 0% are possible because Greedy is not a guaranteed global optimum. When no complete assignment exists, cost is **undefined and not plotted as zero**; Proposed Single-Round's PL10 quality has **n=1**.

**Coverage vs complete success.** Coverage counts each terminal Robot–Task pair *only when both its robot and task occur exactly once* in the final native observed snapshot, divides by 100 tasks and averages over all 100 paired seeds. No arbitrary winner is selected for duplicate claims (CBBA PL80 excludes an average 4.73 conflicting pair claims per seed; PL90 excludes 28.05). Proposed and Centralized partial assignments are paid native Commit-backed; CBAA/CBBA are original terminal observer snapshots without an equivalent paid Commit. Thus **coverage reflects conflict-free observed progress, not an equal distributed-termination guarantee**. Strict 100-of-100 complete success remains separately reported in the table.

**Scientific limitations.** The underlying Rady application-delay sample plus a **hypothetical shared 144 Mbps medium** measures modeled communication timing, **not field Wi-Fi/MAC/PHY**. Independent receiver loss applies to Cost/Vote while TASK/Score/Commit are modeled reliable; the CBAA/CBBA native observer/terminal guarantees and Proposed paid Commit are not interchangeable. The two figures show different allowed decision budgets, not a claim of equal number of packets, perfect protocol fairness, or universal centralized failure.

**Reproducible publication data:** [50-row plotted summary and sample denominators](docs/figures/p2de/formal/verified_50point_summary.csv) · [source SHA256s, calculation and caveats](docs/figures/p2de/formal/README.md) · [P2D canonical experiment](docs/EXPERIMENT_PROTOCOL.md#54-p2d--one-shot-centralized-method-and-full-info-greedy-comparison-2026-10-14) · [P2E canonical experiment](docs/EXPERIMENT_PROTOCOL.md#55-p2e--proposed-redecision-ab-one-vs-300-epochs-2026-10-15). The previous [P2-C four-method Price Auction figure](docs/figures/p2c/formal/p2c_packet_loss_four_panel.svg) and [full historical P2-C audit](docs/P2C_FORMAL_100SEED.md) remain archived, not removed or passed off as the new test.

## C. Coordination time and deadline design

**Historical-protocol figure:** the E9G/E9I deadline experiments here used earlier sequential-task Voting (or their stated original control), **not** the new P2-B batched Greedy Voting. Their source curves and data are preserved and must not be interpreted as the current batch-protocol latency across robot sizes. Updating these plots would require **new Voting-only runs at the original E9I sizes and seeds**, not rerunning unchanged native baselines.

**Scientific question:** does the communication delay come mostly from waiting for late Cost / Vote packets or from modeled shared-medium packet service?

### Adaptive deadlines under 30% packet loss

**Formal setting:** robots=tasks, 5–100 in steps of 5, 100 Seeds per size; both Cost and Vote drop probabilities are **30%**. Original baseline and revised deadline policy use matched settings.

![Fixed and adaptive deadline policy with 30 percent Cost and Vote loss](docs/figures/e9i_cost30/formal/fig02_time_vote30.svg)

At **100 robots/100 tasks**, the old fixed received-plurality deadline averaged **71.918 s** versus **20.132 s** with guarded one-time Cost and adaptive Vote deadlines (**72.01% lower modeled time**). Both compared arms completed 100/100 Seeds at that size; this **does not** imply 72% less sender payload or better optimality. [20-point original source](docs/figures/e9i_cost30/formal/formal_20point_plot_data.csv) · [source manifest](docs/figures/e9i_cost30/formal/formal_publication_manifest.json).

### Radio-model sensitivity — separate control

With 100 robots, zero application-layer loss, and a **fixed 609.113 ms task wait**, the Rady-delay-only model yielded **68.143 s**, versus **68.224 s** with the *assumed* 144 Mbps shared radio (**81.722 ms** more). This is a **zero-loss control**, not an empirical 100-robot Wi-Fi result or a second curve of the 30%-Loss deadline experiment. [Source](docs/figures/e9g_wifi/formal/scaling_20points_verified.csv) · [manifest](docs/figures/e9g_wifi/formal/publication_manifest.json).

## D. Algorithm comparison and task capacity

**Historical P1 benchmark, not current P2-B:** this archived P1 figure was executed under the earlier serialized Voting protocol, before batch Greedy. It also retains a five-method archival extension; **Voting Multi-task is not part of the current official four-method P2-B comparison**. All original P1 cases remain historical evidence. The current new batched Voting N=T=100 comparison is README B; other P1 sizes require separate matched Voting-only runs.

**Scientific question:** on common task-capacity and geometry, what are the trade-offs among original assignment algorithms?

### Five original algorithms — matched capacity-one, original 100 Seeds verified

**P1 formal original ZIP independently audited — zero data-integrity errors.** Same N=T=25,50,100, capacity **one**, packet Loss **30%** on each original method-native lossy packet, **100 paired Seeds per N**. All **five methods were newly run in the same source commit (1,500 original method cases)**, rather than mixing frozen historical three-algorithm averages with newer runs. An external observer records the first globally unique feasible assignment **after an originally incurred communication phase**; it neither adds messages nor stops or changes a robot. Native method-specific termination/guard is recorded **separately**.

![P1 verified: five native original algorithms, native stop, external first feasible, Bytes and same-success Hungarian cost](docs/figures/p1/formal/primary_matched_five_protocol_time_bytes_quality.svg)

| N=100; 30% Loss; 100 Seeds | Voting | Original CBAA | Price Auction | Voting Multi-task | Original CBBA |
|---|---:|---:|---:|---:|---:|
| **External first globally feasible (s)** | 20.132 | **7.898** | 119.400¹ | 101.919 | 11.539 |
| Original protocol modeled stop (s) | 20.132 | 13.647 | 135.828 | 101.919 | **12.368** |
| Attempted application sender (decimal kB) | **255.50** | 2,693.04 | 353.94 | 305.39 | 6,488.06 |
| **Native complete** | 100/100 | 100/100 | **78/100** | 100/100 | 100/100 |
| First feasible observable | 100/100 | 100/100 | 79/100 | 100/100 | 100/100 |
| Euclidean/Hungarian ratio² (lower better) | 1.3668 | 1.2348 | **1.1173** | 1.3673 | 1.2348 |

¹ Auction first-feasible time averages **79 observed Seeds**; 22 guard-limited failures remain in the **all-100-Seed native stop and sender Bytes**. Missing first-feasible timestamps are **not** imputed. ² Hungarian ratios are conditioned on the **same 78 Seeds where all five native methods completed**; this is explicitly different from the unconditional success counts.

**Key discovery — rankings reverse under a common observed event.** At 100 robots CBAA's first feasible assignment is **7.898 s**, ahead of CBBA **11.539 s in all 100 paired Seeds**, but CBBA reaches its **original native stop** sooner (**12.368 s** vs CBAA **13.647 s**). The paired mean CBAA−CBBA first-feasible difference is **−3.640 s** (10k paired-bootstrap 95% CI **[−3.939,−3.364]**). CBAA and CBBA produced **the exact same final assignment on all 300 N/Seed paired scenes**; CBBA transmitted **2.41×** the CBAA application Bytes at N100. Thus this observation isolates their packet and native stopping trade-off, not a change in CBAA/CBBA allocation quality.

**Completion and quality trade-off:** Price Auction has the lowest matched Hungarian cost ratio, but N100 native completion is just **78%**. Of the **1,500 complete original cases**, 1,476 natively completed and 1,478 ever formed a first externally feasible assignment. All **24 original native guard failures** belong to Auction (2 at N50, 22 at N100); two failed native endpoints already had an externally feasible snapshot, proving the two time/stop definitions cannot be substituted.

**Limits:** original Voting pays Score/Commit while CBAA, CBBA and Price Auction have native local/observer stopping; **first feasible is a read-only simulator event, not paid distributed termination or common knowledge**. Lossy native packet classes and objective formulations still differ, even with identical geometry/Seed/measurement. Timing combines Rady application-delay traces with a **hypothetical 144Mbps shared radio**, not measured 100-robot Wi-Fi latency.

**Formal evidence:** [Original ZIP independent audit/report](docs/P1_FORMAL_100SEED.md) · [original 15-row summary](docs/figures/p1/formal/original_summary_p1.csv) · [same-five-success quality](docs/figures/p1/formal/original_same_success_quality_p1.csv) · [machine audit](docs/figures/p1/formal/p1_independent_original_zip_audit.json) · [pre-registered implementation](docs/P1_MATCHED_FIVE_NATIVE.md). The previous original **20-size historical descriptive comparison** is retained separately in the [E9N source audit](docs/E9N_FORMAL_100SEED.md) and [archived source figure](docs/figures/e9n/formal/primary_five_method_time_bytes_success.svg), not overwritten or relabeled.

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

## Remaining acceptance work — P1 completed; next tests conditional

The previously identified **first-priority five-original-method fairness-of-external-measurement study is now COMPLETE and source-verified**. We will not automatically rerun historical pilots or open new optimization baselines. [Bounded closure plan](docs/RESEARCH_CLOSURE_PLAN.md).

| Conditional need | Next action |
|---|---|
| **Claim actual network / Wi-Fi communication time** | First validate the hypothetical 144Mbps radio service and packet timing against a packet-level or controlled multi-host setting. Not needed for claims explicitly limited to **modeled communication time**. |
| **Claim capacity-four multi-task scalability** | One prespecified additional C4 scale (e.g. 50R/200T) if needed; current 25R/100T original result is a single accepted C4 point, not a scaling curve. |
| **Incomplete exploratory controls** | Archive only; no required backfilling. |

## Reproducibility, archives and limitations

- [Historical internal study IDs, names and status](docs/EXPERIMENT_LEGACY_INDEX.md) · [Detailed historical results](docs/EXPERIMENT_RESULTS_ARCHIVE_20261012.md) · [prior README snapshot](docs/README_PRE_ABCD_20261013.md).
- [Cross-experiment audit](docs/EXPERIMENT_RESULTS_AUDIT_20261012.md) · [canonical protocol](docs/EXPERIMENT_PROTOCOL.md) · [change continuity](docs/CHANGE_CONTINUITY.md) · [bibliography](docs/references/e9g_wifi_timing.bib).
- [Matched five-original-method source audit](docs/P1_FORMAL_100SEED.md) · [previous original single-task source audit](docs/E9N_FORMAL_100SEED.md) · [original multi-task source audit](docs/E9M_CORRECTED_ORIGINAL_ZIP_AUDIT_100SEED.md). Original ZIPs are retained unchanged in the user's personal Library with documented SHA-256 identities.

**Comparison boundaries:** *method-native* modeled endpoint ≠ shared paid terminal guarantee; synthetic-timing loss study ≠ Rady radio-proxy experiment; capacity 1 ≠ capacity 4; aggregate historical source ≠ newly rerun paired original source. These limits are preserved in the reports. No actual 100-robot Wi-Fi deployment is claimed.
