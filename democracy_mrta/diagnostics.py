from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ALLOWED_CATEGORIES = {
    "data",
    "time",
    "state",
    "dependency",
    "planning",
    "safety",
    "runtime",
    "contract",
}


@dataclass(frozen=True)
class Diagnostic:
    owner: str
    function: str
    category: str
    code: str
    expected: Any | None = None
    actual: Any | None = None
    details: str | None = None

    def __post_init__(self) -> None:
        if self.category not in ALLOWED_CATEGORIES:
            raise ValueError(f"unsupported diagnostic category: {self.category}")


class ProtocolError(RuntimeError):
    def __init__(self, diagnostic: Diagnostic):
        self.diagnostic = diagnostic
        super().__init__(
            f"{diagnostic.owner}.{diagnostic.function} "
            f"[{diagnostic.category}/{diagnostic.code}] "
            f"expected={diagnostic.expected!r} actual={diagnostic.actual!r} "
            f"details={diagnostic.details!r}"
        )
