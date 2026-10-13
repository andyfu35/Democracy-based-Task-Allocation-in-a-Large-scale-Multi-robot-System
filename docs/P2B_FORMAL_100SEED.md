# P2-B formal 100-seed evidence audit — batched Voting, reused CBAA / CBBA / Price Auction

**Verified and accepted on 2026-10-13: 1,000 new Voting simulations + 3,000 exact original baseline rows = 4,000 paired cases, 40 four-method summaries.** The user supplied the original complete ZIP and an independent checker recomputed actual deterministic geometry, one-to-one assignments, Hungarian costs, sender/receiver-phase identities, all 40 aggregate groups, exact unmodified baseline rows, and original terminal lines: **zero inconsistencies**.

## Immutable sources and lineage

- **New Mac ZIP:** `p2_batch_voting_only_100seed.zip`, 1,742,540 bytes, **SHA256 `acd3dd389303a58cb27a16f46f29b6008f8b4678ff786d249e13caf60d61c08a`**. Executed source Git **`7c082610bb3e3489ab09d07aaa339d1bbcd9acaa`**, finished `2026-10-13T13:00:01.494096+00:00`. Original *new Voting only* `per_seed_p2.csv` SHA256 `0a55d5a3d2016de8346be7b005ae26959202c206205e7164eaeb0a42bb2f0958`.
- **Four-way reassembled evidence:** original user-run `per_seed_p2_combined.csv` SHA256 `dca1f1b1db3ba1425dc64ae43641d838ea2881b9f6dcc9a94c6d4ad4afb3b24a`; original `summary_p2.csv` SHA256 `63ad7ee2c37f93f3f39ef761ab8138fdc1e5a6bc010c95b301d5655d90d6369b` (40 groups), `summary_voting_p2b.csv` SHA256 `ae4ed7bbb288f4f8bb16ab4ef757ae6c8de67c5909a843177765210dd75f531c` (10 groups), and original four-panel run SVG SHA256 `7a3a14e7bd84c6f1d876a1379e75168f51b2db50f0d68042318ae53f10721d88`.
- **Immutable original baseline archive:** `p2_loss10_100seed.zip`, SHA256 `1d08a167308b9368ee2a764737066223ac041a5bd6508621c7b6cd0320036bb9`; original `per_seed_p2.csv` SHA256 `78c4871a9f0e391c11c92ace9c2b532695d2a2c4ca40d31166e31bf89901e5fc`; originally executed Git `f514cfa3613e7b0bad5c739d136b09fea8c3f92c`. New Voting has this NEW source tag, every reused CBAA/CBBA/Price Auction row retains the ORIGINAL source tag. **Zero baseline cases re-executed; 3,000/3,000 selected baseline rows identical in every raw data field.** Original old sequential Voting never enters the new four-method results.
- Historical original baseline ZIP and new original Mac run ZIP are *not added as binary Git artifacts*. These exact names/SHA and original first-failure constraints are preserved in [source manifest](figures/p2b/formal/source_manifest.json). [Audited compact per-method plotting source](figures/p2b/formal/verified_40point_summary.csv) and [publication-only four-panel figure](figures/p2b/formal/p2b_packet_loss_four_panel.svg) are DERIVED from source and have rounded presentation values, not substituted as original raw.

## Study protocol, all source rows checked

100 robots, 100 tasks, capacity=1, paired Seeds 0–99, PL 0/10/20/30/40/50/60/70/80/90%. Voting uses **one initial reliable logical TASK announcement** (three physical application frames for the full 100-task set), **exactly one 100-robot Cost exchange** (100 physically counted Cost frame SENDs even on later Vote retries), local capacity-one *full remaining-task* Greedy planning on physically received Cost rows, explicit batched receiver-loss Vote and reliable candidate Score-vector/unique-executor Commit with the original retirement state owner. The 1,000 Voting cases had 0 native failures or diagnostics. Independent observer shows full one-to-one feasibility in all 1,000, all 100 Seeds at 0% **exactly match independently calculated full-information sequential Greedy pairs** and all 100 end in **one batch epoch**.

