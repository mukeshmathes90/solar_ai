"""Rule-based energy-management demonstration.

This is deliberately transparent: a fixed, explainable allocation policy rather
than a learned controller.  It answers a single question - "given the power we
are generating right now, how should we split it between essential load,
deferrable load and storage?" - and it says so plainly on the dashboard.

SAFETY
------
The relay output is **never** switched automatically.  Automatic load switching
needs a verified wiring harness, a correctly rated relay/SSR and a low-voltage
bench test, none of which can be assumed.  ``relay_control_enabled`` therefore
defaults to 0 and the recommendation is advisory unless an operator explicitly
enables it *and* the node is reporting live data.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

STATUS_SURPLUS = "surplus"
STATUS_BALANCED = "balanced"
STATUS_DEFICIT = "deficit"
STATUS_UNKNOWN = "unknown"


def optimise_energy(reading: Optional[Dict[str, Any]],
                    options: Dict[str, Any]) -> Dict[str, Any]:
    """Allocate current generation across load tiers and storage.

    ``reading`` may be ``None`` (node offline) or contain null power values
    (no connected load).  In both cases the function returns an explicit
    "unknown" status rather than inventing a generation figure.
    """
    names = {
        "critical_load_w": float(options.get("optimize_load_low_w", 1.5)),
        "deferrable_load_w": float(options.get("optimize_load_high_w", 4.0)),
        "reserve_w": float(options.get("optimize_reserve_w", 5.0)),
    }
    device_online = bool(options.get("device_online", False))
    relay_enabled = bool(int(options.get("relay_control_enabled", 0)))
    device_online_s = options.get("device_online_seconds")
    generation = options.get("generation_w")
    predicted_generation = options.get("predicted_generation_w")

    result: Dict[str, Any] = {
        "status": STATUS_UNKNOWN,
        "generation_w": generation,
        "predicted_generation_w": predicted_generation,
        "critical_load_demand_w": names["critical_load_w"],
        "deferrable_load_demand_w": names["deferrable_load_w"],
        "reserve_target_w": names["reserve_w"],
        "allocation": {
            "critical_load_w": None,
            "deferrable_load_w": None,
            "storage_charge_w": None,
            "reserve_held_w": None,
            "curtailed_w": None,
            "deficit_w": None,
        },
        "relay": {
            "enabled": relay_enabled,
            "action": "hold",
            "reason": "Automatic relay switching is disabled for safety.",
        },
        "recommendations": [],
        "assumptions": [
            "Allocation is a transparent rule-based policy, not a learned "
            "optimal controller.",
            "Only measured generation can be allocated; predicted generation is "
            "reported for information and is never switched on.",
            "The relay output stays OFF unless an operator enables relay control "
            "after a verified low-voltage load test.",
        ],
    }

    if generation is None:
        result["recommendations"] = [
            "No generation figure is available - the node has not reported a "
            "measurable power value.",
            "Check whether a load is connected. Without a closed current path "
            "the INA219 reports voltage only and current stays null.",
        ]
        result["relay"]["reason"] = (
            "No measured generation; the relay stays in its safe OFF state.")
        return result

    if not device_online:
        result["recommendations"] = [
            "Node is offline - the last measured generation value may be stale.",
            "Holding the relay OFF until live telemetry resumes.",
        ]
        result["relay"]["reason"] = "Node offline; refusing to switch on stale data."
        if device_online_s is not None:
            result["seconds_since_last_seen"] = device_online_s

    available = max(0.0, float(generation))
    critical = min(names["critical_load_w"], available)
    remaining = available - critical

    reserve_held = min(names["reserve_w"], remaining)
    remaining -= reserve_held

    deferrable = min(names["deferrable_load_w"], remaining)
    remaining -= deferrable

    storage = remaining
    demand = names["critical_load_w"] + names["deferrable_load_w"]
    deficit = max(0.0, demand - available)

    result["allocation"] = {
        "critical_load_w": round(critical, 4),
        "deferrable_load_w": round(deferrable, 4),
        "storage_charge_w": round(storage, 4),
        "reserve_held_w": round(reserve_held, 4),
        "curtailed_w": 0.0,
        "deficit_w": round(deficit, 4),
    }

    if deficit > 0.0:
        result["status"] = STATUS_DEFICIT
    elif storage > 0.05:
        result["status"] = STATUS_SURPLUS
    else:
        result["status"] = STATUS_BALANCED

    recommendations: List[str] = []
    if result["status"] == STATUS_SURPLUS:
        recommendations.append(
            "Surplus of %.2f W available - route it to storage or a deferrable "
            "load." % storage)
        recommendations.append(
            "Deferrable load can run at %.2f W of its %.2f W demand."
            % (deferrable, names["deferrable_load_w"]))
    elif result["status"] == STATUS_BALANCED:
        recommendations.append(
            "Generation just covers essential and deferrable demand; no surplus "
            "for storage this cycle.")
    else:
        recommendations.append(
            "Shortfall of %.2f W against configured demand - shed the "
            "deferrable load before the essential load." % deficit)
        recommendations.append(
            "Essential load served at %.2f W of %.2f W."
            % (critical, names["critical_load_w"]))

    if storage > 0.05:
        recommendations.append(
            "%.2f W is being assigned to storage (simulated energy budget)."
            % storage)

    if predicted_generation is not None:
        delta = float(predicted_generation) - available
        trend = "rising" if delta > 0.05 else ("falling" if delta < -0.05 else "flat")
        recommendations.append(
            "Model expects generation to be %s (%.2f W predicted vs %.2f W "
            "measured this cycle)." % (trend, float(predicted_generation), available))

    if not device_online:
        recommendations.append(
            "Recommendations are based on the last known reading only.")

    result["recommendations"] = recommendations
    result["relay"]["reason"] = (
        "Advisory only: enable relay control in Settings only after a verified "
        "low-voltage load test."
    )
    return result
