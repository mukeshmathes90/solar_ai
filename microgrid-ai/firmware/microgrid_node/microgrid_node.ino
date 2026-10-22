/*
 * ============================================================================
 *  microgrid_node.ino  -  ESP8266 (NodeMCU) telemetry node
 *  AI-Enabled Predictive Monitoring and Energy Optimization of a Renewable
 *  Microgrid using IoT
 * ============================================================================
 *
 *  Responsibilities
 *  ----------------
 *  * Read a solar channel and a wind channel through two INA219 modules.
 *  * Read ambient temperature / humidity from a DHT11.
 *  * Count turbine revolutions with a Hall-effect module.
 *  * Classify ambient light as bright / dark with an LDR module.
 *  * Build one stable JSON reading and POST it to the Flask backend.
 *  * Stay responsive: the loop never blocks for more than a few milliseconds.
 *  * Fail loudly: a missing or failed sensor is named in `sensor_status` and
 *    on the serial console rather than being silently replaced with a guess.
 *
 *  Honesty rules baked into this sketch
 *  ------------------------------------
 *  * Generated *current* cannot be measured without a closed current path and a
 *    suitable load.  When no meaningful current is present the field is sent as
 *    `null` (and power as `null`) instead of a fabricated 0 or estimate.
 *  * The relay is held OFF.  No automatic switching happens on the device.
 *  * Wi-Fi credentials never leave this file.
 *
 *  Board   : "NodeMCU 1.0 (ESP-12E Module)"  (esp8266:esp8266:nodemcuv2)
 *  Serial  : 115200 baud
 *
 *  Wiring summary (see docs/WIRING.md for the full table):
 *      I2C  SDA = D2 (GPIO4)      SCL = D1 (GPIO5)   -> both INA219 + optional LCD
 *      DHT11 data = D5 (GPIO14)   (10k pull-up to 3V3)
 *      Hall DO    = D6 (GPIO12)
 *      LDR DO     = D7 (GPIO13)
 *      Relay IN   = D0 (GPIO16)
 * ============================================================================
 */

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <Wire.h>
#include <time.h>

#include <Adafruit_INA219.h>
#include <DHT.h>

/* -------------------------------------------------------------------------- */
/*  Configuration                                                             */
/*  All of the values below can be overridden from credentials.h.             */
/* -------------------------------------------------------------------------- */
#if __has_include("credentials.h")
#include "credentials.h"
#else
#warning "credentials.h not found - using placeholder Wi-Fi/backend values. Copy credentials.example.h to credentials.h."
#endif

#ifndef WIFI_SSID
#define WIFI_SSID "change-me"
#endif
#ifndef WIFI_PASS
#define WIFI_PASS "change-me"
#endif
#ifndef BACKEND_URL
#define BACKEND_URL "http://192.168.43.10:5000"
#endif
#ifndef DEVICE_TOKEN
#define DEVICE_TOKEN ""
#endif
#ifndef DEVICE_ID
#define DEVICE_ID "ESP8266-GRID-01"
#endif
#ifndef SAMPLE_INTERVAL_MS
#define SAMPLE_INTERVAL_MS 5000UL
#endif
#ifndef PULSES_PER_REV
#define PULSES_PER_REV 1
#endif
#ifndef LIGHT_ACTIVE_LOW
#define LIGHT_ACTIVE_LOW 1
#endif
#ifndef RELAY_ACTIVE_LOW
#define RELAY_ACTIVE_LOW 1
#endif

/* ------------------------------------------------------------- pin map ---- */
static const uint8_t PIN_SDA   = 4;   /* D2 */
static const uint8_t PIN_SCL   = 5;   /* D1 */
static const uint8_t PIN_DHT   = 14;  /* D5 */
static const uint8_t PIN_HALL  = 12;  /* D6 */
static const uint8_t PIN_LDR   = 13;  /* D7 */
static const uint8_t PIN_RELAY = 16;  /* D0 */

#define DHT_TYPE DHT11

/* INA219 addresses.  Two modules on one bus MUST use different addresses,
 * selected with the A0/A1 solder jumpers (0x40 = default, 0x41 = A0 bridged). */
static const uint8_t INA219_SOLAR_ADDR = 0x40;
static const uint8_t INA219_WIND_ADDR  = 0x41;

/* Current below this magnitude is treated as "no measurable load" and is
 * reported as null rather than as a real 0 A reading. */
static const float CURRENT_NOISE_MA = 1.5f;

/* --------------------------------------------------------- timing / state -- */
static const unsigned long WIFI_RETRY_MS   = 10000UL;
static const unsigned long SENSOR_RETRY_MS = 30000UL;
static const unsigned long HTTP_TIMEOUT_MS = 4000UL;

