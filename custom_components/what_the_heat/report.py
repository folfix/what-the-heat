"""A full report of the last days in one file, for evaluating the rooms elsewhere.

It holds the raw history of the thermostats, the outdoor and PV sensors and the rooms' own
entities from the recorder, and everything each room has learned. Entity names and room
titles stay in it, so it belongs to the owner, not to the public repository.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.http import KEY_HASS
from homeassistant.helpers.json import json_bytes
from homeassistant.util import dt as dt_util

from .const import CONF_THERMOSTAT, DOMAIN, VERSION, is_settings_entry
from .coordinator import merged_config
from .settings import async_get_settings

REPORT_URL = f"/api/{DOMAIN}/report"
DEFAULT_DAYS = 7
MAX_DAYS = 30
# The rooms' own entities worth having over time. The others follow from these.
ROOM_KEYS = (
    "mode",
    "status",
    "problem",
    "duty",
    "requested_setpoint",
    "integral",
    "sun_correction",
    "outdoor_correction",
    "water_temperature",
)
# What the controller reads from a thermostat, besides its state.
THERMOSTAT_ATTRIBUTES = ("current_temperature", "temperature", "hvac_action")
_REGISTERED = f"{DOMAIN}_report_registered"


def _value(value: Any) -> Any:
    """Numbers as numbers, rounded to keep the file small, and anything else as it is."""
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return value


def _rows(states: list[State], attributes: tuple[str, ...]) -> list[list[Any]]:
    return [
        [round(state.last_updated.timestamp()), _value(state.state), *(state.attributes.get(name) for name in attributes)]
        for state in states
    ]


async def _async_history(
    hass: HomeAssistant, start: datetime, end: datetime, thermostats: list[str], others: list[str]
) -> dict[str, list[list[Any]]] | None:
    """Return the recorded rows of each entity, or None without a recorder."""
    if "recorder" not in hass.config.components:
        return None
    from homeassistant.components.recorder import get_instance, history  # noqa: PLC0415

    entity_ids = sorted(set(thermostats) | set(others))
    if not entity_ids:
        return {}
    # Every recorded change, attributes included, and the state at the start.
    states = await get_instance(hass).async_add_executor_job(
        history.get_significant_states, hass, start, end, entity_ids, None, True, False, False, False
    )
    return {
        entity_id: _rows(rows, THERMOSTAT_ATTRIBUTES if entity_id in thermostats else ())
        for entity_id, rows in states.items()
    }


async def async_build_report(hass: HomeAssistant, days: int = DEFAULT_DAYS) -> dict[str, Any]:
    """Collect the last days of all rooms into one record."""
    end = dt_util.utcnow()
    start = end - timedelta(days=days)
    settings = await async_get_settings(hass)
    registry = er.async_get(hass)
    rooms: list[dict[str, Any]] = []
    thermostats: list[str] = []
    others = [entity for entity in (settings.outdoor_entity, settings.pv_entity) if entity]
    for entry in hass.config_entries.async_entries(DOMAIN):
        if is_settings_entry(entry) or entry.state is not ConfigEntryState.LOADED:
            continue
        coordinator = entry.runtime_data
        config = merged_config(entry)
        entities = {
            item.translation_key: item.entity_id
            for item in er.async_entries_for_config_entry(registry, entry.entry_id)
            if item.translation_key in ROOM_KEYS
        }
        thermostats.append(config[CONF_THERMOSTAT])
        others.extend(entities.values())
        rooms.append(
            {
                "title": entry.title,
                "thermostat": config[CONF_THERMOSTAT],
                "entities": entities,
                "config": config,
                "runner": coordinator.runner.snapshot(),
                "learned": asdict(coordinator.runner.learned()),
                "today": coordinator.log.today,
                "days": coordinator.log.rows,
            }
        )
    return {
        "report": {
            "integration_version": VERSION,
            "home_assistant_version": HA_VERSION,
            "created": end.isoformat(),
            "start": start.isoformat(),
            "days": days,
            "time_zone": hass.config.time_zone,
            # Solar time is UTC plus this many hours. Rounded, so that it does not give the place away.
            "solar_offset_h": round(hass.config.longitude / 15.0, 1),
            "history_rows": (
                "[time in seconds since 1970 UTC, state], and for a thermostat also "
                + ", ".join(THERMOSTAT_ATTRIBUTES)
            ),
        },
        "shared": settings.snapshot(),
        "rooms": rooms,
        "history": await _async_history(hass, start, end, thermostats, others),
    }


class ReportView(HomeAssistantView):
    """Hands out the report as a file, to the page or any signed-in client."""

    url = REPORT_URL
    name = f"api:{DOMAIN}:report"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Return the report of the last days, by default 7."""
        try:
            days = min(MAX_DAYS, max(1, int(request.query.get("days", DEFAULT_DAYS))))
        except ValueError:
            return self.json_message("days must be a whole number", HTTPStatus.BAD_REQUEST)
        report = await async_build_report(request.app[KEY_HASS], days)
        name = f"what-the-heat-report-{dt_util.now().date().isoformat()}.json"
        return web.Response(
            body=json_bytes(report),
            content_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )


def register_report(hass: HomeAssistant) -> None:
    """Make the report available, once. A route cannot be removed, so it stays across reloads."""
    if hass.http is None or hass.data.get(_REGISTERED):
        return
    hass.http.register_view(ReportView())
    hass.data[_REGISTERED] = True
