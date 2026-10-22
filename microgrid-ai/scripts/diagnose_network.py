"""Diagnose the laptop side of the microgrid telemetry link.

Run this from the project root while the phone hotspot and the Flask backend are
running::

    python scripts/diagnose_network.py

It reports, in order:

* every IPv4 address on this machine, with the Windows adapter name,
* which addresses look like a phone-hotspot subnet,
* the value to paste into ``BACKEND_URL`` in
  ``firmware/microgrid_node/credentials.h``,
* whether the backend port is actually listening on this machine,
* the most common reasons the node still cannot reach it.

The script is read-only: it changes nothing and needs no third-party packages.
"""

from __future__ import annotations

import argparse
import re
import socket
import subprocess
import sys
from typing import List, Tuple

# Subnets commonly handed out by phone hotspots and Windows Mobile Hotspot.
HOTSPOT_PREFIXES = (
    "192.168.43.",   # Android tethering (very common)
    "192.168.42.",   # Android alternate
    "192.168.137.",  # Windows Mobile Hotspot
    "172.20.10.",    # iPhone personal hotspot
    "192.168.2.",    # some Android/tablet hotspots
)

IPV4_RE = re.compile(r"IPv4 Address[^:]*:\s*(\d+\.\d+\.\d+\.\d+)")
ADAPTER_RE = re.compile(r"^[A-Za-z].*adapter\s+(.+?):\s*$")


def _run_ipconfig() -> str:
    try:
        completed = subprocess.run(
            ["ipconfig"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout or ""


def parse_ipconfig(text: str) -> List[Tuple[str, str]]:
    """Return a list of (adapter_name, ipv4) pairs from ``ipconfig`` output."""
    pairs: List[Tuple[str, str]] = []
    adapter = "unknown adapter"
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        match = ADAPTER_RE.match(line)
        if match:
            adapter = match.group(1).strip()
            continue
        found = IPV4_RE.search(line)
        if found:
            pairs.append((adapter, found.group(1)))
    return pairs


def fallback_addresses() -> List[Tuple[str, str]]:
    """Best-effort address list when ``ipconfig`` is unavailable."""
    seen = set()
    pairs: List[Tuple[str, str]] = []
    for family in (socket.AF_INET,):
        try:
            infos = socket.getaddrinfo(socket.gethostname(), None, family, socket.SOCK_STREAM)
        except socket.gaierror:
            continue
        for info in infos:
            address = info[4][0]
            if address not in seen:
                seen.add(address)
                pairs.append(("(resolved hostname)", address))
    return pairs


def is_hotspot(address: str) -> bool:
    return any(address.startswith(prefix) for prefix in HOTSPOT_PREFIXES)


def is_link_local(address: str) -> bool:
    """169.254.x.x means the adapter never got a DHCP lease - not usable."""
    return address.startswith("169.254.")


def is_loopback(address: str) -> bool:
    return address.startswith("127.")


def port_listening(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5000,
                        help="backend port (default 5000)")
    parser.add_argument("--path", default="/api/ingest",
                        help="ingest path (default /api/ingest)")
    args = parser.parse_args()

    print("Microgrid telemetry network diagnostic")
    print("=" * 52)
    print("hostname : %s" % socket.gethostname())

    pairs = parse_ipconfig(_run_ipconfig())
    if not pairs:
        print("(ipconfig unavailable - falling back to name resolution)")
        pairs = fallback_addresses()

    if not pairs:
        print("\nNo IPv4 addresses found. Is any network adapter up?")
        return 1

    print("\nIPv4 addresses")
    for adapter, address in pairs:
        note = ""
        if is_hotspot(address):
            note = "  <-- looks like a phone hotspot"
        elif is_link_local(address):
            note = "  <-- link-local, no DHCP lease (not usable)"
        elif is_loopback(address):
            note = "  <-- loopback"
        print("  %-38s %s%s" % (adapter[:38], address, note))

    hotspot = [(a, ip) for a, ip in pairs if is_hotspot(ip)]
    usable = [(a, ip) for a, ip in pairs
              if not is_hotspot(ip) and not is_link_local(ip) and not is_loopback(ip)]
    no_usable = not hotspot and not usable

    print("\nSuggested credentials.h value")
    if hotspot:
        _, ip = hotspot[0]
        print('  #define BACKEND_URL "http://%s:%d"' % (ip, args.port))
        print("  (a phone-hotspot subnet was detected - the ESP8266 should")
        print("   join the same hotspot)")
    elif usable:
        _, ip = usable[0]
        print('  #define BACKEND_URL "http://%s:%d"' % (ip, args.port))
        print("  (no obvious hotspot subnet found; confirm this adapter is the")
        print("   one the ESP8266 will share a network with)")
    else:
        print("  No usable address found. Join the phone hotspot (or start a")
        print("  Windows Mobile Hotspot) and re-run this script.")

    print("\nBackend reachability")
    loop_ok = port_listening("127.0.0.1", args.port)
    print("  localhost:%d  -> %s" % (args.port, "listening" if loop_ok else "NOT listening"))
    for _, ip in pairs:
        if is_loopback(ip):
            continue
        ok = port_listening(ip, args.port)
        print("  %-15s -> %s" % (ip + ":" + str(args.port), "listening" if ok else "not reachable"))

    print("\nChecklist if the node cannot POST")
    checks = [
        "Start the backend (run.bat) - it must be listening before the node posts.",
        "ESP8266 supports 2.4 GHz Wi-Fi only; a 5 GHz hotspot will never work.",
        "Laptop and node must be on the SAME hotspot network.",
        "Some hotspots isolate clients (AP isolation) - disable it if available.",
        "Windows Firewall must allow inbound TCP %d (run.bat adds the rule)." % args.port,
        "Confirm BACKEND_URL has the scheme and port: http://IP:%d" % args.port,
        "Test from the phone/laptop browser: http://<ip>:%d/api/health" % args.port,
    ]
    for index, text in enumerate(checks, start=1):
        print("  %d. %s" % (index, text))

    healthy = loop_ok and not no_usable
    print("\nRESULT: %s" % ("looks ready" if healthy
                            else "ACTION NEEDED - see the checklist above"))
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
