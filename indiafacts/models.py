from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Status(StrEnum):
    ok = "ok"
    unavailable = "unavailable"
    gap = "gap"
    stale = "stale"
    conflict = "conflict"
    unverified = "unverified"


class PeriodType(StrEnum):
    Q = "Q"
    FY = "FY"
    TTM = "TTM"
    point = "point"


class Basis(StrEnum):
    consolidated = "consolidated"
    standalone = "standalone"
    unknown = "unknown"


class AvailabilityKind(StrEnum):
    filed = "filed"
    deadline_estimate = "deadline_estimate"
    unknown = "unknown"


_NO_VALUE = {Status.unavailable, Status.gap}
_TICKER = re.compile(r"[A-Z0-9&-]{1,20}(\.[A-Z]{1,3})?")


class Fact(BaseModel):
    model_config = ConfigDict(frozen=True)

    fact_id: str
    entity_key: str
    metric: str
    value: Decimal | None
    unit: str
    period_start: date | None = None
    period_end: date
    period_type: PeriodType
    fiscal_label: str | None = None
    basis: Basis = Basis.unknown
    source: str
    source_field: str | None = None
    retrieved_at: datetime
    available_from: date | None = None
    availability_kind: AvailabilityKind = AvailabilityKind.unknown
    status: Status = Status.ok
    reason: str = ""
    related_fact_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> Fact:
        if self.status != Status.ok and not self.reason.strip():
            raise ValueError(f"status {self.status} requires a reason")
        if self.status in _NO_VALUE and self.value is not None:
            raise ValueError(f"status {self.status} requires a null value")
        if self.status == Status.ok and self.value is None:
            raise ValueError("status ok requires a value")
        return self

    @staticmethod
    def compute_id(entity_key: str, metric: str, period_end: date, period_type: str, source: str) -> str:
        raw = f"{entity_key}|{metric}|{period_end.isoformat()}|{period_type}|{source}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @classmethod
    def make(cls, **fields) -> Fact:
        fields["fact_id"] = cls.compute_id(
            fields["entity_key"], fields["metric"], fields["period_end"],
            str(fields["period_type"]), fields["source"],
        )
        return cls(**fields)

    def with_(self, **changes) -> Fact:
        return self.model_copy(update=changes)


class Identifier(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: str | None
    status: Status
    reason: str = ""

    @classmethod
    def missing(cls, reason: str) -> Identifier:
        return cls(value=None, status=Status.unavailable, reason=reason)


class Entity(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker_input: str
    ticker: str
    nse_symbol: Identifier
    bse_code: Identifier
    isin: Identifier
    name: str | None = None
    resolution: str = "resolved"
    resolution_reason: str = ""

    @classmethod
    def from_ticker(cls, raw: str) -> Entity:
        ticker = raw.strip().upper()
        if not _TICKER.fullmatch(ticker):
            raise ValueError(f"invalid ticker {raw!r}: expected letters/digits/&/- plus an optional .NS/.BO suffix")
        nse = Identifier(value=ticker[:-3], status=Status.ok) if ticker.endswith(".NS") else \
            Identifier.missing("ticker is not an NSE (.NS) symbol")
        return cls(
            ticker_input=raw,
            ticker=ticker,
            nse_symbol=nse,
            bse_code=Identifier.missing("no identifier source configured"),
            isin=Identifier.missing("no identifier source configured"),
        )

    def unresolved(self, reason: str) -> Entity:
        return self.model_copy(update={"resolution": "unresolved", "resolution_reason": reason})


class FactSet(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity: Entity
    facts: list[Fact]
    retrieved_at: datetime
    not_yet_public: list[Fact] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)
    price_notes: list[str] = Field(default_factory=list)

    def by_metric(self, name: str) -> list[Fact]:
        return [f for f in self.facts if f.metric == name]
