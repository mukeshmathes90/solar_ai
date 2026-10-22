# Troubleshooting

Symptoms are grouped by where the problem usually lives. Read the **serial
log first** — the firmware prints a named reason for almost every failure.

---

## Flashing / boot

**`Failed to connect to ESP8266: Timed out waiting for packet header`**
- Wrong port selected, charge-only USB cable, or missing USB-serial driver.
- Hold **FLASH/BOOT** while starting the upload on some clone boards.
- Lower the upload speed to 115200.

**Board boots but serial is garbage characters**
- Baud rate is not **115200**.

**`IRAM` usage warning / sketch too big**
- The default build already runs near the IRAM limit because of Wi-Fi +
  interrupts. Close other large libraries and rebuild; do not add heavy ISR code.

---

## Wi-Fi

**`[wifi] connecting...` forever**
- The ESP8266 supports **2.4 GHz only**. A 5 GHz hotspot will never work.
- SSID/password in `credentials.h` are case-sensitive.
- Some phone hotspots hide the SSID or use a captive-portal — disable that.

**Connects, then drops repeatedly**
- Weak signal or too many clients on the hotspot. Move closer; disable
  "smart" battery/energy saving on the hotspot settings.
- Keep the laptop and the node on the **same** hotspot.

**No `[ntp] synced` line**
- The hotspot may have no internet, so NTP cannot resolve. This is fine: the
  nodes still work because the **server stamps the timestamp** when the field
  is absent. Readings remain correctly ordered.

---

## I²C / INA219

**`[i2c] no devices found`**
- SDA/SCL swapped, or no common ground, or missing pull-ups.
- Some INA219 modules want VCC = 3V3; confirm the module's logic level.

**Only one INA219 appears (e.g. only `0x40`)**
- Both modules are still at `0x40`. Bridge **A0** on the wind module to make it
  `0x41`, or use a TCA9548A multiplexer.

**`SOLAR_INA_FAIL` / `WIND_INA_FAIL` in `sensor_status`**
- That module did not answer at boot. The firmware retries every 30 s; reseat
  the jumper/wiring and it should recover without a reflash.

**Voltage reads, current is always `null`**
- **Expected** with no connected load: an INA219 cannot measure generated
  current through an open circuit. Add a small load (see `WIRING.md` §2).
- If you *do* have a load and current is still `null`, the path is not closed
  through the shunt — recheck `VIN+` → `VIN-` → load → GND.

**Current reads negative**
- `VIN+`/`VIN-` are reversed. Either swap them or accept the sign, but swap is
  cleaner.

---

## DHT11

**`[dht] read failed` / `DHT_FAIL`**
- Missing or wrong pull-up resistor (10 kΩ data→3V3).
- Reading faster than every 2 s — the DHT11 will fail. Keep
  `SAMPLE_INTERVAL_MS ≥ 2000`.
- Long cables (>50 cm) destabilise the DHT11; shorten or twist the wires.

---

## Hall sensor / RPM

**`rpm` always 0**
- Magnet not passing close enough to the sensor head (usually < 5 mm).
- Wrong output type: this firmware expects a **digital** pulse output on D6.
- `PULSES_PER_REV` wrong, so a real spin gives an absurd number.

**`rpm` jitters wildly**
- Electrical noise. The ISR already debounces 400 µs; reduce cable length and
  keep the sensor wires away from the generator.

---

## LDR / light status

**`light_status` is inverted (dark when lit)**
- Set `LIGHT_ACTIVE_LOW 0` in `credentials.h` and reflash.

---

## HTTP / backend

**`[http] skipped - Wi-Fi down`**
- Normal while reconnecting. Watch for it to resume.

**`[http] request failed (connection refused)`**
- Backend not running, or `BACKEND_URL` points at the wrong address/port.
- Run `ipconfig` on the laptop; use the **hotspot adapter's** IPv4, e.g.
  `http://192.168.43.10:5000`.

**`[http] 401 REJECTED`**
- `DEVICE_TOKEN` in the firmware does not match the token saved in the
  dashboard **Settings**. Set both to the same value, or leave both empty.

**`[http] 422 REJECTED: {...}`**
- The backend rejected a field. The JSON body names it, e.g.
  `temperature = 999.0000 is outside the plausible range -40.00-85.00 degC`.
  That is a real wiring/sensor problem, not a server bug — fix the sensor.

**`[http] 201 OK` but the dashboard shows nothing**
- The reading may be old (check the timestamp) or the dashboard is filtering a
  different device/source. Clear the History filters.

---

## Network discovery

Run the bundled helper from the project root:

```
python scripts\diagnose_network.py
```

It prints the laptop's addresses, the expected `BACKEND_URL`, whether port 5000
is listening, and whether a hotspot interface looks active — the fastest way to
find the right IP for `credentials.h`.
