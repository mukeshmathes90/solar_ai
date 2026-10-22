/*
 * credentials.example.h
 * ---------------------
 * Copy this file to `credentials.h` (same folder, NOT committed to git) and
 * fill in your own values.  `microgrid_node.ino` picks it up automatically;
 * if the file is missing the sketch still compiles with placeholder values so
 * that the build can be verified without any secrets.
 *
 *   copy credentials.example.h credentials.h
 */

#ifndef MICROGRID_CREDENTIALS_H
#define MICROGRID_CREDENTIALS_H

/* ---------------------------------------------------------------- Wi-Fi --- */
/* Phone hotspot (or any 2.4 GHz AP the laptop is also joined to).
 * The ESP8266 does NOT support 5 GHz networks. */
#define WIFI_SSID       "your-hotspot-name"
#define WIFI_PASS       "your-hotspot-password"

/* -------------------------------------------------------------- Backend --- */
/* Address of the laptop running the Flask backend, on the SAME network.
 * Find it by running `ipconfig` on the laptop and reading the IPv4 address of
 * the Wi-Fi / "Mobile hotspot" adapter.  Keep the scheme and port. */
#define BACKEND_URL     "http://192.168.43.10:5000"

/* Must match the device token saved on the dashboard Settings page.
 * Leave empty ("") to disable token checking (development only). */
#define DEVICE_TOKEN    ""

/* ----------------------------------------------------------- Identity ----- */
/* The name this node reports; it appears on the dashboard device list. */
#define DEVICE_ID       "ESP8266-GRID-01"

/* ------------------------------------------------------- Sampling rate ---- */
/* How often the node samples every sensor and posts one JSON reading, in
 * milliseconds.  Called out to be >= 2000 ms because the DHT11 needs 2 s
 * between conversions.  This is a firmware setting; the dashboard's
 * "sampling interval" is advisory documentation of it. */
#define SAMPLE_INTERVAL_MS  5000

/* ------------------------------------------------ Turbine pulse counting -- */
/* Number of Hall-sensor pulses produced per full revolution of the turbine.
 * Count the pulses for one hand-turn, or read the datasheet of your rotor:
 * many small wind turbines with a single magnet produce 1 pulse per rev. */
#define PULSES_PER_REV  1

/* ------------------------------------------------ Light module polarity -- */
/* Most LDR comparator modules (e.g. KY-018 style) drive their digital output
 * LOW when the sensor is brightly lit.  Set to 0 if your module is inverted. */
#define LIGHT_ACTIVE_LOW  1

/* --------------------------------------------------------------- Relay ---- */
/* The relay is held OFF at boot and is never switched automatically by this
 * firmware.  Automatic load switching is a dashboard-side, opt-in feature that
 * must not be used until a correctly rated relay and a low-voltage bench test
 * have been verified. */
#define RELAY_ACTIVE_LOW  1

#endif /* MICROGRID_CREDENTIALS_H */
