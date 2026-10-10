from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import ssl
import urllib.error
import urllib.request

from .diagnostics import Diagnostic, ProtocolError


RADY_SOURCE_REPOSITORY = "minarady1/wifi_for_industrial_robotics"
RADY_SOURCE_COMMIT = "1996e5bb69b9ba4d25060cbc14838ddedf65cff2"
RADY_SOURCE_BLOB_SHA = "11e70e685229cc26458f272b0c954487c87d7953"
RADY_SOURCE_PATH = "plots/perama_range_testing.json"
RADY_SOURCE_URL = (
    "https://raw.githubusercontent.com/"
    f"{RADY_SOURCE_REPOSITORY}/{RADY_SOURCE_COMMIT}/{RADY_SOURCE_PATH}"
)

PRIMARY_LOCATION = "2"
PRIMARY_LOCATION_LABEL = "Medium range LoS (60 m)"
PRIMARY_CONFIG = "ax_160mhz_6ghz"
PRIMARY_CONFIG_LABEL = "Wi-Fi 6E ax/6/160"
PRIMARY_STEADY_START_S = 120.0
PRIMARY_STEADY_END_S = 181.0


@dataclass(frozen=True)
class EmpiricalLatencyProfile:
    source_repository: str
    source_commit: str
    source_blob_sha: str
    location: str
    location_label: str
    config: str
    config_label: str
    steady_start_s: float
    steady_end_s: float
    samples_ms: tuple[float, ...]

    @property
    def sample_count(self) -> int:
        return len(self.samples_ms)


def compute_git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def verify_rady_dataset_bytes(data: bytes) -> None:
    actual = compute_git_blob_sha(data)
    if actual != RADY_SOURCE_BLOB_SHA:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="verify_rady_dataset_bytes",
                category="data",
                code="RADY_DATASET_BLOB_MISMATCH",
                expected=RADY_SOURCE_BLOB_SHA,
                actual=actual,
                details=f"source_commit={RADY_SOURCE_COMMIT}",
            )
        )


def build_verified_https_context() -> ssl.SSLContext:
    try:
        import certifi
    except ImportError as exc:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="build_verified_https_context",
                category="dependency",
                code="CERTIFI_NOT_INSTALLED",
                expected="certifi installed from requirements.txt",
                actual="missing",
                details="run: python3 -m pip install -r requirements.txt",
            )
        ) from exc

    return ssl.create_default_context(cafile=certifi.where())


def ensure_rady_dataset(
    destination: Path,
    *,
    allow_download: bool = True,
) -> Path:
    if destination.exists():
        data = destination.read_bytes()
        verify_rady_dataset_bytes(data)
        return destination

    if not allow_download:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="ensure_rady_dataset",
                category="dependency",
                code="RADY_DATASET_MISSING",
                expected=str(destination),
                actual="missing",
                details="download disabled",
            )
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    ssl_context = build_verified_https_context()
    try:
        with urllib.request.urlopen(
            RADY_SOURCE_URL,
            timeout=120,
            context=ssl_context,
        ) as response:
            data = response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="ensure_rady_dataset",
                category="dependency",
                code="RADY_DATASET_DOWNLOAD_FAILED",
                expected=RADY_SOURCE_URL,
                actual=type(exc).__name__,
                details=str(exc),
            )
        ) from exc

    verify_rady_dataset_bytes(data)

    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(destination)
    return destination


