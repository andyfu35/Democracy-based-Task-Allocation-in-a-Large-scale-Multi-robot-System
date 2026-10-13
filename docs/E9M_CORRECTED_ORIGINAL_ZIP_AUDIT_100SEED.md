# E9M corrected formal 100-seed — original ZIP source audit (2026-10-13)

**Evidence status: ORIGINAL SOURCE ZIP RECEIVED AND VERIFIED (100 paired seeds).** Supersedes the earlier **terminal-only audit status** in [the historical E9M Terminal note](E9M_CORRECTED_TERMINAL_100SEED.md), without replacing or erasing that original record. The user uploaded the exact original `e9m_fixed_25r100t_loss30_100seed.zip`; retained unchanged in the user's persistent personal Library at `/投票演算法/E9M/e9m_fixed_25r100t_loss30_100seed.zip`. GitHub stores this independently derived source-audit JSON and its cryptographic identity; **the binary ZIP itself is stored in Library, not in this repository.**

## Immutable original identities

| Identity | SHA-256 / Git |
|---|---|
| Uploaded original ZIP | `de68d1cce8045a46b8e37f2d8f91e3988004db39d29544e1865d4759336e46b5` |
| Original `per_seed_e9m.csv` | `1268c3ca82dd3d40793da94c46900cee4648f1903cfcf847dc5113dc6d04f753` |
| Original `summary_e9m.csv` | `1f2a3468b52d36eb09b2cfd58b3df699cadb2d376c10cf0b6466988b6cbe950f` |
| Original `manifest.json` | `68fbca3241ea0f670ef497f40cd6da7d0297ef1ac1f046699a4cc26110d7748e` |
| Original `*.log` | `c7812ae6a97df214d6727f1aca5d28b15494a5f5f889bf7bd08ac57c265f5a5d` |
| **Executed** E9M Git commit | `7e857fd232c9459d0777cf130bc36766467e1ff0` |
| RADY original source commit / blob | `1996e5bb69b9ba4d25060cbc14838ddedf65cff2` / `11e70e685229cc26458f272b0c954487c87d7953` |

Original run root: `results/e9m_fixed_25r100t_loss30_100seed_20261013_084946`. Started UTC: `2026-10-13T00:49:47.049418+00:00`; completed UTC: `2026-10-13T00:50:45.608081+00:00`; platform: `macOS-14.5-arm64-arm-64bit-Mach-O`; Python: `3.13.5`.

## Frozen original experiment cell

25 Robots, 100 Tasks, maximum **4 tasks/robot**, 100 paired scenario seeds 0..99, independently applied receiver packet loss **30%** on each method's native lossy messages, 160 CBBA safety guard, 100m×100m deterministic scene, 1 m/s robot travel, zero task service time, Rady empirical application delay input plus **assumed** 144 Mbps shared-medium proxy. Voting Multi-task has candidate-only Vote unicast and no sender SEND for local self-vote on the executed corrected SHA; CBBA uses native fragmented 1200B max snapshots. The original recorded time is modeled *protocol stop/coordination time*, **not Python wall runtime or measured wireless RF**.

## Full-source statistics (100 original seeds per method)

| Metric | Voting Multi-task | CBBA | Direction |
|---|---:|---:|---|
| Complete unique task assignment | 100/100 | 100/100 | Both fully complete |
| Modeled allocation / observer stop | **63.023 s** | **6.878 s** | CBBA smaller (but different finalization) |
| Original sender application Bytes | **116,827.40 B** | **1,006,873.34 B** | Voting smaller |
| Native original SENDs | 5681.97 | 1115.34 | CBBA fewer, but much larger snapshots |
| Total travel (sum of routes) | 1319.764 m | 1209.480 m | CBBA smaller |
| Makespan (longest route at 1 m/s) | 134.554 s | 148.635 s | Voting smaller |
| Discounted path reward (higher better) | 9735.450 | 9754.469 | CBBA modestly higher |
| CBBA rounds / Voting task epochs | 100.00 | 16.81 | Different meanings |
| Guard-censored / failed | 0/100 | 0/100 | All original attempts retained |

Mean modeled time ratio Voting/CBBA: **9.163×**; sender-Byte ratio CBBA/Voting: **8.618×**. Among 100 *paired* seeds, Voting took longer in 100/100, used fewer Bytes in 100/100, and produced a shorter **total** route in only 17/100, while a shorter **makespan** in 63/100. The two advantages in route metrics should be presented separately: CBBA typically minimizes **sum** of distances better, but Voting gives lower mean **maximum** route duration.

Illustrative paired-bootstrap percentile 95% intervals (20,000 seed-pair resamples, deterministic NumPy random seed 20261013, difference = Voting − CBBA): modeled time **+56.144 s** [55.387,56.868] s; attempted bytes **−890,046 B** [−925,010,−856,776] B; total travel **+110.285 m** [89.417,131.339] m; makespan **−14.081 s** [−20.585,−7.683] s; discounted reward **−19.019** [−22.540,−15.537]. This is a derived descriptive paired bootstrap on the **same E9M workload**, not a cross-study, RF or equivalent-termination claim.

## Independent original-source acceptance

- PASS: ZIP member count and safe paths; original raw CSV and summary file SHA-256 exactly reproduce `manifest.json.sha256`.
- PASS: complete 200 unique `(seed,method)` original rows (seeds0..99 × Voting Multi-task/CBBA); 200 Manifest original per-phase ledgers have matching unique keys.
- PASS: all 200 successful, each exactly 100 **distinct** tasks in 25 routes; 0 duplicates/missing, no capacity violation, local certificates25 and observer agreement; 0 hidden guard/censor failures.
- PASS: for **each of 200** rows, independently regenerate 100m original robot/task positions from the recorded seed and recompute total route distances, longest-route makespan and exact discounted cumulative distance reward `100*(0.999**cumulative_distance)`; they agree with raw CSV floating-point values.
- PASS: every original per-phase SEND/Bytes/receiver_attempts/delivered/dropped ledger sums to corresponding original row, per-phase recipient accounting balances, and the Manifest per-seed method phase ledger matches the CSV. Vote SENDs are one-target unicast with 20-byte original ballots; Task external announcements have **25** recipients, native robot broadcasts 24.
- PASS: independently recompute original method summaries from all 100 raw rows and reproduce the shipped original `summary_e9m.csv` with full precision.
- PASS: all 200 originally printed Terminal log rows reconcile with full-precision original raw rows after the expected three-decimal log rounding; terminal completion SHA equals `manifest.git_sha`.

Machine-readable detailed audit: [Original ZIP audited evidence JSON](figures/e9m_multitask/verified_original_zip_audit_100seed.json). The JSON is a **new independent summary**, never a replacement for the source ZIP. The earlier terminal-derived 200-row CSV is retained separately, not substituted for original raw.

## Limits and next experiment

This verifies **data integrity, calculation reproducibility, packet accounting consistency, paired source scope and executed version**, not correctness of every literature CBBA consensus detail or physical Wi-Fi performance. **CBBA observer-based free stopping and Voting paid reliable Score/Commit do not provide identical finalization guarantees.** Distances/rewards are exact only for the declared 100m Euclidean/zero-service setting.

Keep this verified E9M capacity4 result independent of [E9N capacity-one five-method comparison](E9N_ONE_TASK_FIVE_METHOD.md): no pooled timing ranking between 25R/100T/C4 and N=T/C1. Previous pre-correction E9M source `f347e26` remains superseded preliminary evidence and is not substituted.
