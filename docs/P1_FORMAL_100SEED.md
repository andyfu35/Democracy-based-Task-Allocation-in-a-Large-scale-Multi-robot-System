# P1 — Five original algorithms, same-scene 100-Seed formal result and independent source audit

**Status (2026-10-13): ORIGINAL USER ZIP RECEIVED AND INDEPENDENTLY VERIFIED — 0 audit errors.** The 100-Seed source is complete; all 1,500 new native method executions are accounted for. The data are model-based and deliberately retain method-native endpoint differences.

## Original study identity and immutable source

| Evidence | Original identity |
|---|---|
| Original user ZIP | `p1_matched_five_100seed_20261013_122905.zip`, SHA256 `d2f30bf39d1f4aff336a5b7220a4f15ee887d0d79ccc8c8a536819f40691de58`, size 362,773 Bytes |
| Executed Git commit | `24e002695748e976c7b2abdfce661431839c4a7b` |
| Original Mac environment | macOS 14.5 arm64 / Python 3.13.5 |
| Original elapsed execution | Started 2026-10-13 04:07:02 UTC, completed 04:29:05 UTC, 22 minutes 3 seconds |
| Original raw per-seed CSV SHA256 | `86c2d0473329f479924f5c7233bf77f95fd4a6ca13d02184027d37e31501c4af` (1,500 rows) |
| Original 15-row summary CSV SHA256 | `79a14809f515278095c735e28abd17f8a35a460ccafb0be5b8f64093bc7e2abe` |
| Original 15-row common-success quality CSV SHA256 | `3247136535a56af94e49213b0df4c100cc17344c1a31e3f88de156d12af0e239` |
| Original run SVG SHA256 | `0aaf63d6f5eeba77a5a02ab04f87f45df24c7cc78b9eb9120d048240fc193e97` |
| Original run manifest SHA256 | `9daa190b5e28ee65dee41527d6225f41248a73ca2d40a08be6e99ea72d0afd02` |
| Original complete Terminal log SHA256 | `bfa7ba057852f12edafce54c0c06f679e58fc4e510181e2393d3bb7a67e90f8a` |
| Native historical Price Auction algorithm source Git blob | `2d2f1c0eaff94143ce256eebf0a0ee30603d8cba` |
| Raw original ZIP storage | Personal Library `/投票演算法/P1/p1_matched_five_100seed_20261013_122905.zip`, retained unchanged, **not uploaded into the Git tree** |

**Frozen experiment:** N=T ∈ {25, 50, 100}; maximum one task per robot; 100 paired scene Seeds (0…99); independent receiver packet-loss probability 30% on each original method-native lossy wave; reliable Task announcements; assumed 144 Mbps radio service with source-verified Rady ROS latency; 100m seeded square; Price Auction epsilon10m; native 160 guard for CBAA, CBBA and Auction, native 300 guard for original Voting. No Paid CBAA. Original algorithms retain their native packet selection, retransmission/stop semantics and objectives.

## Unified five-method original results (no old aggregate substitution)

For time and payload, means are **over all 100 original Seeds**, including round-guard cases. “First feasible” time is the mean **over Seeds with a source-observed first globally unique assignment**, not a mean with missing failures imputed. Hungarian ratio is computed only for native-full-success Seeds; a later table restricts all five to **the same successful Seeds**.

