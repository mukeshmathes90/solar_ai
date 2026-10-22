# Wiring guide

> This is a **low-voltage bench prototype**. Everything on the sensor side runs
> at 3.3 V (ESP8266 logic) and the generators are small DC devices. Do **not**
> connect mains, a mains charger, or a full-size solar array to this board.
> Never feed a generator's raw output into the ESP8266 3V3 pin.

Board: **NodeMCU 1.0 (ESP-12E)**, target `esp8266:esp8266:nodemcuv2`, serial
**115200 baud**.

---

## 1. Pin map

| Signal | ESP8266 pin | GPIO | Notes |
|---|---|---|---|
| I²C **SDA** | D2 | GPIO4 | shared by both INA219 (+ optional LCD) |
| I²C **SCL** | D1 | GPIO5 | shared by both INA219 (+ optional LCD) |
| **DHT11** data | D5 | GPIO14 | needs a 10 kΩ pull-up to 3V3 |
| **Hall** digital out (KY-024) | D6 | GPIO12 | interrupt pin, pulse counting |
| **LDR** digital out | D7 | GPIO13 | bright / dark detection |
| **Relay** IN | D0 | GPIO16 | active-low module; held **OFF** |
| ESP8266 on-board LED | D4 | GPIO2 | heartbeat blink (not wired) |

The two I²C lines are the ESP8266's default I²C pins, so `Wire.begin()` and the
INA219 library both work without re-pinning.

---

## 2. I²C bus — both INA219 modules

Both INA219 modules sit on the **same** SDA/SCL bus and must have **different
addresses**:

| Module | Address | Jumper |
|---|---|---|
| Solar INA219 | `0x40` | factory default (A0 = A1 = GND) |
| Wind INA219 | `0x41` | **bridge A0 to VCC** |

If both modules ship at `0x40` and you cannot change one, either re-solder the
A0 jumper on one board, use a TCA9548A I²C multiplexer, or run a **single**
INA219 and accept that only one channel is measured. The firmware reports a
missing module by name in `sensor_status` (`SOLAR_INA_FAIL` / `WIND_INA_FAIL`).

Connections per module:

```
INA219 VCC  -> NodeMCU 3V3
INA219 GND  -> NodeMCU GND
INA219 SDA  -> D2 (shared)
INA219 SCL  -> D1 (shared)
```

### Measuring current (important)

The INA219 measures current through its **shunt** (`VIN+` → `VIN-`). To read a
generator's current you must route the generator's output **through** the shunt
into a real load:

```
Solar panel +  ->  INA219 VIN+
                   INA219 VIN-  ->  small load (e.g. 10–100 Ω power resistor / LED + resistor)
Panel −        ->  load −  ->  NodeMCU GND (common ground)
```

If nothing draws current (open circuit), the module can still measure
**voltage**, but current is physically unmeasurable. When that is the case this
firmware sends `solar_current` / `wind_current` as `null` and the power as
`null` — it does **not** guess. The dashboard shows "not measured".

---

## 3. DHT11 (temperature / humidity)

```
DHT11 VCC  -> 3V3
DHT11 GND  -> GND
DHT11 DATA -> D5 (GPIO14)  + 10 kΩ resistor from DATA to 3V3
```

The DHT11 needs at least **2 s** between conversions; the default sample
interval is 5 s.

---

## 4. Hall-effect module (turbine RPM)

```
KY-024 VCC -> 3V3
KY-024 GND -> GND
KY-024 DO  -> D6 (GPIO12)
```

Attach one (or more) small magnets to the turbine shaft so the sensor emits one
pulse per pass. Set `PULSES_PER_REV` in `credentials.h` to match your rotor.
RPM is computed as `pulses × 60000 / (PULSES_PER_REV × interval_ms)`.

---

## 5. LDR module (light status)

```
LDR module VCC -> 3V3
LDR module GND -> GND
LDR module DO  -> D7 (GPIO13)
```

Most comparator modules pull **DO low when bright**. If yours is inverted, set
`LIGHT_ACTIVE_LOW 0` in `credentials.h`.

---

## 6. Relay (optional, default OFF)

```
Relay module VCC -> 5V (VU) or 3V3 depending on the module
Relay module GND -> GND
Relay module IN  -> D0 (GPIO16)
```

* GPIO16 is chosen because it is a **safe** pin at boot (no boot-strapping).
* The firmware drives the relay to its **OFF** state in `setup()` and never
  switches it automatically. Automatic load switching is a dashboard feature
  that must stay disabled until a correctly rated relay/SSR and a low-voltage
  bench test have been verified.
* Never switch mains with this prototype.

---

## 7. Optional I²C LCD (future use)

An HD44780 + PCF8574 LCD (`0x27`) can share the same SDA/SCL bus and display
the latest readings. It is not used by the current firmware build; if you add
it, keep it on 3V3 logic and ensure the total bus pull-up is adequate.

---

## 8. Common ground

All modules and both generators' negative terminals must share the ESP8266
GND. A missing common ground is the single most common cause of flickering or
zero readings.

---

## 9. Before you apply power

Work through `docs/HARDWARE_CHECKLIST.md`. It lists the continuity, polarity and
voltage-level checks to perform **with the ESP8266 powered off**.
