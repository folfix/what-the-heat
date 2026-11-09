"""Per-day measurements: comfort metrics for comparing runs, and raw data for later learning."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields

BAND = 0.3
MAX_ROWS = 400


@dataclass
class _Day:
    """Running totals for one calendar day."""

    date: str
    seconds: float = 0.0
    measured_s: float = 0.0
    within_band_s: float = 0.0
    squared_deviation: float = 0.0
    room_sum: float = 0.0
    target_sum: float = 0.0
    heating_known_s: float = 0.0
    heating_s: float = 0.0
    closed_run_s: float = 0.0
    longest_closed_s: float = 0.0
    active_s: float = 0.0
    outdoor_s: float = 0.0
    outdoor_sum: float = 0.0
    water_s: float = 0.0
    water_sum: float = 0.0
    pv_s: float = 0.0
    pv_wh: float = 0.0
    sun_s: float = 0.0
    sun_sum: float = 0.0
    outdoor_correction_s: float = 0.0
    outdoor_correction_sum: float = 0.0
    writes: int = 0

    def row(self) -> dict[str, float | int | str | None]:
        """Return the day as a plain record, with percentages and means."""

        def share(part: float, whole: float) -> float | None:
            return round(part / whole * 100.0, 1) if whole > 0 else None

        def mean(total: float, whole: float) -> float | None:
            return round(total / whole, 2) if whole > 0 else None

        return {
            "date": self.date,
            "hours": round(self.seconds / 3600.0, 2),
            "time_in_band_pct": share(self.within_band_s, self.measured_s),
            "rms_deviation": round(math.sqrt(self.squared_deviation / self.measured_s), 3) if self.measured_s > 0 else None,
            "room_mean": mean(self.room_sum, self.measured_s),
            "target_mean": mean(self.target_sum, self.measured_s),
            "heating_pct": share(self.heating_s, self.heating_known_s),
            "longest_closed_h": round(self.longest_closed_s / 3600.0, 2),
            "active_pct": share(self.active_s, self.seconds),
            "outdoor_mean": mean(self.outdoor_sum, self.outdoor_s),
            "water_mean": mean(self.water_sum, self.water_s),
            "pv_kwh": round(self.pv_wh / 1000.0, 2) if self.pv_s > 0 else None,
            "sun_correction_pct": mean(self.sun_sum, self.sun_s),
            "outdoor_correction_pct": mean(self.outdoor_correction_sum, self.outdoor_correction_s),
            "writes": self.writes,
        }


class DailyLog:
    """Collects measurements and closes a row whenever the date changes."""

    def __init__(self, rows: list[dict] | None = None, current: dict | None = None) -> None:
        self._rows: list[dict] = list(rows or [])
        # Saved state may come from a version with other fields.
        known = {item.name for item in fields(_Day)}
        self._day = _Day(**{key: value for key, value in current.items() if key in known}) if current else None

    @property
    def rows(self) -> list[dict]:
        """Return the completed days, oldest first."""
        return list(self._rows)

    @property
    def today(self) -> dict | None:
        """Return the current day so far."""
        return self._day.row() if self._day else None

    def snapshot(self) -> dict:
        """Return everything needed to continue after a restart."""
        return {"rows": list(self._rows), "current": asdict(self._day) if self._day else None}

    def add(
        self,
        date: str,
        dt_s: float,
        target: float,
        temperature: float | None = None,
        is_heating: bool | None = None,
        is_active: bool = False,
        outdoor: float | None = None,
        water: float | None = None,
        writes: int = 0,
        pv_w: float | None = None,
        sun_correction: float | None = None,
        outdoor_correction: float | None = None,
    ) -> None:
        """Add one interval to the given date.

        `pv_w` is the PV power, and the corrections are the changes of the duty caused by the
        sun and by the outdoor temperature.
        """
        if self._day is None or self._day.date != date:
            if self._day is not None:
                self._rows.append(self._day.row())
                del self._rows[:-MAX_ROWS]
            self._day = _Day(date=date)
        day = self._day
        day.writes += writes
        if dt_s <= 0:
            return
        day.seconds += dt_s
        if is_active:
            day.active_s += dt_s
        if temperature is not None:
            deviation = temperature - target
            day.measured_s += dt_s
            day.room_sum += temperature * dt_s
            day.target_sum += target * dt_s
            day.squared_deviation += deviation * deviation * dt_s
            # Rounded, because 23.3 - 23.0 comes out slightly above 0.3 in floating point.
            if round(abs(deviation), 3) <= BAND:
                day.within_band_s += dt_s
        if is_heating is not None:
            day.heating_known_s += dt_s
            if is_heating:
                day.heating_s += dt_s
                day.closed_run_s = 0.0
            else:
                day.closed_run_s += dt_s
                day.longest_closed_s = max(day.longest_closed_s, day.closed_run_s)
        if outdoor is not None:
            day.outdoor_s += dt_s
            day.outdoor_sum += outdoor * dt_s
        if water is not None:
            day.water_s += dt_s
            day.water_sum += water * dt_s
        if pv_w is not None:
            day.pv_s += dt_s
            day.pv_wh += pv_w * dt_s / 3600.0
        if sun_correction is not None:
            day.sun_s += dt_s
            day.sun_sum += sun_correction * dt_s
        if outdoor_correction is not None:
            day.outdoor_correction_s += dt_s
            day.outdoor_correction_sum += outdoor_correction * dt_s
