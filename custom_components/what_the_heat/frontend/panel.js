// Sidebar overview of all rooms. Plain JavaScript with no build step.
// It uses only what Home Assistant passes to a panel: entity states, the entity and device
// registries, and service calls.

(() => {
  const PLATFORM = "what_the_heat";
  const ELEMENT = "what-the-heat-panel";
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
    buffer_over_limit: "The buffer temperature is above the limit.",
  };
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
    .modes { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; }
    .modes button { min-height: 40px; padding: 4px; font-size: 13px; }
    .modes button.selected {
      background: var(--primary-color, #03a9f4);
      border-color: var(--primary-color, #03a9f4);
      color: var(--text-primary-color, #fff);
    }
    .modes button.confirm { border-color: var(--warning-color, #d9650a); color: var(--warning-color, #d9650a); font-weight: 500; }
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
      this.shadowRoot.addEventListener("click", (event) => this._onClick(event));
    }

    set hass(hass) {
      this._hass = hass;
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

    _update() {
      if (!this._hass) return;
      const rooms = this._rooms();
      const signature = JSON.stringify([
        this._pending,
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
        <header>${menu}<h1>What the Heat</h1></header>
        <main>${rooms.length ? this._summary(rooms) + `<div class="rooms">${rooms.map((room) => this._room(room)).join("")}</div>` : this._empty()}</main>
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
      return `<div class="card summary">${item(rooms.length, "Rooms")}${item(heating, "Heating now")}${item(active, "Controlled")}${item(problems, "Problems", problems > 0)}</div>`;
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
          <div class="modes" role="group" aria-label="Mode of ${name}">${MODES.map(([value, label]) => this._modeButton(room, mode, value, label)).join("")}</div>
          <p class="note">${MODE_NOTES[mode] || ""}</p>
          <div class="foot">
            <span>Buffer ${this._number(room, "assumed_buffer_temperature", 1) ?? "–"} °C · Writes ${this._number(room, "setpoint_writes") ?? "–"} · Resent ${this._number(room, "resends") ?? "–"}</span>
            <a href="/config/devices/device/${encodeURIComponent(room.id)}">Details</a>
          </div>
        </section>
      `;
    }

    _modeButton(room, mode, value, label) {
      const selected = mode === value;
      const confirming = this._pending && this._pending.room === room.id && this._pending.mode === value;
      const classes = [selected ? "selected" : "", confirming ? "confirm" : ""].join(" ");
      return `<button class="${classes}" data-action="mode" data-room="${room.id}" data-mode="${value}" aria-pressed="${selected}">${confirming ? "Confirm?" : label}</button>`;
    }

    _onClick(event) {
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      const room = this._rooms().find((item) => item.id === button.dataset.room);
      if (!room) return;
      if (button.dataset.action === "target") this._changeTarget(room, Number(button.dataset.delta));
      else this._changeMode(room, button.dataset.mode);
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
      const needsConfirm = mode !== "observe";
      const confirmed = this._pending && this._pending.room === room.id && this._pending.mode === mode;
      clearTimeout(this._pendingTimer);
      if (needsConfirm && !confirmed) {
        this._pending = { room: room.id, mode };
        this._pendingTimer = setTimeout(() => {
          this._pending = null;
          this._update();
        }, CONFIRM_MS);
      } else {
        this._pending = null;
        this._hass.callService("select", "select_option", { entity_id: room.entities.mode, option: mode });
      }
      this._update();
    }
  }

  if (!customElements.get(ELEMENT)) customElements.define(ELEMENT, WhatTheHeatPanel);
})();
