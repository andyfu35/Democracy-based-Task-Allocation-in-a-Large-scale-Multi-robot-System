# E0 Perfect-Information Correctness Results

Canonical E0 now validates the **full-matrix Hungarian proposal + distributed majority vote** protocol.

The earlier `e0_20261009T130507Z.csv` run, if present locally, belongs to the obsolete sequential task-wise implementation and must not be used as paper evidence.

Run:

```bash
python3 -m unittest discover -s tests -v
python3 -m experiments.run_e0 --seeds 100
```

Expected corrected outputs:

- `raw/e0_corrected_<UTC timestamp>.csv` — immutable per-seed evidence
- `summary.csv` — current corrected aggregate summary
- `figures/` — reserved for paper-facing plots

A corrected E0 condition passes only when all of these are true:

- mean optimality gap = 0
- assignment success rate = 1
- oracle assignment mismatches = 0
- non-unanimous task count = 0
- safety failures = 0
- deterministic replay failures = 0

Do not hand-edit raw result files.