| N | Original algorithm | Native full successes | First feasible observed | Mean original native stop (s) | Mean first feasible (s; conditional) | Mean sender (decimal kB) | Mean native-success Euclidean / Hungarian |
|---:|---|---:|---:|---:|---:|---:|---:|
| 25 | Voting | 100/100 | 100/100 | 4.550 | 4.550 | 18.06 | 1.2979 |
| 25 | CBAA | 100/100 | 100/100 | 7.713 | 3.888 | 111.10 | 1.1645 |
| 25 | Price Auction | 100/100 | 100/100 | 39.028 | 36.154 | 31.55 | 1.0508 |
| 25 | Voting Multi-task | 100/100 | 100/100 | 12.336 | 12.336 | 20.11 | 1.2843 |
| 25 | CBBA | 100/100 | 100/100 | 2.102 | 1.818 | 178.99 | 1.1645 |
| 50 | Voting | 100/100 | 100/100 | 9.141 | 9.141 | 66.91 | 1.3307 |
| 50 | CBAA | 100/100 | 100/100 | 10.325 | 5.602 | 557.26 | 1.1919 |
| 50 | Price Auction | 98/100 | 99/100 | 80.568 | 76.300 | 116.43 | 1.0836 |
| 50 | Voting Multi-task | 100/100 | 100/100 | 36.345 | 36.345 | 77.71 | 1.3259 |
| 50 | CBBA | 100/100 | 100/100 | 5.685 | 5.206 | 1,091.61 | 1.1919 |
| 100 | Voting | 100/100 | 100/100 | 20.132 | 20.132 | 255.50 | 1.3621 |
| 100 | CBAA | 100/100 | 100/100 | 13.647 | 7.898 | 2,693.04 | 1.2353 |
| 100 | Price Auction | 78/100 | 79/100 | 135.828 | 119.400 | 353.94 | 1.1173 |
| 100 | Voting Multi-task | 100/100 | 100/100 | 101.919 | 101.919 | 305.39 | 1.3612 |
| 100 | CBBA | 100/100 | 100/100 | 12.368 | 11.539 | 6,488.06 | 1.2353 |

**All 1,500 original method runs:** 1,476 native complete; 24 guard-limited (all Price Auction); 1,478 first globally feasible observations. Of the 24 Auction native-guard cases, N50 Seed42 and N100 Seed88 had already formed an externally feasible complete assignment, **but lacked the native endpoint certificate**, so they are counted as failures in native completion and excluded from native-success-only quality.

## Critical result: native-stop rankings reverse when evaluating first feasibility

At N=T=100, CBAA and CBBA independently formed exactly the **same final assignment for every one of the 100 paired Seeds**. This holds at N25 and N50 too: **300/300 final assignment identities** (not merely the same mean Hungarian ratio). Both native-complete 100/100 at N100 and obtain an identical mean cost ratio of **1.2352608183**. Thus the observed trade-off here is a **communication and termination protocol effect**, not a different task cost among these two implementations.

| N100, 100 paired Seeds | Original CBAA | Original CBBA | Difference (CBAA − CBBA) |
|---|---:|---:|---:|
| Mean first globally feasible time (s) | 7.898 | 11.539 | **−3.640 s** |
| Mean method-native stop time (s) | 13.647 | **12.368** | **+1.280 s** |
| Mean native attempted sender payload | 2,693.04 kB | 6,488.06 kB | −3,795.02 kB |
| Mean Euclidean / Hungarian ratio | 1.235261 | 1.235261 | 0.000000 |

Across all N100 Seeds, **CBAA first feasible time beats CBBA on 100/100 pairs**, whereas CBBA native stop beats CBAA on **81/100** pairs. Paired-bootstrap percentile 95% CI, 10,000 resamples with fixed RNG Seed20261013, for CBAA−CBBA: first feasibility **−3.640s [−3.939,−3.364]**; native stopping **+1.280s [+0.952,+1.592]**; Bytes **−3,795,022B [−4,031,694,−3,570,418]**. CBAA spends ~5.75 seconds from first feasible to its local-evidence certificate at N100 on average; CBBA spends ~0.83 seconds to its optimistic observer stop. These are **not** identical distributed “all robots know to stop” guarantees.

## Common successful-Seed quality, not cherry-picked failure-free methods

At N25: all five succeed on **100/100 same Seeds**. At N50: **98/100**. At N100: **78/100**. Every cost ratio below is calculated on exactly that N-sized identical successful five-method paired subset; Auction’s 22 failures are **not** included in the N100 quality denominator and remain visible in the first results table.

| Algorithm | N25 (same-success 100) | N50 (same-success 98) | N100 (same-success 78) |
|---|---:|---:|---:|
| Voting | 1.2979 | 1.3316 | 1.3668 |
| CBAA | 1.1645 | 1.1921 | 1.2348 |
| Price Auction | 1.0508 | 1.0836 | 1.1173 |
| Voting Multi-task | 1.2843 | 1.3251 | 1.3673 |
| CBBA | 1.1645 | 1.1921 | 1.2348 |

