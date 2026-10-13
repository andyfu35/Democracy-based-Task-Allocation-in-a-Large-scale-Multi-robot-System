undefined

## One combined five-algorithm comparison figure (E9I/J/L + E9M)

New bounded source-verified **presentation-only** owner: `experiments.plot_e9m_unified_comparison`. Do not rerun E9I/J/L just to plot: use the existing published immutable 20-point original three-algorithm CSV and a **NEW corrected** E9M 100-seed output root. The figure includes five algorithms on ONE SVG, arranged into two clearly different workloads:

- **A: legacy N=T, capacity1:** E9I Voting, E9J original CBAA, E9L distributed Price Auction. All-seed modeled time and sender Bytes vs N=5..100; available E9L per-size completion counts; E9I/J per-N completion is omitted when unsupported by plotted source.
- **B: E9M R=25/T=100, capacity4:** voting_multitask and CBBA, 100 paired Seeds. Modeled time, sender Bytes, completion rates. Quality metrics (total distance, makespan, discounted reward) remain in the original raw and in the new chart's verified source summary; they are NOT plotted as comparable to legacy Hungarian-relative one-task Cost.

No cross-family absolute speed ranking or single joint best method. All protocol endpoints and modeled radio limitations remain explicit. The original old E9M `f347e26` execution is **not accepted**: source must be descendant of commit `638081b9c040cde5a796a4de83fc3b025fe10b48` (Vote unicast and free local ballots). The presentation verifies original E9L Git-blob identity, E9M raw/summary SHA256s, manifest/preregistered R25T100 C4 p30, every seed0..99 and method exactly once, raw per-phase network ledgers and complete task routes on successful records. Existing source files are never modified.

After Git pull, run these in the Mac repository root **ONLY after the corrected formal 100-seed E9M run is complete**:

```bash
# Set the exact successful corrected result directory; do NOT use old f347e26.
E9M_ROOT="results/e9m_fixed_25r100t_loss30_100seed_<YOUR_TIMESTAMP>"

PLOT_ROOT="results/e9m_unified_$(date +%Y%m%d_%H%M%S)"
python3 -m unittest discover -s tests -p 'test_e9m_unified_comparison.py' -v

python3 -m experiments.plot_e9m_unified_comparison \
  --e9m-root "$E9M_ROOT" \
  --output-root "$PLOT_ROOT"

zip -r "$HOME/Downloads/e9m_unified_evidence.zip" "$E9M_ROOT" "$PLOT_ROOT"
```

This writes one source-attested `unified_method_time_bytes_success.svg`, one `unified_method_comparison_source.csv` with 5 rows and cohort boundaries, and one SHA provenance `unified_method_manifest.json`. Keep old original ZIPs. Send this ZIP back for source audit; **only then** replace the existing E9L main time/Bytes image with the unified chart in README (keep total README plots small). No CI.
