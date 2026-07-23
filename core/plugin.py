"""Plugin interface — Source, Dataset, SniffResult, Catalog, DomainPlugin."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from core.model import CapabilityResult

__all__ = [
    "Capability",
    "Catalog",
    "Dataset",
    "DomainPlugin",
    "SniffResult",
    "Source",
]

# ── Source ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Source:
    paths: tuple[Path, ...]
    media_type: str | None = None


# ── SniffResult ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SniffResult:
    confidence: float
    evidence: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"SniffResult.confidence must be in [0.0, 1.0], got {self.confidence}"
            )


# ── Dataset (minimal cross-domain protocol) ───────────────────────────────────


@runtime_checkable
class Dataset(Protocol):
    @property
    def dataset_id(self) -> str: ...

    @property
    def source(self) -> Source: ...

    def manifest(self) -> list[tuple[str, str]]: ...


# ── Capability / Catalog ──────────────────────────────────────────────────────

type _Cost = Literal["cheap", "moderate", "expensive"]


@dataclass(frozen=True)
class Capability:
    id: str
    description: str
    params_schema: dict[str, object]
    produces: tuple[str, ...]
    renders: bool
    cost: _Cost


@dataclass(frozen=True)
class Catalog:
    capabilities: tuple[Capability, ...]
    measurement_types: tuple[str, ...]


# ── DomainPlugin ──────────────────────────────────────────────────────────────


class DomainPlugin(Protocol):
    name: str
    version: str

    def sniff(self, source: Source) -> SniffResult: ...

    def open(self, source: Source) -> Dataset: ...

    def catalog(self) -> Catalog: ...

    def run(
        self, capability_id: str, ds: Dataset, **params: object
    ) -> CapabilityResult: ...