Six original user manifest file SHA256 values, 1,000 Voting printed terminal lines, 1,000 independent batch TASK/Cost/Vote/Score/Commit physical SEND-count and timing ledgers, original 4,000 field-wise new/reused source identities, 4,000 independently seeded 100m geometry/Hungarian and final one-to-one assignment cost/gap/ratio/makespan values, 10 Voting-only summary rows, all 40 reassembled original summary rows and both original/native-success counts all match. **Independent audit discrepancies: 0.** No new Python CI/automated full repository test run is asserted here; this is a completed result-file forensic audit.

## Completion across receiver packet loss (100 paired seeds each)

| PL | Voting | CBAA | CBBA | Price Auction | all-four common native success |
|---|---:|---:|---:|---:|---:|
| 0% | 100 | 100 | 100 | 98 | 98 |
| 10% | 100 | 100 | 100 | 99 | 99 |
| 20% | 100 | 100 | 100 | 90 | 90 |
| 30% | 100 | 100 | 100 | 78 | 78 |
| 40% | 100 | 100 | 100 | 51 | 51 |
| 50% | 100 | 100 | 100 | 31 | 31 |
| 60% | 100 | 100 | 100 | 14 | 14 |
| 70% | 100 | 100 | 100 | 9 | 9 |
| 80% | 100 | 100 | 0 | 0 | **0** |
| 90% | 100 | 100 | 0 | 0 | **0** |

All 4,000 comparison rows yield **3,270 native complete / 730 native guard-censored** (200 CBBA at PL80–90; 530 Price Auction across PL). Native stop guarantees remain unequal: Voting reliably pays Score/Commit; original CBAA/CBBA/Auction have different native local or simulator terminal criteria. Auction also has two failures at PL0, which cannot be attributed to packet loss. An unobserved full completion at a fixed round guard does not establish a theoretical PL threshold.

## Batched Voting compared with historically serialized Voting (same exact 100 seeds)

| PL | Old serialized stop | New batched stop | modeled stop reduction | Old sender payload | New sender payload | payload reduction |
|---|---:|---:|---:|---:|---:|---:|
| 0% | 16.474 s | **2.027 s** | **87.7%** | 249.25 kB | **171.65 kB** | 31.1% |
| 30% | 20.132 s | **3.120 s** | **84.5%** | 255.50 kB | **156.94 kB** | 38.6% |
| 60% | 22.326 s | **4.745 s** | **78.7%** | 258.49 kB | **144.06 kB** | 44.3% |
| 90% | 27.497 s | **11.742 s** | **57.3%** | 254.23 kB | **142.01 kB** | 44.1% |

**Paired-seed bootstrap**, 10,000 resamples with replacement, RNG seed `20261013`, 95% percentile intervals for percentage reduction of **mean old/new native stop**: PL0 **87.69% [87.27%,88.11%]**, PL30 **84.50% [83.95%,85.04%]**, PL90 **57.30% [56.27%,58.29%]**. These quantify same-scenario simulation uncertainty across the 100 selected deterministic Seeds, not physical radio or general scenario distribution guarantees.

## Communication time stage proof

| PL | TASK once | Cost once | Vote + Score | Commit | total native stop | mean batch epochs |
|---|---:|---:|---:|---:|---:|---:|
| 0% | 0.076 s | 0.489 s | 0.983 s | 0.480 s | **2.027 s** | 1.00 |
| 30% | 0.076 s | 0.609 s | 1.713 s | 0.722 s | **3.120 s** | 3.75 |
| 60% | 0.076 s | 0.609 s | 3.044 s | 1.016 s | **4.745 s** | 7.25 |
| 90% | 0.076 s | 0.609 s | 9.533 s | 1.524 s | **11.742 s** | 20.78 |

The Cost is **not repeated** in 20.78 high-loss batch epochs; the increase in simulated delay is mainly Vote+Score retry phases. A logical TASK broadcast covers 100 tasks but is segmented into **3 real framed application sends**; do not call it one *physical* packet. All above are modeled native times, including method-specific termination/guard treatment, **not actual execution wall-clock or robot Wi-Fi measurements**.