def load_rady_latency_profile(
    dataset_path: Path,
    *,
    location: str = PRIMARY_LOCATION,
    location_label: str = PRIMARY_LOCATION_LABEL,
    config: str = PRIMARY_CONFIG,
    config_label: str = PRIMARY_CONFIG_LABEL,
    steady_start_s: float = PRIMARY_STEADY_START_S,
    steady_end_s: float = PRIMARY_STEADY_END_S,
) -> EmpiricalLatencyProfile:
    try:
        data = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="load_rady_latency_profile",
                category="data",
                code="RADY_DATASET_PARSE_FAILED",
                expected="valid JSON dataset",
                actual=type(exc).__name__,
                details=str(exc),
            )
        ) from exc

    if location not in data:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="load_rady_latency_profile",
                category="data",
                code="RADY_LOCATION_MISSING",
                expected=location,
                actual=tuple(sorted(data.keys())),
            )
        )

    location_data = data[location]
    if config not in location_data:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="load_rady_latency_profile",
                category="data",
                code="RADY_CONFIG_MISSING",
                expected=config,
                actual=tuple(sorted(location_data.keys())),
                details=f"location={location}",
            )
        )

    profile_data = location_data[config]
    timestamps = profile_data.get("control_timestamp_s")
    delays = profile_data.get("control_delay_ms")
    if not isinstance(timestamps, list) or not isinstance(delays, list):
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="load_rady_latency_profile",
                category="data",
                code="RADY_CONTROL_SERIES_MISSING",
                expected="control_timestamp_s and control_delay_ms arrays",
                actual=tuple(sorted(profile_data.keys())),
            )
        )
    if len(timestamps) != len(delays):
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="load_rady_latency_profile",
                category="data",
                code="RADY_CONTROL_SERIES_LENGTH_MISMATCH",
                expected=len(timestamps),
                actual=len(delays),
            )
        )

    samples: list[float] = []
    for timestamp, delay in zip(timestamps, delays):
        try:
            t = float(timestamp)
            d = float(delay)
        except (TypeError, ValueError):
            continue
        if (
            math.isfinite(t)
            and math.isfinite(d)
            and d >= 0.0
            and steady_start_s <= t <= steady_end_s
        ):
            samples.append(d)

    if not samples:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="load_rady_latency_profile",
                category="data",
                code="RADY_STEADY_PROFILE_EMPTY",
                expected="at least one finite delay sample",
                actual=0,
                details=(
                    f"location={location}, config={config}, "
                    f"window=[{steady_start_s},{steady_end_s}]"
                ),
            )
        )

    return EmpiricalLatencyProfile(
        source_repository=RADY_SOURCE_REPOSITORY,
        source_commit=RADY_SOURCE_COMMIT,
        source_blob_sha=RADY_SOURCE_BLOB_SHA,
        location=location,
        location_label=location_label,
        config=config,
        config_label=config_label,
        steady_start_s=steady_start_s,
        steady_end_s=steady_end_s,
        samples_ms=tuple(samples),
    )


def percentile(values: tuple[float, ...] | list[float], probability: float) -> float:
    if not values:
        raise ValueError("values must not be empty")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be within [0,1]")
    ordered = sorted(float(value) for value in values)
    index = int(probability * (len(ordered) - 1))
    return ordered[index]


def summarize_latency_profile(profile: EmpiricalLatencyProfile) -> dict[str, float | int]:
    samples = profile.samples_ms
    return {
        "sample_count": len(samples),
        "mean_ms": sum(samples) / len(samples),
        "p50_ms": percentile(samples, 0.50),
        "p90_ms": percentile(samples, 0.90),
        "p95_ms": percentile(samples, 0.95),
        "p99_ms": percentile(samples, 0.99),
        "min_ms": min(samples),
        "max_ms": max(samples),
    }


class EmpiricalLatencySampler:
    def __init__(self, profile: EmpiricalLatencyProfile, seed: int):
        if profile.sample_count <= 0:
            raise ValueError("profile must contain samples")
        self._samples = profile.samples_ms
        self._seed = int(seed)

    def sample_ms(self, key: str) -> float:
        digest = hashlib.sha256(
            f"{self._seed}|{key}".encode("utf-8")
        ).digest()
        index = int.from_bytes(digest[:8], "big") % len(self._samples)
        return self._samples[index]


def validate_packet_loss_probability(p_loss: float) -> float:
    value = float(p_loss)
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="validate_packet_loss_probability",
                category="data",
                code="INVALID_PACKET_LOSS_PROBABILITY",
                expected="finite probability within [0, 1]",
                actual=p_loss,
            )
        )
    return value


def validate_vote_repetitions(vote_repetitions: int) -> int:
    """Bound a no-ACK, sender-side repetition transport experiment.

    One physical remote vote is sent for each copy. Local self-votes remain
    local and are never repeated. The 1-copy setting is the original E2 model.
    """
    if type(vote_repetitions) is not int or not 1 <= vote_repetitions <= 3:
        raise ProtocolError(
            Diagnostic(
                owner="network",
                function="validate_vote_repetitions",
                category="data",
                code="INVALID_VOTE_REPETITIONS",
                expected="integer in {1, 2, 3} (physical copies per remote ballot)",
                actual=vote_repetitions,
            )
        )
    return vote_repetitions


class BernoulliLossSampler:
    def __init__(self, seed: int):
        self._seed = int(seed)

    def is_delivered(self, key: str, p_loss: float) -> bool:
        probability = validate_packet_loss_probability(p_loss)
        digest = hashlib.sha256(
            f"{self._seed}|loss|{key}".encode("utf-8")
        ).digest()
        unit = int.from_bytes(digest[:8], "big") / float(1 << 64)
        return unit >= probability
