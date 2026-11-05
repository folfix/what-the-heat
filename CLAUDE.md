# what-the-heat

A Home Assistant custom integration for water-based underfloor heating. Requirements, architecture and the roadmap are in [docs/specification.md](docs/specification.md). Read it before changing the design, and keep it up to date when decisions change.

## Rules

- **English only in the repository:** code, comments, identifiers, documentation, commit messages, issues. Conversation with the owner may be in Polish. Local Polish notes must not be committed.
- **Work goes straight to `main`.** No feature branches or pull requests unless asked.
- **Public repository:** do not commit personal data or device identifiers such as MAC addresses, Zigbee addresses, tokens or local URLs.

## Design constraints

- There are no floor sensors and there will be none. Floor temperature must never be a required input.
- The control core has no Home Assistant imports and no third-party dependencies, so that it runs in the simulator and in unit tests.
- Thermostats are controlled through setpoints only. Do not rely on `hvac_mode: off`.
- Nothing critical may depend on SmartThings or AccuWeather, since both are cloud services.
- Simulation results compare options. Do not present them as predictions for the real house.
