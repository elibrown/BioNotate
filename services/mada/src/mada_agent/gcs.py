"""Glasgow Coma Scale: validation, reporting, and the escalation (trend) rules.

Reporting follows glasgowcomascale.org: report the three components; give a total only when no
component is Not Testable (NT). Escalation rules are the NICE CG176 criteria quoted in the
glasgowcomascale.org FAQ. Comparisons only use components testable in both readings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

Score = int | Literal["NT"]
_MAX = {"eye": 4, "verbal": 5, "motor": 6}
_LETTER = {"eye": "E", "verbal": "V", "motor": "M"}
SUSTAINED = timedelta(minutes=30)


class GcsError(ValueError):
    pass


@dataclass(frozen=True)
class GcsReading:
    eye: Score
    verbal: Score
    motor: Score
    timestamp: datetime

    def get(self, comp: str) -> Score:
        return getattr(self, comp)

    @property
    def components(self) -> str:
        return " ".join(f"{_LETTER[c]}{self.get(c)}" for c in _MAX)

    @property
    def total(self) -> int | None:
        vals = [self.get(c) for c in _MAX]
        return None if any(v == "NT" for v in vals) else sum(vals)  # type: ignore[arg-type]

    def as_dict(self) -> dict[str, Any]:
        return {"components": self.components, "eye": self.eye, "verbal": self.verbal, "motor": self.motor,
                "total": self.total, "timestamp": self.timestamp.isoformat()}


def parse_reading(value: Any, timestamp: datetime) -> GcsReading:
    """Validate a GCS answer like {"eye": 3, "verbal": "NT", "motor": 5}."""
    if not isinstance(value, dict):
        raise GcsError("GCS answer must be an object with eye, verbal and motor")
    parsed: dict[str, Score] = {}
    for comp, top in _MAX.items():
        v = value.get(comp)
        if isinstance(v, str) and v.strip().upper() == "NT":
            parsed[comp] = "NT"
        elif isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= top:
            parsed[comp] = v
        else:
            raise GcsError(f"GCS {comp} must be 1-{top} or 'NT' (got {v!r})")
    return GcsReading(parsed["eye"], parsed["verbal"], parsed["motor"], timestamp)


def _comparable_level(a: GcsReading, b: GcsReading) -> tuple[int, int] | None:
    """Sum of the components testable in both readings, for a and for b."""
    comps = [c for c in _MAX if a.get(c) != "NT" and b.get(c) != "NT"]
    if not comps:
        return None
    return sum(a.get(c) for c in comps), sum(b.get(c) for c in comps)  # type: ignore[misc]


@dataclass(frozen=True)
class GcsAlert:
    rule: str
    from_: GcsReading
    to: GcsReading

    @property
    def message(self) -> str:
        return (f"Consciousness is getting worse (GCS {self.from_.components} → {self.to.components}). "
                "Tell the Crew Medical Officer now.")

    def as_dict(self) -> dict[str, Any]:
        return {"rule": self.rule, "from": self.from_.components, "to": self.to.components,
                "from_timestamp": self.from_.timestamp.isoformat(),
                "to_timestamp": self.to.timestamp.isoformat(), "message": self.message}


def check_trend(readings: list[GcsReading]) -> GcsAlert | None:
    """Return an alert if the latest reading meets a NICE escalation rule against any earlier one."""
    if len(readings) < 2:
        return None
    rs = sorted(readings, key=lambda r: r.timestamp)
    latest = rs[-1]
    earlier = rs[:-1]

    for base in earlier:  # large drops: compare latest with every earlier reading
        for comp in ("eye", "verbal"):
            b, l = base.get(comp), latest.get(comp)
            if b != "NT" and l != "NT" and b - l >= 3:  # type: ignore[operator]
                return GcsAlert("drop_eye_or_verbal_ge_3", base, latest)
        b, l = base.motor, latest.motor
        if b != "NT" and l != "NT" and b - l >= 2:  # type: ignore[operator]
            return GcsAlert("drop_motor_ge_2", base, latest)

    # Sustained 1-point drop: from the first reading below a baseline, every later reading stays
    # below it, and the latest is at least 30 min after that first drop.
    for i, base in enumerate(earlier):
        later = rs[i + 1:]
        first_drop = None
        for r in later:
            lv = _comparable_level(base, r)
            if lv and lv[1] <= lv[0] - 1:
                first_drop = first_drop or r
            else:
                first_drop = None  # recovered: the drop is not sustained
        if first_drop is not None and latest.timestamp - first_drop.timestamp >= SUSTAINED:
            return GcsAlert("sustained_drop_1_ge_30min", base, latest)
    return None
