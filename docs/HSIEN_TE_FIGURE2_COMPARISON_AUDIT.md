# Hsien-Te Methods — Figure 2 five-method comparison provenance (2026-10-22)

## User-confirmed name and method identity

**Hsien-Te Methods** is the new publication display name for the already executed **P2J-v3** arm, native mode `probabilistic_complete_fallback` and study `P2J_V3_DETERMINISTIC_FALLBACK_PAIRED`. Native mode, code identifiers, experimental source SHA, raw evidence and transport behavior are **not changed or renamed**. The main README primary Figure 2 retains the four previously published curves and adds Hsien-Te Methods as the fifth. Older four-method Figure 2 remains at `docs/figures/p2i/formal/figure2_reliable_four_method.svg` with the original 40point CSV and P2I source audit untouched. The newer five-method publication assets are `docs/figures/p2j/formal/figure2_hsien_te_five_methods.svg` and `docs/figures/p2j/formal/verified_50point_hsien_te_summary.csv`.

## Native source and independent verification

Original uploaded formal ZIP `p2j_v3_complete_100seed.zip`: SHA256 `9839901650acc1d2feba0a14158a55c1211796a486bfc6c2d5fd9c8ac358e710`, native code source Git SHA `33bd5f771b347365d768890ea71e87f0c1e7c6a3` on `experiment/p2j-v3-completion-fallback-20261022`. Original manifest study = `P2J_V3_DETERMINISTIC_FALLBACK_PAIRED`; 3,000 native per-seed rows (three methods), 30 loss/method groups, 100 paired E0 scenes per loss. Uploaded manifest attests:
- `per_seed_p2j.csv` SHA256 `8f3ad6556313d0997306948bf35527d856637f59aa9f10703735aefe2b6c661c`
- `summary_p2j.csv` SHA256 `63b797a7b3c482796b30e8766694a880522492be0513190ba84993871715efc0`
- `run_config_p2j.json` SHA256 `7fd616f7beb55bf8ea8ea74d942651c6fe1fcafba744063b37545a0837f7e8a6`

The original ZIP and all 3 inner manifest SHA256 values were verified in this publication step. Independent reaggregation from **all 3,000 raw native rows** passed **37,150 assertions** over case identity, one original Cost/Vote SEND per voter, exact per-phase sender SEND/Byte reconciliation, unique original native committed robot/task pairs, original assignment SHA256, legitimate fallback/Commit count, completion-only signed cost calculations and matching 30 summary groups. The 10 displayed Hsien-Te points are exactly the `probabilistic_complete_fallback` records of this verified formal summary; no new native case was run to draw the figure. This check does not replay every radio packet arrival or verify measured real RF behavior.

The **original four** displayed methods reproduce exactly the already published 40 cells in `docs/figures/p2i/formal/verified_40point_summary.csv`. Those methods draw on 20 newly executed P2I cells (`full_retry`, `cost_retry_vote_once`), 10 archived CBAA cells from original `docs/figures/p2de/formal/verified_50point_summary.csv` and 10 archived Centralized cells from P2G SVG tooltips. Historical centralized seconds/kB remain **rounded to the 4 decimal places available**. All 50 display cells encode data provenance, the original native Git SHA, 100 trials and successful-only cost n. The 200 figure tooltips are directly generated from those cells (5 methods × 10 losses × 4 metrics).

## Measurement definition and selected comparisons

Fixed E0 100 robots / 100 tasks / capacity 1; loss 0–90% by 10%; 100 Seeds per method/loss. Panel A = native **full 100-task allocation success**, not partial coverage. Panel B = per-seed mean signed cost gap from **full-information Global minimum-pair Greedy**, conditional on all 100 native tasks committed (not Hungarian; Figure1 instead uses task-ID Greedy). Negative cost difference is valid because full-information Global Greedy is a heuristic. Panel C = **modeled** all-seed communication stop seconds; computational optimization CPU time excluded. Panel D = all attempted original application-layer sender kB (decimal, 1000 B), counting lost DATA sends, applicable retries/ACK and genuinely emitted Score/Commit.

| PL | Method | Complete | Cost gap | Time (s) | Sender (kB) |
|---|---|---:|---:|---:|---:|
| 30% | Hsien-Te Methods | 100/100 | −6.0133% | 2.1393 | 142.4669 |
| 30% | Full Retransmission | 100/100 | 0% | 14.7731 | 838.4786 |
| 30% | Cost Retransmission Only | 100/100 | 0% | 8.3862 | 504.6580 |
| 30% | CBAA | 100/100 | 0% | 13.6474 | 2693.0400 |
| 30% | Baseline Centralized | 100/100 | 0% | 3.5067 | 122.5402 |
| 90% | Hsien-Te Methods | 100/100 | +35.6531% | 2.1497 | 133.6216 |
| 90% | Full Retransmission | 100/100 | 0% | 148.5252 | 8661.7952 |
| 90% | Cost Retransmission Only | 100/100 | 0% | 75.0786 | 4405.0126 |
| 90% | CBAA | 100/100 | 0% | 71.3832 | 14135.6000 |
| 90% | Baseline Centralized | 100/100 | 0% | 32.3970 | 828.9269 |

**Important limitations:** Hsien-Te Methods guarantees native full assignment under **generalist 100R100T capacity-1 E0** with intentionally reliable, paid candidate Score and Commit; it does NOT guarantee a physical robot finishes its task or that physical wireless packet delivery is reliable. At PL90, 38% of its Seeds use 1+ deterministic zero-vote fallback (mean 0.54 fallback assignments per Seed); missing Costs are not used to choose fallback, but true realized fallback costs are evaluated after assignment. Cross-experiment baseline protocols and CBAA native stopping/observation differ from paid Hsien-Te Commit, so these are source-grounded **descriptive** comparisons, not controlled causal claims about universal speed or byte efficiency. P2I model-reliable bitmap ACK/data resend and Hsien-Te model-reliable Score/Commit are explicitly charged. Shared-medium Rady-derived timing with assumed 144 Mbps does not model measured multi-robot hardware radio collisions, MAC retries, lossy ACKs or computational solver runtime. The specific centralized implementation cannot stand for all centralized methods.

## Bounded publication boundary / owner and diagnostics

Changed only the primary bilingual README Figure 2 reference and narrative, appended a frozen 50-cell CSV, static SVG, this source audit, a publication-specific canonical note, and mandatory continuity. **No executable function, optimizer, Cost/Vote/Score/Commit owner, duplicate state machine, packet model or original archived case was modified.** Original authorship/provenance is P2J-v3 owner `coordination.complete_unassigned_score_matching`, `coordination.resolve_dynamic_probability_margin_winners`, `experiments.run_p2j_probabilistic_batch.run_one_p2j_case` / `summarize_p2j_cases`; old Figure2 native P2I/CBAA/Centralized owners remain unchanged. Original `experiments.p2g_plot.render_p2g_figure` remains historical and is not rerun. First diagnostic remains owner/function/category/code/expected/actual/details with fixed data/time/state/dependency/planning/safety/runtime/contract categories. No Python or Mac native tests newly executed for this documentation-only publication. Figure1 and archived one-shot Figure A are unchanged.
