"""The integration inside Home Assistant, with a stand-in thermostat entity."""

import asyncio
import json
import logging
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.frontend import DATA_PANELS
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.what_the_heat.const import (
    CONF_OUTDOOR_ENTITY,
    CONF_PHASE_OFFSET,
    CONF_PV_ENTITY,
    CONF_TARGET,
    CONF_THERMOSTAT,
    CONF_WATER_TEMPERATURE,
    DOMAIN,
    SETTINGS_ID,
    VERSION,
)
from custom_components.what_the_heat.coordinator import merged_config
from custom_components.what_the_heat.diagnostics import async_get_config_entry_diagnostics
from custom_components.what_the_heat.panel import PANEL_URL_PATH

THERMOSTAT = "climate.pilot_thermostat"
ROOM = "climate.pilot"
HEAT_PUMP = "climate.heat_pump"
OUTDOOR = "sensor.outdoor"
PV = "sensor.pv_power"
SUN = "sensor.pilot_sun_correction"
MODE = "select.pilot_mode"
TARGET = "number.pilot_target"
DUTY = "sensor.pilot_duty"
STATUS = "sensor.pilot_status"
WATER = "sensor.pilot_water_temperature"
PROBLEM = "binary_sensor.pilot_problem"
VALVE = "binary_sensor.pilot_valve_requested"
WRITES = "sensor.pilot_setpoint_writes"
IN_BAND = "sensor.pilot_time_in_band_today"
LEARNED = "sensor.pilot_learned_demand"
RESET = "button.pilot_reset_learning"
FORM = {CONF_TARGET: 21.0, CONF_PHASE_OFFSET: 0}


def set_thermostat(
    hass: HomeAssistant,
    temperature: float | None = 20.0,
    setpoint: float | None = 19.0,
    state: str = "heat",
    action: str = "idle",
    entity_id: str = THERMOSTAT,
) -> None:
    hass.states.async_set(
        entity_id,
        state,
        {
            "current_temperature": temperature,
            "temperature": setpoint,
            "hvac_action": action,
            "hvac_modes": ["off", "heat"],
            "min_temp": 5.0,
            "max_temp": 35.0,
            "target_temp_step": 0.5,
        },
    )


@pytest.fixture
async def set_temperature_calls(hass: HomeAssistant):
    # The climate component replaces any service registered before it loads.
    assert await async_setup_component(hass, "climate", {})
    return async_mock_service(hass, "climate", "set_temperature")


@pytest.fixture
async def set_hvac_mode_calls(hass: HomeAssistant):
    assert await async_setup_component(hass, "climate", {})
    return async_mock_service(hass, "climate", "set_hvac_mode")


def room_entry(title: str = "Pilot", thermostat: str = THERMOSTAT, **overrides) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=title,
        unique_id=thermostat,
        data={"name": title, CONF_THERMOSTAT: thermostat, **FORM, **overrides},
    )


async def add_room(hass: HomeAssistant, title: str = "Pilot", thermostat: str = THERMOSTAT, **overrides) -> MockConfigEntry:
    entry = room_entry(title, thermostat, **overrides)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def add_stored_room(hass: HomeAssistant, hass_storage, **runner) -> MockConfigEntry:
    """A room that already ran, with the given saved controller state."""
    entry = room_entry()
    entry.add_to_hass(hass)
    key = f"{DOMAIN}.{entry.entry_id}"
    hass_storage[key] = {"version": 1, "minor_version": 1, "key": key, "data": {"runner": runner}}
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def select_mode(hass: HomeAssistant, mode: str) -> None:
    await hass.services.async_call("select", "select_option", {"entity_id": MODE, "option": mode}, blocking=True)
    await hass.async_block_till_done()


def settings_entry(**options) -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, title="Shared settings", unique_id=SETTINGS_ID, data={}, options=options)


