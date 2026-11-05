"""The integration inside Home Assistant, with a stand-in thermostat entity."""

import asyncio
from datetime import timedelta

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.what_the_heat.const import (
    CONF_BUFFER_ENTITY,
    CONF_BUFFER_FALLBACK,
    CONF_OUTDOOR_ENTITY,
    CONF_PHASE_OFFSET,
    CONF_TARGET,
    CONF_THERMOSTAT,
    DOMAIN,
)
from custom_components.what_the_heat.diagnostics import async_get_config_entry_diagnostics

THERMOSTAT = "climate.pilot_thermostat"
HEAT_PUMP = "climate.heat_pump"
OUTDOOR = "sensor.outdoor"
MODE = "select.pilot_mode"
TARGET = "number.pilot_target"
DUTY = "sensor.pilot_duty"
STATUS = "sensor.pilot_status"
BUFFER = "sensor.pilot_assumed_buffer_temperature"
PROBLEM = "binary_sensor.pilot_problem"
VALVE = "binary_sensor.pilot_valve_requested"
WRITES = "sensor.pilot_setpoint_writes"
IN_BAND = "sensor.pilot_time_in_band_today"


def set_thermostat(
    hass: HomeAssistant,
    temperature: float | None = 20.0,
    setpoint: float | None = 19.0,
    state: str = "heat",
    action: str = "idle",
) -> None:
    hass.states.async_set(
        THERMOSTAT,
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
def set_temperature_calls(hass: HomeAssistant):
    return async_mock_service(hass, "climate", "set_temperature")


@pytest.fixture
def set_hvac_mode_calls(hass: HomeAssistant):
    return async_mock_service(hass, "climate", "set_hvac_mode")


async def add_room(hass: HomeAssistant, **overrides) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pilot",
        unique_id=THERMOSTAT,
        data={
            "name": "Pilot",
            CONF_THERMOSTAT: THERMOSTAT,
            CONF_TARGET: 21.0,
            CONF_BUFFER_FALLBACK: 34.0,
            CONF_PHASE_OFFSET: 0,
            **overrides,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def select_mode(hass: HomeAssistant, mode: str) -> None:
    await hass.services.async_call("select", "select_option", {"entity_id": MODE, "option": mode}, blocking=True)
    await hass.async_block_till_done()


async def tick(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_add_a_room_through_the_form(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Pilot", CONF_THERMOSTAT: THERMOSTAT, CONF_TARGET: 21.0, CONF_BUFFER_FALLBACK: 34.0, CONF_PHASE_OFFSET: 0},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Pilot"
    await hass.async_block_till_done()
    assert hass.states.get(MODE).state == "observe"


async def test_a_thermostat_can_belong_to_only_one_room(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    await add_room(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Again", CONF_THERMOSTAT: THERMOSTAT, CONF_TARGET: 21.0, CONF_BUFFER_FALLBACK: 34.0, CONF_PHASE_OFFSET: 0},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_change_and_can_remove_an_entity(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    hass.states.async_set(HEAT_PUMP, "heat", {"temperature": 30.0})
    entry = await add_room(hass, **{CONF_BUFFER_ENTITY: HEAT_PUMP})
    assert float(hass.states.get(BUFFER).state) == 30.0
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_BUFFER_FALLBACK: 36.0, CONF_PHASE_OFFSET: 15},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert float(hass.states.get(BUFFER).state) == 36.0


async def test_new_room_observes_and_writes_nothing(hass: HomeAssistant, set_temperature_calls, set_hvac_mode_calls) -> None:
    set_thermostat(hass, temperature=18.0, setpoint=15.0, state="off", action="off")
    entry = await add_room(hass)
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
    assert set_temperature_calls[0].data == {"entity_id": THERMOSTAT, "temperature": 23.0}
    assert hass.states.get(WRITES).state == "1"


async def test_active_mode_switches_on_a_thermostat_that_is_off(
    hass: HomeAssistant, set_temperature_calls, set_hvac_mode_calls
) -> None:
    set_thermostat(hass, temperature=20.0, setpoint=23.0, state="off", action="off")
    await add_room(hass)
    await select_mode(hass, "active")
    assert len(set_hvac_mode_calls) == 1
    assert set_hvac_mode_calls[0].data == {"entity_id": THERMOSTAT, "hvac_mode": "heat"}


async def test_handback_writes_the_plain_target_once(hass: HomeAssistant, set_temperature_calls) -> None:
    set_thermostat(hass, temperature=20.0, setpoint=23.0, action="heating")
    entry = await add_room(hass)
    await select_mode(hass, "handback")
    assert [call.data["temperature"] for call in set_temperature_calls] == [21.0]
    set_thermostat(hass, temperature=20.0, setpoint=21.0, action="heating")
    for _ in range(5):
        await tick(hass, entry)
    assert len(set_temperature_calls) == 1


async def test_target_change_moves_the_setpoint(hass: HomeAssistant, set_temperature_calls) -> None:
    set_thermostat(hass, temperature=20.0, setpoint=23.0, action="heating")
    await add_room(hass)
    await select_mode(hass, "active")
    await hass.services.async_call("number", "set_value", {"entity_id": TARGET, "value": 22.0}, blocking=True)
    await hass.async_block_till_done()
    assert float(hass.states.get(TARGET).state) == 22.0
    assert set_temperature_calls[-1].data["temperature"] == 24.0


async def test_runs_every_minute_on_its_own(hass: HomeAssistant, set_temperature_calls) -> None:
    set_thermostat(hass, temperature=20.8, setpoint=19.0)
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
    assert [call.data["temperature"] for call in set_temperature_calls] == [23.0]
    assert hass.states.get(STATUS).state == "normal"


async def test_failing_service_call_does_not_stop_the_room(hass: HomeAssistant) -> None:
    set_thermostat(hass, temperature=20.0, setpoint=15.0)
    entry = await add_room(hass)
    # No climate service exists in this test, so the call raises.
    await select_mode(hass, "active")
    await tick(hass, entry)
    assert entry.runtime_data.last_update_success
    assert hass.states.get(MODE).state == "active"


async def test_buffer_is_read_from_the_heat_pump_setpoint(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    hass.states.async_set(HEAT_PUMP, "heat", {"temperature": 30.0, "current_temperature": 55.7})
    entry = await add_room(hass, **{CONF_BUFFER_ENTITY: HEAT_PUMP})
    assert float(hass.states.get(BUFFER).state) == 30.0
    # In auto mode the pump exposes no setpoint, so the last value stays in use.
    hass.states.async_set(HEAT_PUMP, "auto", {"current_temperature": 55.7})
    await tick(hass, entry)
    assert float(hass.states.get(BUFFER).state) == 30.0
    hass.states.async_set(HEAT_PUMP, "unavailable")
    await tick(hass, entry)
    assert float(hass.states.get(BUFFER).state) == 30.0


async def test_buffer_fallback_without_any_reading(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    hass.states.async_set(HEAT_PUMP, "unavailable")
    await add_room(hass, **{CONF_BUFFER_ENTITY: HEAT_PUMP})
    assert float(hass.states.get(BUFFER).state) == 34.0


async def test_buffer_over_the_limit_raises_a_problem(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    hass.states.async_set(HEAT_PUMP, "heat", {"temperature": 40.0})
    entry = await add_room(hass, **{CONF_BUFFER_ENTITY: HEAT_PUMP})
    state = hass.states.get(PROBLEM)
    assert state.state == "on"
    assert state.attributes["reasons"] == ["buffer_over_limit"]
    hass.states.async_set(HEAT_PUMP, "heat", {"temperature": 38.0})
    await tick(hass, entry)
    assert hass.states.get(PROBLEM).state == "off"


async def test_unload_gives_the_target_back_when_active(hass: HomeAssistant, set_temperature_calls) -> None:
    set_thermostat(hass, temperature=20.0, setpoint=15.0)
    entry = await add_room(hass)
    await select_mode(hass, "active")
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert set_temperature_calls[-1].data["temperature"] == 21.0


async def test_unload_writes_nothing_when_observing(hass: HomeAssistant, set_temperature_calls) -> None:
    set_thermostat(hass, temperature=20.0, setpoint=15.0)
    entry = await add_room(hass)
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
    set_thermostat(hass, temperature=21.0, setpoint=23.0, action="heating")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Pilot",
        unique_id=THERMOSTAT,
        data={"name": "Pilot", CONF_THERMOSTAT: THERMOSTAT, CONF_TARGET: 21.0, CONF_BUFFER_FALLBACK: 34.0, CONF_PHASE_OFFSET: 0},
    )
    entry.add_to_hass(hass)
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"{DOMAIN}.{entry.entry_id}",
        "data": {
            "runner": {"mode": "active", "target": 20.5, "integral": 42.0, "carry_s": 60.0, "writes": 7},
            "log": {"rows": [{"date": "2026-11-01", "writes": 3}], "current": None},
            "last_buffer": 33.0,
        },
    }
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(MODE).state == "active"
    assert float(hass.states.get(TARGET).state) == 20.5
    assert entry.runtime_data.runner.snapshot()["integral"] >= 41.0
    assert int(hass.states.get(WRITES).state) >= 7


async def test_diagnostics_contain_the_daily_measurements(hass: HomeAssistant) -> None:
    set_thermostat(hass)
    hass.states.async_set(OUTDOOR, "4.2")
    entry = await add_room(hass, **{CONF_OUTDOOR_ENTITY: OUTDOOR})
    await asyncio.sleep(0.01)
    await tick(hass, entry)
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["config"][CONF_THERMOSTAT] == THERMOSTAT
    assert result["runner"]["mode"] == "observe"
    assert result["today"]["date"] == dt_util.now().date().isoformat()
    assert result["today"]["outdoor_mean"] == 4.2
    assert result["days"] == []


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
    assert hass_storage[key]["data"]["runner"]["mode"] == "observe"


async def test_removing_a_room_deletes_its_stored_state(hass: HomeAssistant, hass_storage) -> None:
    set_thermostat(hass)
    entry = await add_room(hass)
    await select_mode(hass, "observe")
    entry_key = f"{DOMAIN}.{entry.entry_id}"
    await tick(hass, entry)
    await entry.runtime_data._store.async_save(entry.runtime_data.snapshot())
    assert entry_key in hass_storage
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert entry_key not in hass_storage
