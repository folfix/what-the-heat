# Changelog

Each version is also a GitHub release with the same notes, which Home Assistant shows when it offers the update.

## 0.10.0

- The full report shows how learning developed: every daily row keeps what the room had learned at the end of the day, such as the integral, the demand, the sunny days, the solar profile and the outdoor weight.
- New in the Shared settings: **Other entities in the full report**, for window sensors, a second thermometer, a computer's power or anything else that explains what a room does. They are not used for control.
- The report keeps the share of full sun and the difference from the usual outdoor temperature behind the corrections, and lists the columns of each entity's rows.

## 0.9.0

- **Download full report** at the bottom of the What the Heat page saves one file with the last 7 days of all rooms: the recorded history of the thermostats, the outdoor and PV sensors and the rooms' own entities, everything learned, the daily rows and the shared settings.

## 0.8.0

- The solar profile uses solar time, so it no longer shifts when the clocks change, and its correction moves smoothly between hours.
- Each room learns an outdoor correction: more heat when it is colder outside than usual, less when warmer. It learns only while the sun does not shine, starts after a day of readings and stops if the sensor is silent for 2 hours. New sensor: **Outdoor correction**.

## 0.7.1

- The water temperature is set on the What the Heat page again, since it may change over time.
- The shared settings entry is called **⚙ Shared settings**, so that it is listed above the rooms. An existing entry keeps its name until renamed.

## 0.7.0

- The outdoor and PV sensors are set in a **Shared settings** entry with Configure. The first setup asks for them.
- A new room starts in active mode.
- The What the Heat page no longer has mode or Reset learning buttons. Use each room's Mode entity and the Reset learning button on its device page.

## 0.6.0

- Each room learns, hour by hour, how much heat the sun makes unnecessary, using the power of a PV installation as the sun signal. After 3 sunny days the valve opens less while the panels see the sun. New sensor: **Sun correction**.
- The outdoor sensor is shared by all rooms. One set on a room by an older version is ignored.
- Daily rows include the day's PV energy and the mean sun correction.
