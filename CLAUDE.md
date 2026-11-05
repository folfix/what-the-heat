# what-the-heat

A Home Assistant custom integration for water-based underfloor heating. Requirements, architecture and the roadmap are in [docs/specification.md](docs/specification.md). Read it before changing the design, and keep it up to date when decisions change.

## Rules

- **English only in the repository:** code, comments, identifiers, documentation, commit messages, issues. Conversation with the owner may be in Polish. Local Polish notes must not be committed.
- **Work goes straight to `main`.** No feature branches or pull requests unless asked.
- **Public repository:** do not commit personal data or device identifiers such as MAC addresses, Zigbee addresses, tokens or local URLs.

## Commands

- Core and simulation tests: `python -m unittest discover -s tests -t .`
- Pilot room comparison: `python -m tests.simulation.pilot`
- Sidebar page with made-up rooms: run `python -m http.server 8765` in the repository root and open `/tests_ha/panel_preview.html`.
- Integration tests on a real Home Assistant core: `python -m pytest` in an environment with `requirements_test.txt`. On Windows that environment also needs stand-ins for the Unix modules `fcntl` and `resource`.

## Design constraints

- There are no floor sensors and there will be none. Floor temperature must never be a required input.
- The temperature set on the heat pump is treated as the real buffer temperature, and it must not exceed 38 °C.
- `custom_components/what_the_heat/__init__.py` must stay free of top-level Home Assistant imports, since importing the core runs it.
- The control core has no Home Assistant imports and no third-party dependencies, so that it runs in the simulator and in unit tests. Decisions belong in the core, and the Home Assistant layer stays thin.
- A new room starts in observe mode, and observe mode never writes to a device.
- Thermostats are controlled through setpoints only. Do not rely on `hvac_mode: off`.
- Nothing critical may depend on SmartThings or AccuWeather, since both are cloud services.
- Simulation results compare options. Do not present them as predictions for the real house.
