# E9N Formal 100-Seed Source Audit — Five Algorithms, Capacity One

**2026-10-13 ORIGINAL ZIP VERIFIED, zero audit errors.** Executed Git SHA `5bb3f7ca18c3812413539550edb3a2b370fa11d3`. User original ZIP `e9n_cap1_100seed_20261013_102240.zip` (773,072 bytes), SHA-256 `f4807e70fe5c58ec9908c6adc39f2fbc50a31312222d757ca8205ee6ca3cc86d`, retained **unchanged** in personal Library `/投票演算法/E9N/`, not checked into Git. Original run on macOS arm64/Python 3.13.5 started 2026-10-13T01:14:32Z, ended 02:22:39Z.

## Preregistered original setting and source

20 N=T scales 5,10,...,100; each robot maximum **one task**, 100 Seeds 0..99 per scale, packet loss p=.30, 160-round safety censor, deterministic 100m square geometry, 1m/s, Rady ROS sampled delay + assumed 144Mbps shared wireless proxy. **Two newly executed methods**: native Voting Multi-task C1, genuine CBBA C1 — **4,000 original per-Seed executions**. Old E9I Voting, E9J original CBAA and E9L Price Auction contribute **6,000 frozen already executed observations** from Git source blob `950ea0c2bd28dff280181fcc2f8b58d6db27633a`; none of those three methods was rerun in E9N. E9K team-authored paid CBAA excluded. **Five plotted series are not 10,000 freshly rerun trials from one commit.**

Original signed-by-hash ZIP members:
- `per_seed_e9n.csv`: SHA256 `a0197db3e0821c8d2c5aeec4a6c3f8bbb73a2899cbccfe8446b59d733fbad6da`; 4,000 rows.
- `summary_e9n.csv`: SHA256 `9923c3ffca528618f2bdf2592d0da89503dd74cd7b425b4c6cbdec8f2842cffa`; 40 original N/method summaries.
- `five_method_common_cap1_source.csv`: SHA256 `e7469f50fb47b96d79a467ab2f030597ed76a1d85d0c72a7a3284005856b789f`; 100 N×five-method rows, preserved verbatim in Git.
- Original `five_method_common_cap1.svg`: SHA256 `2753bcb8c336bdd9ba91d1877c7a09bfdef7603b64f902a0f641464819f076f2`, preserved verbatim in Git.
- Original `manifest_e9n.json`: SHA256 `6ef1c2c1140c6a73bdd754e30382c02e13636c4040f515ca497be21f3c144b06`.
- Original terminal log SHA256 `b40dc61f9d9ab3b0876b628746d8f2cd5b279b8dd67335ece9bb8392699256a6`.
- Rady profile source Git commit `1996e5bb69b9ba4d25060cbc14838ddedf65cff2`, blob `11e70e685229cc26458f272b0c954487c87d7953`.

## Official five-method figure — N=T=100, C1, 30% Loss

| Method (source) | All-seed modeled allocation/stop time | All-seed attempted sender payload | Completion evidence from figure source |
|---|---:|---:|---|
| Voting (E9I), historical | 20.132 s | 255.50 kB | Per-N numerator unavailable from frozen plot CSV |
| Original CBAA (E9J), historical | 13.647 s | 2,693.04 kB | Per-N numerator unavailable from frozen plot CSV |
| Price Auction (E9L), historical | 135.828 s | 353.94 kB | 78/100, includes 22 guard-censored |
| Voting Multi-task C1 (E9N), new | 101.919 s | 305.39 kB | **100/100** |
| Original CBBA C1 (E9N), new | **12.368 s** | 6,488.06 kB | **100/100**, optimistic observer |

[**Five-method common-capacity figure**](figures/e9n/formal/primary_five_method_time_bytes_success.svg) · [Original source plot CSV](figures/e9n/formal/original_five_method_common_cap1_source.csv) · [Original run's SVG](figures/e9n/formal/original_five_method_common_cap1.svg) · [Full independent audit JSON](figures/e9n/formal/verified_original_zip_audit_100seed.json).

## Newly executed Voting vs CBBA, 100R/100T

| E9N paired original metric | Voting Multi-task C1 | CBBA C1 |
|---|---:|---:|
| Success, all 100 seeds | 100/100 | 100/100 |
| Sender SEND attempts | 15,110.28 | 6,451.45 |
| Sender application Bytes | 305,393.60 | 6,488,061.61 |
| Modeled time (different paid-Commit vs observer endpoints) | 101.919 s | 12.368 s |
| Sum of actual robot travel | 1,385.148 m | **1,260.847 m** |
| Longest robot travel / Makespan | **85.745 s** | 99.450 s |
| Discounted route Reward, higher better | 9,863.663 | **9,876.359** |

CBBA is **8.241× faster in the modeled study** but transmits **21.245× the Bytes** relative to Voting Multi-task C1. CBBA's sum of route lengths is shorter by 124.301m, whereas Voting's longest route is shorter by 13.704m. This makespan is longest **physical task route**, not communication/allocation time. CBBA sends fewer but much larger original snapshots.

Paired N100, 100 original common Seeds, 10,000 deterministic paired-bootstrap resamples (difference Voting − CBBA): modeled time **+89.551 s** CI95 [88.676,90.445]; sender Bytes **−6,182,668 B** CI95 [−6,459,644,−5,912,509]; total travel **+124.301m** CI95 [108.259,141.247]; makespan **−13.704s** CI95 [−17.377,−9.905]. All 100 Seeds Voting uses fewer Bytes and takes longer modeled time. These paired CIs do **not** apply to E9I/J/L historical aggregate comparisons.

## Independent source check, all PASS

Full original ZIP member CRC/paths; every Manifest file SHA; exactly 4000 unique (N,Seed,Method), all 20 scales and 100 Seeds; 2,000 deterministic seeded scene SHA matches; all 4,000 route/task uniqueness/C1 assignments and independently recomputed original Euclidean travel, max-route duration, discounted reward; all original per-phase physical SEND/Byte/receiver receipt/drop ledgers (Vote 20B recipient-only unicast, N−1 native broadcasts, N receiver task announcements); reaggregated all original 40 summary rows; verified all 100 plotted rows for the two new methods and all 60 old plotted time/byte values against original historic E9I/J/L Git blob; matched 4,000 original Terminal lines against full-precision values allowing logged 3-decimal rounding. **0 errors.** Original graph XML valid. Missing old E9I/J per-N completion remains blank instead of imputed.

The new publication SVG SHA256 `d7508314bfaf2b0f474d857fe8184fca6aca15f5dc4bc4c0780dee8df40f634a` corrects **only presentation spacing** in the original SVG; point data, axis scales, legend and end-condition caveats unchanged. The exact original figure/CSV are separately preserved unchanged, and the source visualization owner is fixed for later renders without changing the original executed E9N source SHA.

**Limitations:** Rady traces and assumed 144Mbps are not empirical Wi-Fi RF; method-native stop conditions differ (CBBA observer/local certification vs Voting paid reliable Score/Commit); frozen historical E9I/J/L code commits differ from newly executed E9N; optimization reward/cost definitions are not strictly identical despite common capacity1 geometry. No five-way paired significance claim. Verified E9M 25R/100T/C4 remains separate.