async def add_settings(hass: HomeAssistant, **options) -> MockConfigEntry:
    entry = settings_entry(**options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def change_settings(hass: HomeAssistant, entry: MockConfigEntry, **options) -> None:
    """Change the shared settings with Configure, as the owner would."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "settings"
    result = await hass.config_entries.options.async_configure(result["flow_id"], options)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()


async def tick(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_the_first_setup_asks_for_the_shared_settings(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["step_id"] == "settings"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_WATER_TEMPERATURE: 32.0, CONF_PV_ENTITY: PV}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Shared settings"
    assert result["result"].options == {CONF_WATER_TEMPERATURE: 32.0, CONF_PV_ENTITY: PV}
    await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["step_id"] == "user"


async def test_add_a_room_through_the_form(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    await add_settings(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Pilot", CONF_THERMOSTAT: THERMOSTAT, **FORM},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Pilot"
    await hass.async_block_till_done()
    assert hass.states.get(MODE).state == "active"


async def test_a_thermostat_can_belong_to_only_one_room(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    await add_settings(hass)
    await add_room(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Again", CONF_THERMOSTAT: THERMOSTAT, **FORM},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_change(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    entry = await add_room(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_PHASE_OFFSET: 15})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert merged_config(entry)[CONF_PHASE_OFFSET] == 15


async def test_an_outdoor_sensor_set_on_a_room_is_left_out(hass: HomeAssistant) -> None:
    # Older versions had one per room. It is now shared by all rooms.
    set_thermostat(hass)
    hass.states.async_set(OUTDOOR, "4.2")
    entry = await add_room(hass, **{CONF_OUTDOOR_ENTITY: OUTDOOR})
    assert CONF_OUTDOOR_ENTITY not in merged_config(entry)
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["today"]["outdoor_mean"] is None


async def test_new_room_takes_control_right_away(hass: HomeAssistant, set_temperature_calls, set_hvac_mode_calls) -> None:
    set_thermostat(hass, temperature=18.0, setpoint=15.0, state="off", action="off")
    await add_room(hass)
    assert hass.states.get(MODE).state == "active"
    assert [call.data["hvac_mode"] for call in set_hvac_mode_calls] == ["heat"]
    assert [call.data["temperature"] for call in set_temperature_calls] == [24.0]


async def test_observe_mode_writes_nothing(hass: HomeAssistant, hass_storage, set_temperature_calls, set_hvac_mode_calls) -> None:
    set_thermostat(hass, temperature=18.0, setpoint=15.0, state="off", action="off")
    entry = await add_stored_room(hass, hass_storage, mode="observe")
    for _ in range(5):
        await tick(hass, entry)
    assert hass.states.get(MODE).state == "observe"
    assert float(hass.states.get(DUTY).state) > 0
    assert hass.states.get(VALVE).state == "on"
    assert hass.states.get(WRITES).state == "0"
    assert set_temperature_calls == []
    assert set_hvac_mode_calls == []


async def test_active_mode_opens_a_cold_room(hass: HomeAssistant, set_temperature_calls) -> None:
    set_thermostat(hass, temperature=20.0, setpoint=15.0)
    await add_room(hass)
    await select_mode(hass, "active")
    assert hass.states.get(MODE).state == "active"
    assert len(set_temperature_calls) == 1
    assert set_temperature_calls[0].data == {"entity_id": THERMOSTAT, "temperature": 24.0}
    assert hass.states.get(WRITES).state == "1"


async def test_decisions_and_commands_are_logged(hass: HomeAssistant, set_temperature_calls, caplog) -> None:
    caplog.set_level(logging.DEBUG, logger="custom_components.what_the_heat")
    set_thermostat(hass, temperature=20.0, setpoint=15.0)
    await add_room(hass)
    assert "duty=" in caplog.text
    assert "set_temperature {'temperature': 24.0}" in caplog.text
    await select_mode(hass, "handback")
    assert "mode active -> handback" in caplog.text


async def test_active_mode_switches_on_a_thermostat_that_is_off(
    hass: HomeAssistant, set_temperature_calls, set_hvac_mode_calls
) -> None:
    set_thermostat(hass, temperature=20.0, setpoint=24.0, state="off", action="off")
    await add_room(hass)
    await select_mode(hass, "active")
    assert len(set_hvac_mode_calls) == 1
    assert set_hvac_mode_calls[0].data == {"entity_id": THERMOSTAT, "hvac_mode": "heat"}


async def test_handback_writes_the_plain_target_once(hass: HomeAssistant, set_temperature_calls) -> None:
    set_thermostat(hass, temperature=20.0, setpoint=24.0, action="heating")
    entry = await add_room(hass)
    await select_mode(hass, "handback")
    assert [call.data["temperature"] for call in set_temperature_calls] == [21.0]
    set_thermostat(hass, temperature=20.0, setpoint=21.0, action="heating")
    for _ in range(5):
        await tick(hass, entry)
    assert len(set_temperature_calls) == 1


async def test_target_change_moves_the_setpoint(hass: HomeAssistant, set_temperature_calls) -> None:
    set_thermostat(hass, temperature=20.0, setpoint=24.0, action="heating")
    await add_room(hass)
    await select_mode(hass, "active")
    await hass.services.async_call("number", "set_value", {"entity_id": TARGET, "value": 22.0}, blocking=True)
    await hass.async_block_till_done()
    assert float(hass.states.get(TARGET).state) == 22.0
    assert set_temperature_calls[-1].data["temperature"] == 25.0


async def test_runs_every_minute_on_its_own(hass: HomeAssistant, set_temperature_calls) -> None:
    set_thermostat(hass, temperature=20.8, setpoint=18.0)
    await add_room(hass)
    # The first run has no elapsed time to measure, so the metric appears on the second.
    assert hass.states.get(IN_BAND).state == "unknown"
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert float(hass.states.get(IN_BAND).state) == 100.0


async def test_unavailable_thermostat_gets_no_commands(hass: HomeAssistant, set_temperature_calls) -> None:
    hass.states.async_set(THERMOSTAT, "unavailable")
    entry = await add_room(hass)
    await select_mode(hass, "active")
    await tick(hass, entry)
    assert hass.states.get(STATUS).state == "initializing"
    assert set_temperature_calls == []


async def test_thermostat_missing_at_startup_is_picked_up_later(hass: HomeAssistant, set_temperature_calls) -> None:
    entry = await add_room(hass)
    await select_mode(hass, "active")
    assert set_temperature_calls == []
    set_thermostat(hass, temperature=20.0, setpoint=15.0)
    await tick(hass, entry)
    assert [call.data["temperature"] for call in set_temperature_calls] == [24.0]
    assert hass.states.get(STATUS).state == "normal"


async def test_failing_service_call_does_not_stop_the_room(hass: HomeAssistant, caplog) -> None:
    assert await async_setup_component(hass, "climate", {})

    async def fail(_call) -> None:
        raise HomeAssistantError("device offline")

    hass.services.async_register("climate", "set_temperature", fail)
    set_thermostat(hass, temperature=20.0, setpoint=15.0)
    entry = await add_room(hass)
    await select_mode(hass, "active")
    await tick(hass, entry)
    assert entry.runtime_data.last_update_success
    assert hass.states.get(MODE).state == "active"
    assert "device offline" in caplog.text


async def test_room_has_its_own_thermostat_entity(hass: HomeAssistant) -> None:
    set_thermostat(hass, temperature=20.2, setpoint=18.0, action="idle")
    await add_room(hass)
    state = hass.states.get(ROOM)
    assert state.state == "heat"
    assert state.attributes["current_temperature"] == 20.2
    assert state.attributes["temperature"] == 21.0
    assert state.attributes["preset_mode"] == "active"
    assert state.attributes["hvac_action"] == "idle"


async def test_thermostat_entity_uses_current_home_assistant_names(hass: HomeAssistant, caplog) -> None:
    set_thermostat(hass)
    await add_room(hass)
    assert "provides the deprecated" not in caplog.text


async def test_thermostat_entity_changes_target_and_mode(hass: HomeAssistant) -> None:
    set_thermostat(hass, temperature=20.0, setpoint=18.0)
    await add_room(hass)
    await hass.services.async_call("climate", "set_temperature", {"entity_id": ROOM, "temperature": 22.5}, blocking=True)
    await hass.async_block_till_done()
    assert float(hass.states.get(TARGET).state) == 22.5
    await hass.services.async_call("climate", "set_preset_mode", {"entity_id": ROOM, "preset_mode": "handback"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(MODE).state == "handback"
    assert hass.states.get(ROOM).attributes["preset_mode"] == "handback"


async def test_a_room_cannot_control_its_own_entity(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    await add_settings(hass)
    await add_room(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Loop", CONF_THERMOSTAT: ROOM, **FORM},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_THERMOSTAT: "own_entity"}


async def test_leaving_active_for_observe_gives_the_target_back(hass: HomeAssistant, set_temperature_calls) -> None:
    set_thermostat(hass, temperature=20.0, setpoint=15.0)
    entry = await add_room(hass)
    await select_mode(hass, "active")
    assert set_temperature_calls[-1].data["temperature"] == 24.0
    await select_mode(hass, "observe")
    assert set_temperature_calls[-1].data["temperature"] == 21.0
    count = len(set_temperature_calls)
    await tick(hass, entry)
    assert len(set_temperature_calls) == count


async def test_water_temperature_defaults_to_30(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    await add_room(hass)
    assert float(hass.states.get(WATER).state) == 30.0


async def test_water_temperature_is_shared_by_all_rooms(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    set_thermostat(hass, entity_id="climate.other_thermostat")
    settings = await add_settings(hass)
    await add_room(hass)
    await add_room(hass, title="Other", thermostat="climate.other_thermostat")
    await change_settings(hass, settings, **{CONF_WATER_TEMPERATURE: 32.5})
    assert float(hass.states.get(WATER).state) == 32.5
    assert float(hass.states.get("sensor.other_water_temperature").state) == 32.5


async def test_water_temperature_scales_the_duty(hass: HomeAssistant) -> None:
    set_thermostat(hass, temperature=20.7)
    settings = await add_settings(hass)
    await add_room(hass)
    cool = float(hass.states.get(DUTY).state)
    await change_settings(hass, settings, **{CONF_WATER_TEMPERATURE: 38.0})
    assert float(hass.states.get(DUTY).state) < cool


async def test_a_room_starts_with_the_shared_settings_already_there(hass: HomeAssistant) -> None:
    # Home Assistant may start a room before the settings entry, so the room reads it itself.
    settings_entry(**{CONF_WATER_TEMPERATURE: 33.0}).add_to_hass(hass)
    set_thermostat(hass)
    await add_room(hass)
    assert float(hass.states.get(WATER).state) == 33.0


async def test_water_temperature_stays_within_limits(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    settings = await add_settings(hass)
    await add_room(hass)
    for value in (19.5, 38.5):
        with pytest.raises(vol.Invalid):
            await change_settings(hass, settings, **{CONF_WATER_TEMPERATURE: value})
    assert float(hass.states.get(WATER).state) == 30.0


async def test_a_shared_sensor_can_be_removed(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    hass.states.async_set(PV, "4000", {"unit_of_measurement": "W", "device_class": "power"})
    settings = await add_settings(hass, **{CONF_PV_ENTITY: PV})
    await add_room(hass)
    assert hass.states.get(SUN).state != "unknown"
    await change_settings(hass, settings, **{CONF_WATER_TEMPERATURE: 30.0})
    assert hass.states.get(SUN).state == "unknown"


async def test_without_the_shared_settings_rooms_use_the_defaults(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    settings = await add_settings(hass, **{CONF_WATER_TEMPERATURE: 34.0})
    await add_room(hass)
    assert float(hass.states.get(WATER).state) == 34.0
    await hass.config_entries.async_remove(settings.entry_id)
    await hass.async_block_till_done()
    assert float(hass.states.get(WATER).state) == 30.0


async def test_without_pv_there_is_no_sun_correction(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    await add_room(hass)
    assert hass.states.get(SUN).state == "unknown"


async def test_pv_power_becomes_a_share_of_full_sun_in_any_unit(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    entry = await add_room(hass)
    hass.states.async_set(PV, "4.0", {"unit_of_measurement": "kW", "device_class": "power"})
    await add_settings(hass, **{CONF_PV_ENTITY: PV})
    assert hass.states.get(SUN).attributes["sun_pct"] == 100.0
    hass.states.async_set(PV, "1000", {"unit_of_measurement": "W", "device_class": "power"})
    await tick(hass, entry)
    state = hass.states.get(SUN)
    assert state.attributes["sun_pct"] == 25.0
    # Nothing has been learned about the sun yet, so it changes nothing.
    assert float(state.state) == 0.0
    assert (state.attributes["sunny_days"], state.attributes["active"]) == (0, False)


async def test_what_a_room_learned_about_the_sun_is_restored_and_used(hass: HomeAssistant, hass_storage, set_temperature_calls) -> None:
    set_thermostat(hass, temperature=21.0, setpoint=24.0, action="heating")
    hass.states.async_set(PV, "4000", {"unit_of_measurement": "W", "device_class": "power"})
    settings_entry(**{CONF_PV_ENTITY: PV}).add_to_hass(hass)
    entry = room_entry()
    entry.add_to_hass(hass)
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"{DOMAIN}.{entry.entry_id}",
        "data": {"runner": {"mode": "active", "target": 21.0, "integral": 30.0, "solar": {"values": [40.0] * 24, "sunny_days": 4}}},
    }
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(SUN)
    assert (state.attributes["sunny_days"], state.attributes["active"]) == (4, True)
    assert float(state.state) < 0.0
    assert entry.runtime_data.runner.snapshot()["solar"]["values"] == [40.0] * 24


async def test_heat_pump_is_neither_read_nor_changed(hass: HomeAssistant, set_temperature_calls) -> None:
    hass.states.async_set(HEAT_PUMP, "heat", {"temperature": 40.0, "current_temperature": 55.7})
    set_thermostat(hass, temperature=20.0, setpoint=15.0)
    # A room set up with an older version still names the heat pump in its settings.
    await add_room(hass, buffer_entity=HEAT_PUMP, buffer_fallback=34.0)
    await select_mode(hass, "active")
    assert float(hass.states.get(WATER).state) == 30.0
    assert hass.states.get(PROBLEM).state == "off"
    assert {call.data["entity_id"] for call in set_temperature_calls} == {THERMOSTAT}


async def test_a_running_room_from_an_older_version_keeps_working(
    hass: HomeAssistant, hass_storage, entity_registry: er.EntityRegistry, set_temperature_calls
) -> None:
    set_thermostat(hass, temperature=18.8, setpoint=24.0, action="heating")
    entry = room_entry(buffer_entity=HEAT_PUMP, buffer_fallback=34.0)
    entry.add_to_hass(hass)
    old = entity_registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_assumed_buffer_temperature", config_entry=entry
    )
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"{DOMAIN}.{entry.entry_id}",
        "data": {
            "runner": {"mode": "active", "target": 21.0, "integral": 12.0, "carry_s": 0.0, "writes": 2},
            "log": {
                "rows": [{"date": "2026-11-04", "buffer_mean": 34.0}],
                "current": {"date": dt_util.now().date().isoformat(), "seconds": 3600.0, "buffer_s": 3600.0, "buffer_sum": 122400.0},
            },
            "last_buffer": 34.0,
        },
    }
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(MODE).state == "active"
    assert int(hass.states.get(WRITES).state) == 2
    assert entity_registry.async_get(old.entity_id) is None
    assert float(hass.states.get(WATER).state) == 30.0
    assert set_temperature_calls == []


async def test_sidebar_panel_follows_the_rooms(hass: HomeAssistant) -> None:
    hass.http = Mock(async_register_static_paths=AsyncMock())
    set_thermostat(hass)
    # The shared settings are no room, so they do not keep the page.
    await add_settings(hass)
    entry = await add_room(hass)
    panels = hass.data[DATA_PANELS]
    assert PANEL_URL_PATH in panels
    assert panels[PANEL_URL_PATH].sidebar_title == "What the Heat"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert PANEL_URL_PATH in panels
    assert hass.http.async_register_static_paths.await_count == 1
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert PANEL_URL_PATH not in panels


async def test_rooms_starting_together_all_load_and_share_one_page(hass: HomeAssistant) -> None:
    registered = []

    async def register(configs) -> None:
        # Like the real server: it waits for a worker thread, and refuses a second route.
        await asyncio.sleep(0.05)
        if registered:
            raise RuntimeError("Added route will never be executed, method GET is already registered")
        registered.extend(configs)

    hass.http = Mock(async_register_static_paths=register)
    second_thermostat = "climate.second_thermostat"
    set_thermostat(hass)
    set_thermostat(hass, entity_id=second_thermostat)
    entries = [room_entry(), room_entry("Second", second_thermostat)]
    for entry in entries:
        entry.add_to_hass(hass)
    # This is how Home Assistant starts: all rooms of the integration at the same time.
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    assert [entry.state for entry in entries] == [ConfigEntryState.LOADED] * 2
    assert len(registered) == 1
    assert PANEL_URL_PATH in hass.data[DATA_PANELS]


async def test_room_is_controlled_even_if_the_page_cannot_be_added(hass: HomeAssistant, set_temperature_calls) -> None:
    hass.http = Mock(async_register_static_paths=AsyncMock(side_effect=RuntimeError("no page")))
    set_thermostat(hass, temperature=20.0, setpoint=18.0)
    entry = await add_room(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert PANEL_URL_PATH not in hass.data.get(DATA_PANELS, {})
    await select_mode(hass, "active")
    assert set_temperature_calls[-1].data["temperature"] == 24.0


async def test_unload_gives_the_target_back_when_active(hass: HomeAssistant, set_temperature_calls) -> None:
    set_thermostat(hass, temperature=20.0, setpoint=15.0)
    entry = await add_room(hass)
    await select_mode(hass, "active")
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert set_temperature_calls[-1].data["temperature"] == 21.0


async def test_unload_writes_nothing_when_observing(hass: HomeAssistant, hass_storage, set_temperature_calls) -> None:
    set_thermostat(hass, temperature=20.0, setpoint=15.0)
    entry = await add_stored_room(hass, hass_storage, mode="observe")
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert set_temperature_calls == []


async def test_state_survives_a_reload(hass: HomeAssistant, set_temperature_calls) -> None:
    set_thermostat(hass, temperature=20.0, setpoint=15.0)
    entry = await add_room(hass)
    await select_mode(hass, "active")
    await hass.services.async_call("number", "set_value", {"entity_id": TARGET, "value": 22.5}, blocking=True)
    await hass.async_block_till_done()
    writes = hass.states.get(WRITES).state
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(MODE).state == "active"
    assert float(hass.states.get(TARGET).state) == 22.5
    assert int(hass.states.get(WRITES).state) >= int(writes)


async def test_saved_state_is_restored(hass: HomeAssistant, hass_storage, set_temperature_calls) -> None:
    set_thermostat(hass, temperature=21.0, setpoint=24.0, action="heating")
    entry = room_entry()
    entry.add_to_hass(hass)
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"{DOMAIN}.{entry.entry_id}",
        "data": {
            "runner": {"mode": "active", "target": 20.5, "integral": 42.0, "carry_s": 60.0, "writes": 7},
            "log": {"rows": [{"date": "2026-11-01", "writes": 3}], "current": None},
        },
    }
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(MODE).state == "active"
    assert float(hass.states.get(TARGET).state) == 20.5
    assert entry.runtime_data.runner.snapshot()["integral"] >= 41.0
    assert int(hass.states.get(WRITES).state) >= 7


async def add_room_that_has_learned(hass: HomeAssistant, hass_storage) -> MockConfigEntry:
    """A room at its target, with 8 hours of data behind an integral of 42."""
    set_thermostat(hass, temperature=21.0, setpoint=24.0, action="heating")
    entry = room_entry()
    entry.add_to_hass(hass)
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"{DOMAIN}.{entry.entry_id}",
        "data": {
            "runner": {
                "mode": "active",
                "target": 21.0,
                "integral": 42.0,
                "carry_s": 60.0,
                "heating_share": 0.4,
                "observed_s": 86400.0,
                "learned_s": 8 * 3600.0,
                "writes": 7,
            },
            "log": {"rows": [{"date": "2026-11-01", "writes": 3}], "current": None},
        },
    }
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def press_reset(hass: HomeAssistant) -> None:
    await hass.services.async_call("button", "press", {"entity_id": RESET}, blocking=True)
    await hass.async_block_till_done()


async def test_new_room_has_learned_nothing(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    await add_room(hass)
    state = hass.states.get(LEARNED)
    assert state.state == "unknown"
    assert state.attributes["source"] == "controller"
    assert state.attributes["learned_from_hours"] == 0.0
    assert state.attributes["recent_heating_pct"] is None


async def test_learned_demand_is_shown_with_its_details(hass: HomeAssistant, hass_storage, set_temperature_calls) -> None:
    await add_room_that_has_learned(hass, hass_storage)
    state = hass.states.get(LEARNED)
    # 30 degree water with a target of 21 gives a scale of 10 / 6.
    assert float(state.state) == pytest.approx(70.0, abs=0.5)
    assert state.attributes["source"] == "controller"
    assert state.attributes["learned_from_hours"] == pytest.approx(8.0, abs=0.1)
    assert state.attributes["recent_heating_pct"] == pytest.approx(40.0, abs=1.0)


async def test_reset_button_forgets_what_was_learned(hass: HomeAssistant, hass_storage, set_temperature_calls) -> None:
    entry = await add_room_that_has_learned(hass, hass_storage)
    await press_reset(hass)
    state = entry.runtime_data.runner.snapshot()
    assert state["integral"] == pytest.approx(0.0, abs=0.01)
    assert state["carry_s"] == 0.0
    assert state["observed_s"] < 60.0
    assert state["learned_s"] < 60.0
    assert hass.states.get(LEARNED).state == "unknown"
    saved = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]["runner"]
    assert saved["integral"] == pytest.approx(0.0, abs=0.01)


async def test_reset_keeps_the_mode_target_measurements_and_setpoint(hass: HomeAssistant, hass_storage, set_temperature_calls) -> None:
    entry = await add_room_that_has_learned(hass, hass_storage)
    await press_reset(hass)
    assert hass.states.get(MODE).state == "active"
    assert float(hass.states.get(TARGET).state) == 21.0
    assert int(hass.states.get(WRITES).state) >= 7
    assert entry.runtime_data.log.rows == [{"date": "2026-11-01", "writes": 3}]
    assert set_temperature_calls == []


async def test_reset_survives_a_reload(hass: HomeAssistant, hass_storage, set_temperature_calls) -> None:
    entry = await add_room_that_has_learned(hass, hass_storage)
    await press_reset(hass)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.runner.snapshot()["integral"] == pytest.approx(0.0, abs=0.01)
    assert hass.states.get(LEARNED).state == "unknown"


async def test_reset_while_observing_writes_nothing(hass: HomeAssistant, hass_storage, set_temperature_calls) -> None:
    set_thermostat(hass, temperature=20.0, setpoint=15.0)
    await add_stored_room(hass, hass_storage, mode="observe")
    await press_reset(hass)
    assert set_temperature_calls == []


async def test_diagnostics_contain_the_daily_measurements(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    hass.states.async_set(OUTDOOR, "4.2")
    hass.states.async_set(PV, "3600", {"unit_of_measurement": "W", "device_class": "power"})
    settings = await add_settings(hass, **{CONF_OUTDOOR_ENTITY: OUTDOOR, CONF_PV_ENTITY: PV})
    entry = await add_room(hass)
    await asyncio.sleep(0.01)
    await tick(hass, entry)
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["config"][CONF_THERMOSTAT] == THERMOSTAT
    assert result["shared"]["outdoor_entity"] == OUTDOOR
    assert result["shared"]["sun"]["reference_w"] == 3600.0
    assert result["runner"]["mode"] == "active"
    assert result["learned"]["source"] == "controller"
    assert result["learned"]["sunny_days"] == 0
    assert result["today"]["date"] == dt_util.now().date().isoformat()
    assert result["today"]["outdoor_mean"] == 4.2
    assert result["today"]["water_mean"] == 30.0
    assert result["today"]["pv_kwh"] is not None
    assert result["days"] == []
    shared = await async_get_config_entry_diagnostics(hass, settings)
    assert shared == {"shared": result["shared"]}


async def test_state_is_saved_regularly(hass: HomeAssistant, hass_storage, freezer) -> None:
    set_thermostat(hass)
    entry = await add_room(hass)
    key = f"{DOMAIN}.{entry.entry_id}"
    for _ in range(4):
        freezer.tick(timedelta(seconds=61))
        await tick(hass, entry)
    assert key not in hass_storage
    freezer.tick(timedelta(seconds=61))
    await tick(hass, entry)
    freezer.tick(timedelta(seconds=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass_storage[key]["data"]["runner"]["mode"] == "active"


async def test_removing_a_room_deletes_its_stored_state(hass: HomeAssistant, hass_storage) -> None:
    set_thermostat(hass)
    entry = await add_room(hass)
    entry_key = f"{DOMAIN}.{entry.entry_id}"
    await tick(hass, entry)
    await entry.runtime_data._store.async_save(entry.runtime_data.snapshot())
    assert entry_key in hass_storage
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert entry_key not in hass_storage


def test_version_matches_the_manifest() -> None:
    manifest = json.loads(Path("custom_components/what_the_heat/manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == VERSION


def test_panel_file_exists() -> None:
    assert Path("custom_components/what_the_heat/frontend/panel.js").is_file()


def test_translations_match_strings() -> None:
    base = Path("custom_components/what_the_heat")
    assert (base / "strings.json").read_text(encoding="utf-8") == (base / "translations/en.json").read_text(encoding="utf-8")