## Allocation quality: important cost of batching

At PL0 the 100 original batched Voting assignments **exactly** match full-information sequential Greedy (Voting cost / full-information Greedy cost = 1 for every Seed). But Greedy need not be global Hungarian: mean `Voting cost / Hungarian optimum = 1.351195` even at zero loss. Therefore PL0 ratio >1 **is not an implementation mismatch**.

| PL | Old serialized Voting / Hungarian | New batched Voting / Hungarian | New batched Voting / full-information Greedy |
|---|---:|---:|---:|
| 0% | 1.351 | 1.351 | **1.000** |
| 30% | 1.362 | **1.825** | 1.352 |
| 60% | 1.480 | **2.399** | 1.778 |
| 90% | 2.418 | **3.840** | 2.846 |

**90%-loss quality penalty:** same 100 Seeds new vs old mean Hungarian ratio +**1.42285** (paired bootstrap CI **+1.34252 to +1.50181**), about **58.9% worse relative ratio**; new Voting vs CBAA on the *same 100 fully native-successful Seeds* **3.8404 vs 1.2353**, despite Voting sending vastly fewer attempted application Bytes and completing faster. CBAA first externally feasible at 90% occurs at about **12.77 s**, batched Voting's first complete feasible at about **11.74 s**, whereas the original sequential Voting first feasible was about 27.50 s. Use meaningful matching first-feasible measurements, and still distinguish each native stop guarantee.

**Presentation note:** the original run's plot D uses *intersection of all four native-success Seeds* for `cost/Hungarian`, which becomes undefined at PL80/90. The new publication four-panel D explicitly uses **success-only quality per method** so that PL80/90 Voting and CBAA are visible and their samples truly match all 100 Seeds. For Auction/CBBA at lower PL, the successful-only cohort sizes differ; they **must not be ranked as full-population quality**. The plot title, footnote and separate 40-group CSV state this distinction. At PL0 Hungarian=1.0 is the global optimum, not the Greedy reference.

## One publication four-panel (B)

![P2-B four panel: native full completion, modeled native stop, attempted sender traffic and native-success-conditional quality](figures/p2b/formal/p2b_packet_loss_four_panel.svg)

[40-group rounded derived figure source](figures/p2b/formal/verified_40point_summary.csv) · [Original ZIP/manifest SHA and figure provenance](figures/p2b/formal/source_manifest.json).

**Graph correctness:** A uses distinct dash patterns and differently sized concentric hollow markers **at the same physical data coordinates** where curves overlap. B/C use explicitly labeled logarithmic y scales to prevent 2-second Voting or sub-MB payload curves being hidden by large Auction/CBBA values. D shows all 10 PL values for Voting and CBAA and only native-success values for CBBA/Auction, never invents missing 80%/90% costs. The publication SVG is a **separate derived presentation**: original user-run SVG byte identity and SHA remain on the immutable input, and source csv is six-decimal rounded for plot presentation.

## Interpretation boundaries and next steps

Under this exact simulated, guarded, receiver-loss environment, the batching change improved Voting's modeled latency and attempted sender payload for all 10 tested loss levels, but **also increased assignment-cost suboptimality sharply under loss**. The P2-B claim is **fast, communication-lean, completion-robust at an explicit quality cost**, not universal allocation optimality or an established physical RF tolerance threshold. Rady sampled application delay + *hypothetical* 144 Mbps, lossy per-receiver Cost/Vote plus reliable TASK/Score/Commit, distinct native stop and algorithmic guard limits remain central model assumptions.

The **older original P2 and 100R50T E9E** results are historical different protocols/scenarios. Do not pool. The unrelated manuscript A/C/D benchmark sections with original serialized Voting remain independently valid *for their original protocol*, but **not** numerical evidence of current batched Voting until refreshed using exactly matched new Voting-only scenarios/seeds. No other native baseline rerun required.

