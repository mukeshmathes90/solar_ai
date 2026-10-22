# Hardware bring-up checklist

Do things **in order**. Do not jump to "power everything on" — each stage
proves one thing, so a mistake is caught cheaply.

Legend: `[ ]` to do · mark `[x]` when verified.

---

## Stage 0 — Before touching the board

- [ ] Board identified as **NodeMCU 1.0 (ESP-12E)**, not an ESP-01 or ESP32.
- [ ] USB cable is a **data** cable (some cables are charge-only).
- [ ] Arduino IDE / arduino-cli has the **esp8266 core** installed.
- [ ] You can compile `firmware/microgrid_node` for `esp8266:esp8266:nodemcuv2`
      without errors.
- [ ] `credentials.example.h` copied to `credentials.h` and filled in.

## Stage 1 — Power only, nothing attached

- [ ] Connect the NodeMCU to USB with **no** sensors wired.
- [ ] Flashing succeeds.
- [ ] Serial monitor at **115200** shows the banner and `[wifi] connecting...`.
- [ ] The node joins the hotspot and prints `IP = 192.168.43.x`.
- [ ] `[ntp] synced` appears (or a clear "not synced" notice).
- [ ] Board is reachable: from the laptop, `ping 192.168.43.x`.

## Stage 2 — I²C bus

- [ ] Power **off**. Wire both INA219 modules to 3V3 / GND / SDA (D2) / SCL (D1).
- [ ] Confirm the **wind** module's A0 jumper is bridged (address `0x41`).
- [ ] Power on and read the serial log: `[i2c] device at 0x40` and `0x41`.
- [ ] If a module is missing, the log says `NOT found` — fix wiring/jumpers
      before continuing.

## Stage 3 — Voltage measurement (no load yet)

- [ ] With the solar panel connected to the solar INA219 `VIN+`/`VIN-` (open
      circuit is fine), the serial log shows a plausible `solar=…V`.
- [ ] `solar_current` reads `null` (expected with no load) — **not** a made-up 0.
- [ ] Repeat for the wind channel.

## Stage 4 — Current measurement (with a load)

- [ ] Power off. Insert a small load (10–100 Ω power resistor, or LED + series
      resistor) between `VIN-` and the generator's negative rail.
- [ ] Confirm the load's power rating is well within the generator's capability
      so nothing overheats.
- [ ] Power on: current now reads a small, believable value and power is
      non-null.
- [ ] If current is still `null`, the path is not closed — recheck the shunt
      wiring.

## Stage 5 — DHT11

- [ ] Wire DHT11 with the 10 kΩ pull-up.
- [ ] Log shows believable `T=` and `RH=` values.
- [ ] If `DHT_FAIL`, check VCC/GND and the pull-up; try a 4.7 kΩ if unstable.

## Stage 6 — Hall sensor

- [ ] Wire the KY-024 to D6.
- [ ] Spin/turn the turbine by hand; the logged `rpm` changes.
- [ ] Set `PULSES_PER_REV` so a known hand-turn gives a believable RPM.

## Stage 7 — LDR

- [ ] Wire the LDR module to D7.
- [ ] Cover / uncover the sensor: `light_status` toggles `bright` / `dark`.
- [ ] Flip `LIGHT_ACTIVE_LOW` if the sense is inverted.

## Stage 8 — End-to-end telemetry

- [ ] Flask backend running on the laptop (`run.bat` or `python -m backend.app`).
- [ ] Node prints `[http] 201 OK` every sample cycle.
- [ ] Dashboard **Live Monitoring** shows fresh values with source `hardware`.
- [ ] A rejected reading prints `[http] 422 REJECTED: {…}` with the reason —
      read it; it names the offending field.

## Stage 9 — Safety sign-off

- [ ] Relay observed to be **OFF** at every boot.
- [ ] Relay never switches on by itself, even when generation looks high.
- [ ] Automatic relay control left **disabled** on the dashboard.
- [ ] No exposed mains wiring anywhere on the bench.
- [ ] Only 3.3 V logic levels reach ESP8266 GPIO pins.

---

## What cannot be verified without hardware

The firmware was compiled and statically reviewed, but the following can only
be confirmed on a real bench and must not be claimed as tested until then:

- actual Wi-Fi association and POST latency,
- INA219 accuracy and shunt orientation,
- DHT11 timing stability,
- Hall pulse counts at real turbine speed,
- relay behaviour into a real load.
