# E0 Protocol Correctness Results

This directory is populated by:

```bash
python -m experiments.run_e0 --seeds 100
```

Expected outputs:

- `raw/e0_<UTC timestamp>.csv` — immutable per-seed evidence
- `summary.csv` — current aggregate summary
- `figures/` — reserved for paper-facing plots

Do not hand-edit raw result files.