Adafruit_INA219 inaSolar(INA219_SOLAR_ADDR);
Adafruit_INA219 inaWind(INA219_WIND_ADDR);
DHT dht(PIN_DHT, DHT_TYPE);

struct InaReading {
  float voltage;   /* V, or NAN when unavailable */
  float current;   /* A, or NAN when not measurable */
  float power;     /* W, or NAN when not measurable */
};

volatile unsigned long hallPulses = 0;
volatile unsigned long hallLastPulseUs = 0;
static const unsigned long HALL_DEBOUNCE_US = 400UL;

bool solarOk = false;
bool windOk  = false;
bool dhtOk   = false;

unsigned long lastSampleMs   = 0;
unsigned long lastWifiTryMs  = 0;
unsigned long lastSensorTryMs = 0;
unsigned long lastBlinkMs    = 0;
bool ledOn = false;

/* -------------------------------------------------------------------------- */
/*  Relay (safe defaults)                                                     */
/* -------------------------------------------------------------------------- */
void setRelay(bool on) {
#if RELAY_ACTIVE_LOW
  digitalWrite(PIN_RELAY, on ? LOW : HIGH);
#else
  digitalWrite(PIN_RELAY, on ? HIGH : LOW);
#endif
}

/* -------------------------------------------------------------------------- */
/*  Hall-effect interrupt                                                     */
/* -------------------------------------------------------------------------- */
void ICACHE_RAM_ATTR hallISR() {
  unsigned long now = micros();
  if (now - hallLastPulseUs < HALL_DEBOUNCE_US) {
    return;                       /* electrical debounce for a noisy edge */
  }
  hallLastPulseUs = now;
  hallPulses++;
}

/* -------------------------------------------------------------------------- */
/*  I2C helpers                                                               */
/* -------------------------------------------------------------------------- */
void scanI2C() {
  Serial.println(F("[i2c] scanning bus..."));
  uint8_t found = 0;
  for (uint8_t address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    if (Wire.endTransmission() == 0) {
      Serial.printf("[i2c]   device at 0x%02X\n", address);
      found++;
    }
  }
  if (found == 0) {
    Serial.println(F("[i2c]   no devices found - check SDA/SCL and pull-ups"));
  }
}

bool beginIna(Adafruit_INA219 &ina, uint8_t address, const char *name) {
  /* Adafruit_INA219 1.2.x takes the bus here; the I2C address is fixed by the
   * constructor, which is why inaSolar / inaWind are built with their own
   * addresses above. */
  if (!ina.begin(&Wire)) {
    Serial.printf("[ina] %s (0x%02X) NOT found\n", name, address);
    return false;
  }
  ina.setCalibration_32V_2A();
  Serial.printf("[ina] %s (0x%02X) ready\n", name, address);
  return true;
}

/* Retry any sensor that failed at boot so a re-seated jumper recovers. */
void ensureSensors() {
  unsigned long now = millis();
  if (now - lastSensorTryMs < SENSOR_RETRY_MS) {
    return;
  }
  lastSensorTryMs = now;

  if (!solarOk) {
    solarOk = beginIna(inaSolar, INA219_SOLAR_ADDR, "solar");
  }
  if (!windOk) {
    windOk = beginIna(inaWind, INA219_WIND_ADDR, "wind");
  }
  if (!dhtOk) {
    dht.begin();
    float probe = dht.readTemperature();
    dhtOk = !isnan(probe);
    Serial.printf("[dht] retry: %s\n", dhtOk ? "ok" : "still failing");
  }
}

/* -------------------------------------------------------------------------- */
/*  Sensor reads                                                              */
/* -------------------------------------------------------------------------- */
InaReading readIna(Adafruit_INA219 &ina, bool available) {
  InaReading reading = {NAN, NAN, NAN};
  if (!available) {
    return reading;
  }
  reading.voltage = ina.getBusVoltage_V();

  float currentMa = ina.getCurrent_mA();
  if (fabs(currentMa) < CURRENT_NOISE_MA) {
    /* Open circuit / no load: current is unknowable, so it stays NAN. */
    reading.current = NAN;
    reading.power = NAN;
  } else {
    reading.current = currentMa / 1000.0f;
    reading.power = ina.getPower_mW() / 1000.0f;
  }
  return reading;
}

bool readClimate(float &temperature, float &humidity) {
  if (!dhtOk) {
    return false;
  }
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  if (isnan(t) || isnan(h)) {
    Serial.println(F("[dht] read failed"));
    dhtOk = false;                /* force a re-init on the next sensor pass */
    return false;
  }
  temperature = t;
  humidity = h;
  return true;
}

