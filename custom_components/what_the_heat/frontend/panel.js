// Sidebar overview of all rooms. Plain JavaScript with no build step.
// It uses only what Home Assistant passes to a panel: entity states, the entity and device
// registries, and service calls.

(() => {
  const PLATFORM = "what_the_heat";
  const ELEMENT = "what-the-heat-panel";
  const VERSION = document.currentScript ? new URL(document.currentScript.src).searchParams.get("v") : null;
  const CONFIRM_MS = 5000;
  const MODES = [
    ["observe", "Observe"],
    ["active", "Active"],
    ["handback", "Hand back"],
  ];
  const MODE_NOTES = {
    observe: "Calculating only. Nothing is written to the thermostat.",
    active: "This controller is in charge of the thermostat.",
    handback: "The thermostat is regulating on its own.",
  };
  const REASONS = {
    thermostat_not_following: "The thermostat is not following commands.",
    thermostat_cannot_heat: "The thermostat cannot heat. Check its summer mode.",
    readings_missing: "Room temperature readings are missing.",
  };
  const WATER_MIN = 20;
  const WATER_MAX = 38;
  const UNUSABLE = new Set(["unavailable", "unknown", undefined]);

  const STYLE = `
    :host {
      display: block;
      min-height: 100%;
      background: var(--primary-background-color, #f5f5f5);
      color: var(--primary-text-color, #1c1c1c);
      font-family: var(--paper-font-body1_-_font-family, Roboto, system-ui, sans-serif);
      -webkit-font-smoothing: antialiased;
    }
    * { box-sizing: border-box; }
    header {
      display: flex;
      align-items: center;
      gap: 8px;
      min-height: 56px;
      padding: 0 16px;
      background: var(--app-header-background-color, var(--primary-color, #03a9f4));
      color: var(--app-header-text-color, #fff);
    }
    h1 { margin: 0; font-size: 20px; font-weight: 400; }
    .version { margin-left: auto; font-size: 12px; opacity: 0.7; }
    main { max-width: 1280px; margin: 0 auto; padding: 16px; }
    .card {
      background: var(--card-background-color, #fff);
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: var(--ha-card-border-radius, 12px);
    }
    .summary { display: flex; flex-wrap: wrap; gap: 8px 32px; padding: 12px 16px; margin-bottom: 16px; }
    .summary b { display: block; font-size: 22px; font-weight: 500; font-variant-numeric: tabular-nums; }
    .summary span { font-size: 12px; color: var(--secondary-text-color, #666); }
    .summary .alert b { color: var(--error-color, #db4437); }
    .summary .water { display: flex; align-items: center; gap: 4px; margin-left: auto; }
    .summary .water .water-value { min-width: 96px; text-align: center; }
    .summary .water b { font-size: 18px; }
    @media (max-width: 520px) { .summary .water { margin-left: 0; width: 100%; justify-content: space-between; } }
    .sensors { display: grid; gap: 12px 24px; grid-template-columns: repeat(auto-fit, minmax(min(260px, 100%), 1fr)); padding: 12px 16px; margin-bottom: 16px; }
    .sensors label { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
    .sensors span, .sensors small { font-size: 12px; color: var(--secondary-text-color, #666); }
    select {
      width: 100%;
      min-height: 40px;
      padding: 4px 8px;
      font: inherit;
      color: inherit;
      background: var(--card-background-color, #fff);
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 8px;
    }
    select:focus-visible { outline: 2px solid var(--primary-color, #03a9f4); outline-offset: 1px; }
    .rooms { display: grid; gap: 16px; grid-template-columns: repeat(auto-fill, minmax(min(320px, 100%), 1fr)); }
    .room { display: flex; flex-direction: column; gap: 12px; padding: 16px; min-width: 0; }
    .room.problem { border-color: var(--error-color, #db4437); }
    .top { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
    h2 { margin: 0; font-size: 16px; font-weight: 500; overflow-wrap: anywhere; }
    .area { font-size: 12px; color: var(--secondary-text-color, #666); }
    .chip {
      flex: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 2px 10px;
      border-radius: 999px;
      font-size: 12px;
      white-space: nowrap;
      background: var(--secondary-background-color, #eee);
      color: var(--secondary-text-color, #666);
    }
    .chip::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
    .chip.heating { color: var(--state-climate-heat-color, #d9650a); }
    .temps { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
    .current { font-size: 40px; font-weight: 300; line-height: 1; font-variant-numeric: tabular-nums; }
    .current small { font-size: 16px; color: var(--secondary-text-color, #666); }
    .target { display: flex; align-items: center; gap: 4px; }
    .target-value { min-width: 64px; text-align: center; font-variant-numeric: tabular-nums; }
    .target-value span { display: block; font-size: 11px; color: var(--secondary-text-color, #666); }
    button {
      font: inherit;
      color: inherit;
      cursor: pointer;
      background: none;
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 8px;
    }
    button:hover { background: var(--secondary-background-color, #eee); }
    button:focus-visible { outline: 2px solid var(--primary-color, #03a9f4); outline-offset: 1px; }
    .step { width: 40px; height: 40px; font-size: 20px; line-height: 1; }
    .duty-label { display: flex; justify-content: space-between; gap: 8px; font-size: 13px; margin-bottom: 4px; }
    .duty-label span:last-child { color: var(--secondary-text-color, #666); text-align: right; }
    .bar { height: 8px; border-radius: 4px; overflow: hidden; background: var(--secondary-background-color, #eee); }
    .bar div { height: 100%; background: var(--state-climate-heat-color, #d9650a); }
    .bar.quiet div { background: var(--secondary-text-color, #888); }
    .today { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
    .today b { display: block; font-size: 15px; font-weight: 500; font-variant-numeric: tabular-nums; }
    .today span { display: block; font-size: 11px; color: var(--secondary-text-color, #666); }
    .learned { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    .learned b { display: block; font-size: 15px; font-weight: 500; font-variant-numeric: tabular-nums; }
    .learned span { display: block; font-size: 11px; color: var(--secondary-text-color, #666); }
    .learned button { flex: none; min-height: 40px; padding: 4px 12px; font-size: 13px; }
    .modes { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; }
    .modes button { min-height: 40px; padding: 4px; font-size: 13px; }
    .modes button.selected {
      background: var(--primary-color, #03a9f4);
      border-color: var(--primary-color, #03a9f4);
      color: var(--text-primary-color, #fff);
    }
    button.confirm { border-color: var(--warning-color, #d9650a); color: var(--warning-color, #d9650a); font-weight: 500; }
    .note { margin: 0; font-size: 12px; color: var(--secondary-text-color, #666); }
    .problems { margin: 0; padding: 8px 12px; font-size: 13px; border-radius: 8px; color: var(--error-color, #db4437); border: 1px solid currentColor; }
    .foot { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 12px; font-size: 12px; color: var(--secondary-text-color, #666); }
    a { color: var(--primary-color, #03a9f4); }
    .empty { padding: 32px 16px; text-align: center; color: var(--secondary-text-color, #666); }
    @media (max-width: 360px) { .current { font-size: 32px; } }
  `;

  const escapeHtml = (value) =>
    String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  class WhatTheHeatPanel extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._signature = null;
      this._pending = null;
      this._settings = null;
      this._settingsAsked = false;
      this.shadowRoot.addEventListener("click", (event) => this._onClick(event));
      this.shadowRoot.addEventListener("change", (event) => this._onChange(event));
    }

    set hass(hass) {
      this._hass = hass;
      if (!this._settingsAsked) this._loadSettings();
      this._update();
    }

    get hass() {
      return this._hass;
    }

    set narrow(narrow) {
      this._narrow = narrow;
      this._signature = null;
      this._update();
    }

    set panel(_panel) {}

    set route(_route) {}

    _rooms() {
      const rooms = new Map();
      for (const entity of Object.values(this._hass.entities || {})) {
        if (entity.platform !== PLATFORM || !entity.device_id || !entity.translation_key) continue;
        if (!rooms.has(entity.device_id)) rooms.set(entity.device_id, {});
        rooms.get(entity.device_id)[entity.translation_key] = entity.entity_id;
      }
      return [...rooms.entries()]
        .map(([id, entities]) => {
          const device = (this._hass.devices || {})[id] || {};
          const area = (this._hass.areas || {})[device.area_id];
          return { id, entities, name: device.name_by_user || device.name || id, area: area ? area.name : "" };
        })
        .sort((a, b) => a.name.localeCompare(b.name));
    }

    _state(room, key) {
      const entityId = room.entities[key];
      return entityId ? this._hass.states[entityId] : undefined;
    }

    _number(room, key, digits = 0) {
      const state = this._state(room, key);
      if (!state || UNUSABLE.has(state.state)) return null;
      const value = Number(state.state);
      if (!Number.isFinite(value)) return null;
      return this._format(value, digits);
    }

    _format(value, digits) {
      const language = this._hass.locale ? this._hass.locale.language : undefined;
      return value.toLocaleString(language, { minimumFractionDigits: digits, maximumFractionDigits: digits });
    }

    // The settings shared by all rooms come from the integration itself, not from an entity.
    _loadSettings() {
      this._settingsAsked = true;
      if (!this._hass.callWS) return;
      this._hass.callWS({ type: `${PLATFORM}/settings` }).then(
        (settings) => {
          this._settings = settings;
          this._update();
        },
        () => {
          this._settingsAsked = false;
        },
      );
    }

    _sensorOptions(deviceClass) {
      return Object.entries(this._hass.states)
        .filter(([entityId, state]) => entityId.startsWith("sensor.") && (state.attributes || {}).device_class === deviceClass)
        .map(([entityId, state]) => [entityId, state.attributes.friendly_name || entityId])
        .sort((a, b) => a[1].localeCompare(b[1]));
    }

    _update() {
      if (!this._hass) return;
      const rooms = this._rooms();
      const signature = JSON.stringify([
        this._pending,
        this._settings,
        this._settings ? [this._sensorOptions("temperature"), this._sensorOptions("power")] : null,
        rooms.map((room) => [room.name, room.area, Object.values(room.entities).map((id) => (this._hass.states[id] || {}).last_updated)]),
      ]);
      if (signature === this._signature) return;
      this._signature = signature;
      this._render(rooms);
    }

    _render(rooms) {
      const menu = customElements.get("ha-menu-button") ? "<ha-menu-button></ha-menu-button>" : "";
      this.shadowRoot.innerHTML = `
        <style>${STYLE}</style>
        <header>${menu}<h1>What the Heat</h1>${VERSION ? `<span class="version">${escapeHtml(VERSION)}</span>` : ""}</header>
        <main>${rooms.length ? this._summary(rooms) + this._sensors() + `<div class="rooms">${rooms.map((room) => this._room(room)).join("")}</div>` : this._empty()}</main>
      `;
      const button = this.shadowRoot.querySelector("ha-menu-button");
      if (button) {
        button.hass = this._hass;
        button.narrow = this._narrow;
      }
    }

    _empty() {
      return `<div class="card empty">No rooms yet. Add one under Settings → Devices &amp; services → Add integration → What the Heat.</div>`;
    }

    _summary(rooms) {
      const count = (test) => rooms.filter(test).length;
      const heating = count((room) => (this._state(room, "zone") || { attributes: {} }).attributes.hvac_action === "heating");
      const active = count((room) => (this._state(room, "mode") || {}).state === "active");
      const problems = count((room) => (this._state(room, "problem") || {}).state === "on");
      const item = (value, label, alert) => `<div class="${alert ? "alert" : ""}"><b>${value}</b><span>${label}</span></div>`;
      const water = this._number(rooms[0], "water_temperature", 1);
      const control = `
        <div class="water" role="group" aria-label="Water temperature for all rooms">
          <button class="step" data-action="water" data-delta="-0.5" aria-label="Lower the water temperature">−</button>
          <div class="water-value"><b>${water ?? "–"} °C</b><span>Water, all rooms</span></div>
          <button class="step" data-action="water" data-delta="0.5" aria-label="Raise the water temperature">+</button>
        </div>`;
      return `<div class="card summary">${item(rooms.length, "Rooms")}${item(heating, "Heating now")}${item(active, "Controlled")}${item(problems, "Problems", problems > 0)}${control}</div>`;
    }

    _sensors() {
      if (!this._settings) return "";
      const choice = (key, label, deviceClass, note) => {
        const current = this._settings[key] || "";
        const options = this._sensorOptions(deviceClass);
        if (current && !options.some(([id]) => id === current)) options.unshift([current, current]);
        const items = options.map(([id, name]) => `<option value="${escapeHtml(id)}" ${id === current ? "selected" : ""}>${escapeHtml(name)}</option>`);
        return `
          <label>
            <span>${label}, all rooms</span>
            <select data-setting="${key}"><option value="" ${current ? "" : "selected"}>None</option>${items.join("")}</select>
            <small>${note}</small>
          </label>`;
      };
      return `<div class="card sensors">${choice("outdoor_entity", "Outdoor temperature", "temperature", "Only logged for now, for learning later.")}${choice("pv_entity", "PV power", "power", "Tells each room how much sun there is, so that it can learn what the sun does to it.")}</div>`;
    }

    _room(room) {
      const climate = this._state(room, "zone");
      const attributes = climate ? climate.attributes : {};
      const mode = (this._state(room, "mode") || {}).state || "observe";
      const problem = this._state(room, "problem");
      const reasons = problem && problem.state === "on" ? problem.attributes.reasons || [] : [];
      const temperature = attributes.current_temperature;
      const action = attributes.hvac_action;
      const chip = action === "heating" ? ["heating", "Heating"] : action === "idle" ? ["", "Idle"] : action === "off" ? ["", "Thermostat off"] : ["", "No reading"];
      const target = attributes.temperature;
      const duty = this._number(room, "duty");
      const dutyValue = duty === null ? 0 : Number((this._state(room, "duty") || {}).state);
      const wants = (this._state(room, "valve_requested") || {}).state === "on";
      const dutyLabel = mode === "active" ? "Valve open" : mode === "observe" ? "Would keep the valve open" : "Calculated valve opening";
      const valveNow = mode === "handback" ? "Not in use" : mode === "active" ? (wants ? "Open now" : "Closed now") : wants ? "Would be open now" : "Would be closed now";
      const today = (key, label, digits, unit) => {
        const value = this._number(room, key, digits);
        return `<div><b>${value === null ? "–" : value + unit}</b><span>${label}</span></div>`;
      };
      const name = escapeHtml(room.name);
      return `
        <section class="card room ${reasons.length ? "problem" : ""}" aria-label="${name}">
          <div class="top">
            <div><h2>${name}</h2>${room.area ? `<div class="area">${escapeHtml(room.area)}</div>` : ""}</div>
            <span class="chip ${chip[0]}">${chip[1]}</span>
          </div>
          <div class="temps">
            <div class="current">${temperature == null ? "–" : this._format(temperature, 1)}<small> °C</small></div>
            <div class="target">
              <button class="step" data-action="target" data-room="${room.id}" data-delta="-0.5" aria-label="Lower the target of ${name}">−</button>
              <div class="target-value"><b>${target == null ? "–" : this._format(target, 1)} °C</b><span>Target</span></div>
              <button class="step" data-action="target" data-room="${room.id}" data-delta="0.5" aria-label="Raise the target of ${name}">+</button>
            </div>
          </div>
          ${reasons.length ? `<p class="problems" role="alert">${reasons.map((reason) => escapeHtml(REASONS[reason] || reason)).join("<br>")}</p>` : ""}
          <div>
            <div class="duty-label"><span>${dutyLabel}: ${duty === null ? "–" : duty + "%"}</span><span>${valveNow}</span></div>
            <div class="bar ${mode === "active" ? "" : "quiet"}" role="img" aria-label="${dutyLabel}: ${dutyValue.toFixed(0)}%"><div style="width:${Math.min(100, Math.max(0, dutyValue))}%"></div></div>
          </div>
          <div class="today">
            ${today("time_in_band_today", "In band today", 0, "%")}
            ${today("rms_deviation_today", "Deviation", 2, "°")}
            ${today("heating_today", "Heating", 0, "%")}
            ${today("longest_closed_today", "Longest off", 1, " h")}
          </div>
          ${this._learned(room, name)}
          ${this._sun(room)}
          <div class="modes" role="group" aria-label="Mode of ${name}">${MODES.map(([value, label]) => this._modeButton(room, mode, value, label)).join("")}</div>
          <p class="note">${MODE_NOTES[mode] || ""}</p>
          <div class="foot">
            <span>Writes ${this._number(room, "setpoint_writes") ?? "–"} · Resent ${this._number(room, "resends") ?? "–"}</span>
            <a href="/config/devices/device/${encodeURIComponent(room.id)}">Details</a>
          </div>
        </section>
      `;
    }

    _learned(room, name) {
      const state = this._state(room, "learned_demand");
      if (!state) return "";
      const demand = this._number(room, "learned_demand");
      const { source, learned_from_hours: hours = 0 } = state.attributes;
      const seen = source === "thermostat" ? "Valve opening seen on the thermostat" : "Valve opening this room needs";
      const label = demand === null ? "Nothing learned yet. It takes a few hours near the target." : `${seen}, from ${this._duration(hours)} of data`;
      const confirming = this._isPending(room, "reset");
      const reset = room.entities.reset_learning
        ? `<button class="${confirming ? "confirm" : ""}" data-action="reset" data-room="${room.id}" aria-label="Reset what ${name} has learned">${confirming ? "Confirm?" : "Reset learning"}</button>`
        : "";
      return `<div class="learned"><div><b>${demand === null ? "–" : demand + "%"}</b><span>${label}</span></div>${reset}</div>`;
    }

    // Shown only while a PV sensor is set.
    _sun(room) {
      const state = this._state(room, "sun_correction");
      if (!state || UNUSABLE.has(state.state)) return "";
      const { sunny_days: days = 0, active = false } = state.attributes;
      const correction = this._number(room, "sun_correction");
      const sunnyDays = `${days} sunny ${days === 1 ? "day" : "days"}`;
      const label = active ? `Valve opening the sun takes off now, learned from ${sunnyDays}` : `Learning what the sun does here, from ${sunnyDays} so far`;
      return `<div class="learned"><div><b>${active && correction !== null ? correction + "%" : "–"}</b><span>${label}</span></div></div>`;
    }

    _duration(hours) {
      return hours >= 48 ? `${this._format(hours / 24, 0)} days` : `${this._format(hours, 0)} h`;
    }

    _modeButton(room, mode, value, label) {
      const selected = mode === value;
      const confirming = this._isPending(room, value);
      const classes = [selected ? "selected" : "", confirming ? "confirm" : ""].join(" ");
      return `<button class="${classes}" data-action="mode" data-room="${room.id}" data-mode="${value}" aria-pressed="${selected}">${confirming ? "Confirm?" : label}</button>`;
    }

    _onClick(event) {
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      if (button.dataset.action === "water") {
        this._changeWater(Number(button.dataset.delta));
        return;
      }
      const room = this._rooms().find((item) => item.id === button.dataset.room);
      if (!room) return;
      if (button.dataset.action === "target") this._changeTarget(room, Number(button.dataset.delta));
      else if (button.dataset.action === "reset") this._resetLearning(room);
      else this._changeMode(room, button.dataset.mode);
    }

    _onChange(event) {
      const select = event.target.closest("select[data-setting]");
      if (!select) return;
      const key = select.dataset.setting;
      this._settings = { ...this._settings, [key]: select.value || null };
      Promise.resolve(this._hass.callService(PLATFORM, "set_sensors", { [key]: select.value })).finally(() => this._loadSettings());
    }

    _changeWater(delta) {
      const rooms = this._rooms();
      const state = rooms.length ? this._state(rooms[0], "water_temperature") : undefined;
      if (!state || UNUSABLE.has(state.state)) return;
      const next = Math.min(WATER_MAX, Math.max(WATER_MIN, Number(state.state) + delta));
      this._hass.callService(PLATFORM, "set_water_temperature", { temperature: next });
    }

    _changeTarget(room, delta) {
      const climate = this._state(room, "zone");
      if (!climate || climate.attributes.temperature == null) return;
      const { temperature, min_temp: low = 5, max_temp: high = 30 } = climate.attributes;
      const next = Math.min(high, Math.max(low, temperature + delta));
      this._hass.callService("climate", "set_temperature", { entity_id: room.entities.zone, temperature: next });
    }

    _changeMode(room, mode) {
      const current = (this._state(room, "mode") || {}).state;
      if (current === mode) return;
      // Starting or handing over control writes to the thermostat, so a stray tap must not do it.
      if (this._confirmed(room, mode, mode === "observe")) {
        this._hass.callService("select", "select_option", { entity_id: room.entities.mode, option: mode });
      }
      this._update();
    }

    _resetLearning(room) {
      // What was learned cannot be brought back, so a stray tap must not do it.
      if (this._confirmed(room, "reset")) {
        this._hass.callService("button", "press", { entity_id: room.entities.reset_learning });
      }
      this._update();
    }

    _isPending(room, action) {
      return Boolean(this._pending && this._pending.room === room.id && this._pending.action === action);
    }

    // Returns whether to go ahead. Otherwise the action now waits for a second tap.
    _confirmed(room, action, immediately = false) {
      const confirmed = immediately || this._isPending(room, action);
      clearTimeout(this._pendingTimer);
      this._pending = confirmed ? null : { room: room.id, action };
      if (!confirmed) {
        this._pendingTimer = setTimeout(() => {
          this._pending = null;
          this._update();
        }, CONFIRM_MS);
      }
      return confirmed;
    }
  }

  // A page left open across an update loads this file again, and an element cannot be
  // defined twice, so the new code replaces the methods of the class already registered.
  const registered = customElements.get(ELEMENT);
  if (registered) {
    const { constructor, ...members } = Object.getOwnPropertyDescriptors(WhatTheHeatPanel.prototype);
    Object.defineProperties(registered.prototype, members);
  } else {
    customElements.define(ELEMENT, WhatTheHeatPanel);
  }
})();
