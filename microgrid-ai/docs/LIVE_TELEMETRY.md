# Live telemetry over a phone hotspot

The demo runs entirely on a local network with **no internet dependency and no
public exposure**. The phone hotspot is only a private Wi-Fi bridge between the
ESP8266 node and the laptop. The ESP8266 is **never** the dashboard URL — the
dashboard is served by the laptop.

```
  ┌────────────┐   Wi-Fi (2.4 GHz)   ┌──────────────┐   HTTP POST   ┌──────────────────┐
  │ ESP8266    │ ──────────────────► │ Phone hotspot │ ◄──────────── │ Laptop           │
  │ node       │                     │ (router only) │               │ Flask + SQLite   │
  └────────────┘                     └──────────────┘               │ dashboard        │
        sensors                                                    └──────────────────┘
                                                                    browser on same PC
```

Data path: **sensors → ESP8266 → HTTP POST `/api/ingest` → Flask → SQLite →
model → dashboard**. The hotspot just carries the packets.

---

## 1. Turn on the hotspot

**Android:** Settings → Network & internet → Hotspot & tethering → Wi-Fi hotspot.
Set a **2.4 GHz**, WPA2 name/password. Note the SSID and password.

**iPhone:** Settings → Personal Hotspot → allow others to join. (iPhone is
2.4 GHz-compatible but may be more power-aggressive; Android tethering is the
most predictable for this project.)

> 5 GHz-only hotspots will not work — the ESP8266 radio is 2.4 GHz only.

## 2. Join the laptop to the hotspot

Connect the **laptop** to the phone hotspot as well. Both devices must be on the
**same** network.

## 3. Find the laptop's address on that network

```
ipconfig
```

Read the IPv4 address of the Wi-Fi (or Mobile hotspot) adapter. Typical
hotspot subnets look like `192.168.43.x`, `192.168.137.x` or `172.20.10.x`.

Or let the helper do it:

```
python scripts\diagnose_network.py
```

It prints the exact line to paste into the firmware, e.g.:

```
#define BACKEND_URL "http://192.168.43.10:5000"
```

## 4. Start the backend

```
run.bat
```

The console prints `dashboard : http://127.0.0.1:5000/`. Confirm it truly
answers on the LAN address:

```
curl http://192.168.43.10:5000/api/health
```

If that fails, the node cannot reach it either — fix Firewall first (below).

## 5. Configure and flash the node

1. Copy `firmware/microgrid_node/credentials.example.h` →
   `credentials.h`.
2. Fill in `WIFI_SSID`, `WIFI_PASS`, `BACKEND_URL`, and a `DEVICE_TOKEN` that
   matches the dashboard **Settings** page (or leave it empty for development).
3. Flash `firmware/microgrid_node` to the NodeMCU.
4. Open Serial Monitor at **115200**. You should see the IP address, then
   `[http] 201 OK` once per sample cycle.

## 6. Verify on the dashboard

Open `http://127.0.0.1:5000/` on the laptop:

* **Live Monitoring** shows fresh values with source badge **hardware**.
* **Overview → Latest node reading** lists the device with its IP.
* Demo mode pauses automatically: as soon as hardware telemetry arrives, the
  simulated feed stops writing (they share one database but never mix labels).

---

## Firewall

Inbound TCP 5000 must be allowed. `run.bat` attempts to add a rule on first run;
if you prefer to do it manually (Admin PowerShell):

```
New-NetFirewallRule -DisplayName "Microgrid AI backend (5000)" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow
```

To remove it later:

```
Remove-NetFirewallRule -DisplayName "Microgrid AI backend (5000)"
```

---

## Things that break hotspot links

| Problem | Symptom | Fix |
|---|---|---|
| **AP/client isolation** | Node connects, dashboard never updates | Disable "client isolation"/"AP isolation" in hotspot settings; if it cannot be disabled, use a small travel router instead |
| **5 GHz-only hotspot** | ESP8266 never gets an IP | Switch the hotspot band to 2.4 GHz |
| **Wrong subnet** | `BACKEND_URL` unreachable | Re-run `diagnose_network.py` and update `credentials.h` |
| **DHCP lease change** | Worked, then stopped | Re-check the laptop IP; consider reserving it |
| **Laptop sleep** | Node posts, nothing arrives | Disable sleep, or set the power plan to "never" while running the demo |
| **Backend not running** | `[http] connection refused` | Start `run.bat` before the node samples |
| **Firewall** | Times out | Add the inbound rule above |

---

## Nothing here touches the public internet

* No port forwarding, no ngrok, no cloud service, no dynamic DNS.
* The hotspot does not need an internet connection at all (NTP will simply be
  unavailable, and the server stamps timestamps instead).
* If the hotspot has no internet, the node still works — Wi-Fi association is
  local to the phone.

---

## Recording a run

```
python scripts\backup_csv.py
```

Writes a consistent database snapshot plus a CSV export to `backups/`. Useful
before a demo, after collecting data, or before retraining the models on real
readings.