const char *readLightStatus() {
  int level = digitalRead(PIN_LDR);
#if LIGHT_ACTIVE_LOW
  bool bright = (level == LOW);
#else
  bool bright = (level == HIGH);
#endif
  return bright ? "bright" : "dark";
}

float computeRpm(unsigned long pulses, unsigned long intervalMs) {
  if (intervalMs == 0) {
    return 0.0f;
  }
  float revolutions = (float)pulses / (float)PULSES_PER_REV;
  return revolutions * 60000.0f / (float)intervalMs;
}

String buildSensorStatus(bool solar, bool wind, bool climate) {
  String status = "";
  if (!solar)   { status += F("SOLAR_INA_FAIL,"); }
  if (!wind)    { status += F("WIND_INA_FAIL,"); }
  if (!climate) { status += F("DHT_FAIL,"); }
  if (status.length() == 0) {
    return String(F("OK"));
  }
  status.remove(status.length() - 1);   /* drop trailing comma */
  return status;
}

/* -------------------------------------------------------------------------- */
/*  JSON helpers                                                              */
/* -------------------------------------------------------------------------- */
String fnum(float value, uint8_t decimals) {
  if (isnan(value) || isinf(value)) {
    return String(F("null"));
  }
  return String(value, decimals);
}

bool isoUtcNow(char *buffer, size_t size) {
  time_t now = time(nullptr);
  if (now < 1700000000) {          /* not synced yet (before Nov 2023) */
    return false;
  }
  struct tm timeinfo;
  gmtime_r(&now, &timeinfo);
  strftime(buffer, size, "%Y-%m-%dT%H:%M:%S+00:00", &timeinfo);
  return true;
}

/* -------------------------------------------------------------------------- */
/*  Wi-Fi / NTP                                                               */
/* -------------------------------------------------------------------------- */
void connectWifiBlocking(uint32_t timeoutMs) {
  Serial.printf("[wifi] connecting to \"%s\"\n", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < timeoutMs) {
    delay(250);
    Serial.print('.');
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[wifi] connected, IP = %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println(F("\n[wifi] initial connect timed out; will keep retrying"));
  }
}

void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }
  unsigned long now = millis();
  if (now - lastWifiTryMs < WIFI_RETRY_MS) {
    return;
  }
  lastWifiTryMs = now;
  Serial.println(F("[wifi] reconnecting..."));
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASS);
}

void syncTime() {
  configTime(0, 0, "pool.ntp.org", "time.nist.gov", "time.google.com");
  Serial.print(F("[ntp] waiting for time"));
  unsigned long start = millis();
  while (time(nullptr) < 1700000000 && millis() - start < 15000) {
    delay(300);
    Serial.print('.');
  }
  if (time(nullptr) >= 1700000000) {
    char stamp[32];
    if (isoUtcNow(stamp, sizeof(stamp))) {
      Serial.printf("\n[ntp] synced, UTC = %s\n", stamp);
    }
  } else {
    Serial.println(F("\n[ntp] NOT synced - readings will be timestamped by the server"));
  }
}

/* -------------------------------------------------------------------------- */
/*  HTTP POST                                                                 */
/* -------------------------------------------------------------------------- */
bool postReading(const String &body) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println(F("[http] skipped - Wi-Fi down"));
    return false;
  }

  String url = String(BACKEND_URL) + "/api/ingest";
  WiFiClient client;
  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);

  if (!http.begin(client, url)) {
    Serial.println(F("[http] could not start request"));
    return false;
  }
  http.addHeader("Content-Type", "application/json");
  if (strlen(DEVICE_TOKEN) > 0) {
    http.addHeader("X-Device-Token", DEVICE_TOKEN);
  }

  int status = http.POST(body);
  bool accepted = (status == 200 || status == 201);

  if (accepted) {
    Serial.printf("[http] %d OK (%u bytes)\n", status, (unsigned)body.length());
  } else if (status > 0) {
    String response = http.getString();
    if (response.length() > 200) {
      response = response.substring(0, 200);
    }
    Serial.printf("[http] %d REJECTED: %s\n", status, response.c_str());
  } else {
    Serial.printf("[http] request failed (%s)\n", http.errorToString(status).c_str());
  }

  http.end();
  return accepted;
}