The **Price Auction** has the lowest mean original Euclidean/Hungarian ratio (best distance cost) among the common-success Seeds at all three N values, but its native completion at N100 is only **78%**, its modeled stop takes **135.83s** on all 100 Seeds, and its result cannot be reported as 100% reliable. On the 78 common successful N100 pairs, Price Auction − CBAA mean ratio **−0.117433** with paired-bootstrap 95% CI **[−0.131504,−0.103507]**; Auction cost ratio is lower in 77/78 such pairs. More optimistic terminal protocols must not be equated with Voting’s paid Score/Commit, and different native optimization functions must not be called identical rewards.

## Original-source independent audit acceptance

- **PASS:** safe original ZIP member names, CRC, and original SHA256 file identity for raw CSV, 15-row summary, 15-row paired-quality CSV and original four-panel SVG; original Mac source Git SHA, methods, fixed geometry/loss/guard configuration matches original Manifest.
- **PASS:** 1,500 unique `(N, seed, original method)` rows; exact 25/50/100 × 100 × five fixed grid; all 300 original Seed/N scene SHA values regenerated independently from Python Random uniform positions; no cross-method scene mismatch.
- **PASS:** independent recomputation for all 1,500 source Hungarian optimal costs and every recorded assignment’s uniqueness/capacity, Euclidean robot→task total distance, longest path and cost ratio/gap wherever a feasible source assignment exists. Infeasible rows keep quality blank rather than falsely scoring a partial assignment.
- **PASS:** native receipt/sender ledger arithmetic for all original 1,500 cases with method-specific evidence granularity; 28-byte auction original BID/AWARD packet counts, CBAA 16+12N original bid-vector payload, C1 CBBA/Voting Multi-task phase-by-phase packets and receiver opportunities/drops, summarized original Voting Task/Cost/Vote ledger. The ZIP is **not a packet-level PCAP**; counts audit the emitted model ledger, not real over-the-air frames.
- **PASS:** all 15 original summary rows and 15 strict common-success quality rows independently recomputed from full original CSV, preserving guard-censored Auction Seeds; all 1,500 printed Terminal lines reconciled against per-Seed original status, sender Bytes and timestamp values.
- **PASS:** original SVG XML and chart source verified. Original run SVG preserved **byte-exact**; publication derivative shifts only overlapping captions and redraws the cost-ratio panel using original exact same-success CSV with a clearly labeled 1.00–1.50 vertical axis. The native time, first-feasible time and sender-payload plotted trajectories are unchanged; **no algorithm simulations rerun or output values tuned**.

**Audit errors:** **0**. [Read machine-verifiable audit ledger](figures/p1/formal/p1_independent_original_zip_audit.json); [original summary source CSV](figures/p1/formal/original_summary_p1.csv); [strict common-seed source CSV](figures/p1/formal/original_same_success_quality_p1.csv); [original run SVG](figures/p1/formal/original_five_original_matched_comparison.svg); [primary publication SVG](figures/p1/formal/primary_matched_five_protocol_time_bytes_quality.svg). Original full ZIP, Manifest, raw and Terminal remain stored and named by SHA rather than checked in to Git.

## Scientific interpretation and what remains

**This P1 closes the common-scene/common-external-measurement gap of earlier five-curve historical aggregate comparisons.** It does **not** establish equivalent distributed termination or equal native communication budget. `First feasible` is a **simulator read-only snapshot after a completed native physical-message phase**, not something all agents necessarily know or an execution-time metric. CBAA’s local agreement, CBBA observer’s shared halt, task-home Price Auction local awards, and Voting’s charged reliable Commit are deliberately kept distinct. Network time is a *modeled* Rady delay + hypothetical 144Mbps scheduler, not empirically verified real Wi-Fi time. A stronger physical networking claim still requires a separately scoped packet-level or measured validation; old provisional pilots need not be rerun.

**No additional large native-method benchmark is required solely to close the P1 measurement question** under these explicit claims. Preserve the raw original ZIP. Prior E9N original five-method descriptive chart remains available in history and retains its separate source identity; new source-based P1 numbers are not substituted into the old experiment CSV.
