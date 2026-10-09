from __future__ import annotations

import argparse
from pathlib import Path

from democracy_mrta.network import (
    ensure_rady_dataset,
    load_rady_latency_profile,
    summarize_latency_profile,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download, verify, and summarize the pinned Rady et al. Wi-Fi dataset"
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path("data/external/rady/perama_range_testing.json"),
    )
    args = parser.parse_args()

    path = ensure_rady_dataset(args.destination)
    profile = load_rady_latency_profile(path)
    summary = summarize_latency_profile(profile)

    print(f"RADY_DATASET={path}")
    print(f"RADY_PROFILE_LOCATION={profile.location} {profile.location_label}")
    print(f"RADY_PROFILE_CONFIG={profile.config} {profile.config_label}")
    print(f"RADY_PROFILE_SAMPLES={summary['sample_count']}")
    print(f"RADY_PROFILE_MEAN_MS={summary['mean_ms']:.6f}")
    print(f"RADY_PROFILE_P50_MS={summary['p50_ms']:.6f}")
    print(f"RADY_PROFILE_P95_MS={summary['p95_ms']:.6f}")
    print(f"RADY_PROFILE_P99_MS={summary['p99_ms']:.6f}")
    print(f"RADY_PROFILE_MIN_MS={summary['min_ms']:.6f}")
    print(f"RADY_PROFILE_MAX_MS={summary['max_ms']:.6f}")


if __name__ == "__main__":
    main()