/* -------------------------------------------------------------------------- */
/*  One sampling cycle                                                        */
/* -------------------------------------------------------------------------- */
void sampleAndSend() {
  unsigned long nowMs = millis();
  unsigned long intervalMs = nowMs - lastSampleMs;
  lastSampleMs = nowMs;

  /* ---- turbine revolutions since the previous cycle --------------------- */
  unsigned long pulses;
  noInterrupts();
  pulses = hallPulses;
  hallPulses = 0;
  interrupts();
  float rpm = computeRpm(pulses, intervalMs);

  /* ---- electrical channels --------------------------------------------- */
  InaReading solar = readIna(inaSolar, solarOk);
  InaReading wind  = readIna(inaWind, windOk);

  /* ---- climate ---------------------------------------------------------- */
  float temperature = NAN;
  float humidity = NAN;
  bool climateOk = readClimate(temperature, humidity);

  const char *light = readLightStatus();
  String sensorStatus = buildSensorStatus(solarOk, windOk, climateOk);

  /* ---- JSON (field order matches the documented contract) --------------- */
  String body = "{";
  body += F("\"device_id\":\"");
  body += DEVICE_ID;
  body += F("\",");

  char stamp[32];
  if (isoUtcNow(stamp, sizeof(stamp))) {
    body += F("\"timestamp\":\"");
    body += stamp;
    body += F("\",");
  }

  body += F("\"solar_voltage\":");  body += fnum(solar.voltage, 3); body += F(",");
  body += F("\"solar_current\":");  body += fnum(solar.current, 4); body += F(",");
  body += F("\"solar_power\":");    body += fnum(solar.power, 4);   body += F(",");
  body += F("\"wind_voltage\":");   body += fnum(wind.voltage, 3);  body += F(",");
  body += F("\"wind_current\":");   body += fnum(wind.current, 4);  body += F(",");
  body += F("\"wind_power\":");     body += fnum(wind.power, 4);    body += F(",");
  body += F("\"turbine_rpm\":");    body += fnum(rpm, 1);           body += F(",");
  body += F("\"temperature\":");    body += fnum(temperature, 2);   body += F(",");
  body += F("\"humidity\":");       body += fnum(humidity, 2);      body += F(",");
  body += F("\"light_status\":\""); body += light;                  body += F("\",");
  body += F("\"sensor_status\":\"");body += sensorStatus;           body += F("\",");
  body += F("\"device_ip\":\"");
  body += WiFi.localIP().toString();
  body += F("\"}");

  Serial.printf("[node] rpm=%.1f solar=%.3fV/%.4fA wind=%.3fV/%.4fA "
                "T=%.2f RH=%.2f light=%s status=%s\n",
                rpm, solar.voltage, solar.current,
                wind.voltage, wind.current,
                temperature, humidity, light, sensorStatus.c_str());

  postReading(body);
}

/* -------------------------------------------------------------------------- */
/*  setup / loop                                                              */
/* -------------------------------------------------------------------------- */
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println();
  Serial.println(F("=============================================="));
  Serial.println(F(" Microgrid AI telemetry node"));
  Serial.printf (" device id : %s\n", DEVICE_ID);
  Serial.printf (" backend   : %s\n", BACKEND_URL);
  Serial.println(F("=============================================="));

  /* Relay first, and straight to its safe OFF state. */
  pinMode(PIN_RELAY, OUTPUT);
  setRelay(false);

  pinMode(PIN_HALL, INPUT);
  pinMode(PIN_LDR, INPUT);

  dht.begin();
  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(100000);

  scanI2C();
  solarOk = beginIna(inaSolar, INA219_SOLAR_ADDR, "solar");
  windOk  = beginIna(inaWind, INA219_WIND_ADDR, "wind");

  float probeTemp = dht.readTemperature();
  dhtOk = !isnan(probeTemp);
  Serial.printf("[dht] %s\n", dhtOk ? "ready" : "NOT responding at boot");

  attachInterrupt(digitalPinToInterrupt(PIN_HALL), hallISR, FALLING);

  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  connectWifiBlocking(20000);
  syncTime();

  lastSampleMs = millis();
  Serial.printf("[node] ready. sampling every %lu ms\n", (unsigned long)SAMPLE_INTERVAL_MS);
}

void loop() {
  ensureWifi();
  ensureSensors();

  unsigned long now = millis();

  if (now - lastSampleMs >= SAMPLE_INTERVAL_MS) {
    sampleAndSend();
  }

  /* Slow on-board LED blink = "running" heartbeat. */
  if (now - lastBlinkMs >= 1000UL) {
    lastBlinkMs = now;
    ledOn = !ledOn;
    digitalWrite(LED_BUILTIN, ledOn ? LOW : HIGH);   /* NodeMCU LED is active low */
  }

  delay(2);
}
