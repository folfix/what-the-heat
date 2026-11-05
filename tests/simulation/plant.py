"""Physical models: a three-node room, a thermal actuator and an on/off thermostat."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class RoomParameters:
    """Thermal properties. Capacities in Wh/K, conductances in W/K. All values are assumptions."""

    floor_capacity: float = 650.0
    air_capacity: float = 150.0
    wall_capacity: float = 1000.0
    water_to_floor: float = 150.0
    floor_to_air: float = 160.0
    air_to_wall: float = 200.0
    air_to_outside: float = 15.0
    wall_to_boundary: float = 25.0
    sun_to_floor: float = 0.6

    def scaled(self, factor: float) -> RoomParameters:
        """Return the same room type with a floor area changed by factor."""
        return replace(
            self,
            floor_capacity=self.floor_capacity * factor,
            air_capacity=self.air_capacity * factor,
            wall_capacity=self.wall_capacity * factor,
            water_to_floor=self.water_to_floor * factor,
            floor_to_air=self.floor_to_air * factor,
            air_to_wall=self.air_to_wall * factor,
            air_to_outside=self.air_to_outside * factor,
            wall_to_boundary=self.wall_to_boundary * factor,
        )


class Room:
    """Screed, air and wall mass. The wall loses heat to outdoors or, in a basement, to the ground."""

    def __init__(self, parameters: RoomParameters, air: float = 21.0, floor: float = 25.0, wall: float = 19.0) -> None:
        self.parameters = parameters
        self.air = air
        self.floor = floor
        self.wall = wall

    def step(self, dt_s: float, flow: float, water: float, outside: float, boundary: float, sun_w: float = 0.0) -> None:
        """Advance the room by dt_s seconds."""
        p = self.parameters
        hours = dt_s / 3600.0
        to_floor = p.water_to_floor * flow * (water - self.floor)
        floor_to_air = p.floor_to_air * (self.floor - self.air)
        air_to_wall = p.air_to_wall * (self.air - self.wall)
        floor_delta = (to_floor + p.sun_to_floor * sun_w - floor_to_air) / p.floor_capacity * hours
        air_delta = (
            floor_to_air + (1.0 - p.sun_to_floor) * sun_w - p.air_to_outside * (self.air - outside) - air_to_wall
        ) / p.air_capacity * hours
        wall_delta = (air_to_wall - p.wall_to_boundary * (self.wall - boundary)) / p.wall_capacity * hours
        self.floor += floor_delta
        self.air += air_delta
        self.wall += wall_delta


class Actuator:
    """Thermal valve actuator. Water flows only once it is mostly open."""

    def __init__(self, open_s: float = 210.0, close_s: float = 210.0, flow_from: float = 0.85) -> None:
        self._open_s = open_s
        self._close_s = close_s
        self._flow_from = flow_from
        self.position = 0.0

    def step(self, dt_s: float, powered: bool) -> float:
        """Advance the actuator and return the flow, 0 or 1."""
        if powered:
            self.position = min(1.0, self.position + dt_s / self._open_s)
        else:
            self.position = max(0.0, self.position - dt_s / self._close_s)
        return 1.0 if self.position >= self._flow_from else 0.0


class Thermostat:
    """On/off thermostat with a dead zone below the setpoint, and a reading with limited resolution."""

    def __init__(self, setpoint: float, differential: float = 0.3, resolution: float = 0.1) -> None:
        self.setpoint = setpoint
        self.differential = differential
        self.resolution = resolution
        self.heating = False

    def read(self, air: float) -> float:
        """Return the temperature as the device reports it."""
        return round(air / self.resolution) * self.resolution

    def step(self, air: float) -> bool:
        """Update the relay and return whether it is on."""
        reading = self.read(air)
        if reading <= self.setpoint - self.differential:
            self.heating = True
        elif reading >= self.setpoint:
            self.heating = False
        return self.heating
