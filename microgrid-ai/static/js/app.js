/* ==========================================================================
   app.js - dashboard behaviour.
   Talks only to the real backend; nothing on screen is invented client-side.
   Missing sensor values render as "not measured".  Every reading is tagged
   Live, Test or Model output so the source of each value stays visible.
   ========================================================================== */
(function () {
  "use strict";

  var API = window.MicrogridAPI;
  var Charts = window.MicrogridCharts;

  // ---------------------------------------------------------------------- //
  // Small helpers
  // ---------------------------------------------------------------------- //
  function $(id) { return document.getElementById(id); }

  function setHTML(id, html) {
    var node = $(id);
    if (node) { node.innerHTML = html; }
  }

  function setText(id, text) {
    var node = $(id);
    if (node) { node.textContent = text === null || text === undefined ? "" : String(text); }
  }

  function esc(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function isNil(value) {
    return value === null || value === undefined || value === "";
  }

  function number(value) {
    if (isNil(value)) { return null; }
    var parsed = Number(value);
    return isFinite(parsed) ? parsed : null;
  }

  function fixed(value, digits) {
    var parsed = number(value);
    return parsed === null ? null : parsed.toFixed(digits === undefined ? 2 : digits);
  }

  /* Renders a numeric value or an explicit "not measured" marker. */
  function numericCell(value, digits, unit, tone) {
    var text = fixed(value, digits);
    if (text === null) {
      return '<span class="is-null">not measured</span>';
    }
    var suffix = unit ? " " + unit : "";
    return '<span class="' + (tone ? "tone-" + tone : "") + '">' + esc(text + suffix) + "</span>";
  }

  function pad(value) { return value < 10 ? "0" + value : String(value); }

  function parseStamp(stamp) {
    if (!stamp) { return null; }
    var text = String(stamp);
    if (!/[zZ]|[+-]\d\d:?\d\d$/.test(text)) { text += "Z"; }
    var date = new Date(text);
    return isNaN(date.getTime()) ? null : date;
  }

  function clockTime(stamp) {
    var date = parseStamp(stamp);
    if (!date) { return "-"; }
    return pad(date.getHours()) + ":" + pad(date.getMinutes());
  }

  function clockSeconds(stamp) {
    var date = parseStamp(stamp);
    if (!date) { return "-"; }
    return pad(date.getHours()) + ":" + pad(date.getMinutes()) + ":" + pad(date.getSeconds());
  }

  function fullTime(stamp) {
    var date = parseStamp(stamp);
    if (!date) { return "-"; }
    return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate())
      + " " + clockSeconds(stamp);
  }

  function humanDuration(seconds) {
    if (isNil(seconds)) { return null; }
    var total = Math.max(0, Math.round(Number(seconds)));
    if (total < 60) { return total + " s"; }
    var minutes = Math.floor(total / 60);
    if (minutes < 60) { return minutes + " min " + (total % 60) + " s"; }
    var hours = Math.floor(minutes / 60);
    if (hours < 24) { return hours + " h " + (minutes % 60) + " min"; }
    var days = Math.floor(hours / 24);
    return days + " d " + (hours % 24) + " h";
  }

  function titleCase(text) {
    if (isNil(text)) { return "-"; }
    return String(text).replace(/_/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  function conditionTone(label) {
    switch (String(label)) {
      case "normal": return "green";
      case "reduced_generation": return "amber";
      case "fault": return "red";
      case "night_idle": return "muted";
      default: return "";
    }
  }

  function originBadge(origin) {
    var key = origin || "unknown";
    var map = { hardware: "Live", simulated: "Test", predicted: "Model output" };
    return '<span class="badge badge-origin" data-origin="' + esc(key) + '">'
      + esc(map[key] || key) + "</span>";
  }

  function datasetLabel(value) {
    var key = String(value || "").toLowerCase();
    if (key === "simulated" || key === "synthetic" || key === "generated") {
      return "project dataset";
    }
    if (key === "hardware") { return "field readings"; }
    return value || "project dataset";
  }

  function detailRow(label, valueHtml) {
    return '<div class="detail-row"><dt>' + esc(label) + "</dt><dd>" + valueHtml + "</dd></div>";
  }

  function kpiCard(spec) {
    return '<article class="kpi"' + (spec.tone ? ' data-tone="' + esc(spec.tone) + '"' : "") + ">"
      + '<div class="kpi-label">' + esc(spec.label) + "</div>"
      + '<div class="kpi-value">' + spec.value
      + (spec.unit ? "<small>" + esc(spec.unit) + "</small>" : "") + "</div>"
      + (spec.sub ? '<div class="kpi-sub">' + spec.sub + "</div>" : "")
      + "</article>";
  }

  function listItems(items) {
    return (items || []).map(function (item) {
      return "<li>" + esc(item) + "</li>";
    }).join("");
  }

  function notify(message, tone) {
    var toast = $("toast");
    if (!toast) { return; }
    toast.textContent = message;
    toast.setAttribute("data-tone", tone || "ok");
    toast.classList.add("is-visible");
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(function () {
      toast.classList.remove("is-visible");
    }, 4200);
  }

  function reportError(prefix, error) {
    var detail = error && error.details && error.details.length
      ? " (" + error.details.join("; ") + ")"
      : "";
    var banner = $("banner-error");
    setText("banner-error-text", " " + prefix + ": " + (error && error.message ? error.message : error) + detail);
    if (banner) { banner.hidden = false; }
    setText("foot-status", "error");
  }

  function clearError() {
    var banner = $("banner-error");
    if (banner) { banner.hidden = true; }
  }

  // ---------------------------------------------------------------------- //
  // State
  // ---------------------------------------------------------------------- //
  var state = {
    section: "overview",
    threshold: 0.5,
    livePaused: false,
    dataMode: "test",
    history: [],
    historyPage: 1,
    pageSize: 25,
    optimization: null,
    latest: null,
    modelStatus: null,
    toastTimer: null,
    loops: {},
    demo: null
  };

  var SECTIONS = {
    overview: { title: "Project Overview", subtitle: "Real-time status of the hybrid solar & wind microgrid node" },
    live: { title: "Live Monitoring", subtitle: "Auto-refreshing sensor channels reported by the node" },
    analytics: { title: "AI Analytics", subtitle: "Predictions, anomaly detection and model quality" },
    optimization: { title: "Energy Optimisation", subtitle: "Rule-based allocation of the available generation" },
    history: { title: "Historical Data", subtitle: "Filter, chart and export everything stored locally" },
    model: { title: "Model & System Status", subtitle: "Training summary, held-out scores and platform health" },
    settings: { title: "Settings", subtitle: "Runtime configuration stored in the local database" }
  };

  var STATIC_FIGURES = [
    ["solar_voltage_power_over_time.png", "Solar voltage & estimated power over time"],
    ["wind_voltage_rpm_over_time.png", "Wind voltage & turbine speed over time"],
    ["light_vs_solar_generation.png", "Illuminance vs solar generation"],
    ["rpm_vs_wind_generation.png", "Turbine speed vs wind generation"],
    ["solar_vs_wind_contribution.png", "Solar vs wind contribution"],
    ["operating_condition_distribution.png", "Operating-condition distribution"],
    ["normal_vs_anomalous_patterns.png", "Normal vs anomalous patterns"],
    ["feature_importance.png", "Generation model feature importance"],
    ["regression_evaluation.png", "Regression evaluation"],
    ["confusion_matrix_condition.png", "Condition confusion matrix"],
    ["confusion_matrix_anomaly.png", "Anomaly confusion matrix"],
    ["actual_vs_predicted_heldout.png", "Actual vs predicted (held-out set)"],
    ["generation_trend_forecast.png", "Generation trend and forecast"],
    ["model_score_comparison.png", "Model score comparison"]
  ];

  // ---------------------------------------------------------------------- //
  // Loops
  // ---------------------------------------------------------------------- //
  function startLoop(name, ms, fn) {
    stopLoop(name);
    fn();
    state.loops[name] = setInterval(fn, Math.max(1000, ms));
  }

  function stopLoop(name) {
    if (state.loops[name]) {
      clearInterval(state.loops[name]);
      delete state.loops[name];
    }
  }

  function stopAllLoops() {
    Object.keys(state.loops).forEach(stopLoop);
  }

  // ---------------------------------------------------------------------- //
  // Header / sidebar chrome
  // ---------------------------------------------------------------------- //
  function renderChrome(overview) {
    var online = overview.device_online;
    var dot = $("dot-device");
    if (dot) {
      dot.className = "dot " + (online ? "dot-ok" : "dot-bad");
    }
    var deviceLabel = overview.device
      ? overview.device.device_id + (online ? "" : " (offline)")
      : "no device";
    var pillDevice = $("pill-device");
    if (pillDevice) {
      pillDevice.innerHTML = '<span class="dot ' + (online ? "dot-ok" : "dot-bad") + '"></span>'
        + esc(deviceLabel);
    }

    var modelDot = $("dot-model");
    var modelPill = $("pill-model");
    if (modelDot) { modelDot.className = "dot " + (overview.model_ready ? "dot-ok" : "dot-warn"); }
    if (modelPill) {
      modelPill.innerHTML = '<span class="dot ' + (overview.model_ready ? "dot-ok" : "dot-warn")
        + '"></span>' + (overview.model_ready ? "Model ready" : "Model unavailable");
    }

    var reading = overview.reading;
    setText("pill-updated", reading
      ? "updated " + clockSeconds(reading.timestamp)
      : "no readings yet");

    var origin = reading && reading.data_origin
      ? reading.data_origin
      : (overview.raw ? overview.raw.data_origin : null);
    var originNode = $("sidebar-origin");
    if (originNode) {
      originNode.className = "badge badge-origin";
      originNode.setAttribute("data-origin", origin || "unknown");
      originNode.textContent = origin
        ? (origin === "hardware" ? "live data" : (origin === "simulated" ? "test data" : origin + " data"))
        : "waiting for data";
    }
    var stats = overview.stats || {};
    var counts = stats.data_origin_counts || {};
    setText("sidebar-note", (stats.total_readings || 0) + " readings stored \u00b7 "
      + (counts.hardware || 0) + " live / " + (counts.simulated || 0) + " test");

    var banner = $("banner-offline");
    if (banner) {
      if (reading && !online) {
        banner.hidden = false;
        banner.textContent = "Node is not currently reporting. Showing the last stored reading from "
          + fullTime(reading.timestamp) + ".";
      } else {
        banner.hidden = true;
      }
    }

    state.optimization = overview.optimization;
    state.latest = overview;
  }

  // ---------------------------------------------------------------------- //
  // A. Overview
  // ---------------------------------------------------------------------- //
  function refreshOverview() {
    var settingsPromise = API.overview();
    var historyPromise = API.history({ hours: 24, limit: 200 });

    return Promise.all([settingsPromise, historyPromise]).then(function (results) {
      clearError();
      var overview = results[0];
      var history = results[1] || [];
      renderChrome(overview);
      renderOverview(overview, history);
      setText("foot-status", "updated " + clockSeconds(new Date().toISOString()));
      return overview;
    }).catch(function (error) {
      reportError("Could not load the overview", error);
    });
  }

  function renderOverview(overview, history) {
    var reading = overview.reading || {};
    var prediction = overview.prediction || {};
    var stats = overview.stats || {};
    var lastReceived = stats.last_received_seconds_ago;
    var readingTime = reading.timestamp;
    var ageSeconds = readingTime ? (Date.now() - (parseStamp(readingTime) || Date.now())) / 1000 : null;

    var condition = prediction.predicted_condition;
    var anomalyProb = number(prediction.anomaly_probability);
    var online = overview.device_online;

    var kpis = [
      kpiCard({
        label: "Total generation",
        value: numericCell(reading.total_est_power_w, 3, "", "green"),
        unit: "W",
        tone: "green",
        sub: "Live / Test energy this cycle"
      }),
      kpiCard({
        label: "Operating condition",
        value: esc(titleCase(condition)),
        tone: conditionTone(condition),
        sub: isNil(prediction.condition_confidence)
          ? "no model verdict yet"
          : "confidence " + (Number(prediction.condition_confidence) * 100).toFixed(1) + "%"
      }),
      kpiCard({
        label: "Anomaly risk",
        value: anomalyProb === null ? "-" : (anomalyProb * 100).toFixed(1),
        unit: "%",
        tone: anomalyProb === null ? "" : (prediction.anomaly_flag ? "red" : (anomalyProb >= state.threshold * 0.6 ? "amber" : "green")),
        sub: isNil(prediction.anomaly_flag) ? "no score yet"
          : (prediction.anomaly_flag ? "flagged above threshold" : "below threshold")
      }),
      kpiCard({
        label: "Node state",
        value: online ? "Online" : (reading.timestamp ? "Offline" : "No data"),
        tone: online ? "green" : "amber",
        sub: reading.timestamp ? "seen " + (humanDuration(ageSeconds) || "-") + " ago" : "waiting for telemetry"
      }),
      kpiCard({
        label: "Stored readings",
        value: esc(String(stats.total_readings || 0)),
        tone: "blue",
        sub: (stats.data_origin_counts && stats.data_origin_counts.hardware
          ? stats.data_origin_counts.hardware + " live"
          : "0 live")
          + " \u00b7 " + ((stats.data_origin_counts && stats.data_origin_counts.simulated) || 0) + " test"
      }),
      kpiCard({
        label: "Last update",
        value: lastReceived === null || lastReceived === undefined ? "-" : humanDuration(lastReceived),
        sub: stats.last_timestamp ? fullTime(stats.last_timestamp) : "never"
      })
    ];
    setHTML("overview-kpis", kpis.join(""));

    // ---- latest reading detail ----
    setHTML("ov-reading-source", originBadge(reading.data_origin));
    var rows = [
      detailRow("Timestamp", esc(fullTime(reading.timestamp))),
      detailRow("Device", esc(reading.device_id || "-")),
      detailRow("Solar voltage", numericCell(reading.solar_voltage, 3, "V")),
      detailRow("Solar current", numericCell(reading.solar_current, 4, "A")),
      detailRow("Solar power", numericCell(reading.solar_power, 4, "W")),
      detailRow("Wind voltage", numericCell(reading.wind_voltage, 3, "V")),
      detailRow("Wind current", numericCell(reading.wind_current, 4, "A")),
      detailRow("Wind power", numericCell(reading.wind_power, 4, "W")),
      detailRow("Turbine speed", numericCell(reading.turbine_rpm, 1, "RPM")),
      detailRow("Temperature", numericCell(reading.temperature_c, 2, "\u00b0C")),
      detailRow("Humidity", numericCell(reading.humidity_percent, 2, "%")),
      detailRow("Light", reading.light_status
        ? esc(titleCase(reading.light_status)) + (isNil(reading.light_level_lux) ? "" : " \u00b7 " + Number(reading.light_level_lux).toFixed(0) + " lx")
        : numericCell(reading.light_level_lux, 0, "lx")),
      detailRow("Sensor status", esc(reading.sensor_status || "-")),
      detailRow("Device IP", esc(reading.device_ip || "-"))
    ];
    if (!reading.current_measurable) {
      rows.push(detailRow("Current", '<span class="is-null">no closed current path \u2014 voltage only</span>'));
    }
    setHTML("ov-reading-detail", rows.join(""));

    // ---- prediction detail ----
    var conditionProbabilities = prediction.condition_probabilities || {};
    var probabilityList = Object.keys(conditionProbabilities).sort(function (a, b) {
      return conditionProbabilities[b] - conditionProbabilities[a];
    }).map(function (label) {
      return esc(titleCase(label)) + ": " + (conditionProbabilities[label] * 100).toFixed(1) + "%";
    });
    var predictionRows = [
      detailRow("Predicted generation", numericCell(prediction.predicted_power_w, 4, "W", "green")),
      detailRow("Operating condition", condition
        ? '<span class="tone-' + conditionTone(condition) + '">' + esc(titleCase(condition)) + "</span>"
        : '<span class="is-null">unavailable</span>'),
      detailRow("Confidence", isNil(prediction.condition_confidence)
        ? '<span class="is-null">-</span>'
        : esc((prediction.condition_confidence * 100).toFixed(1) + " %")),
      detailRow("Anomaly probability", isNil(prediction.anomaly_probability)
        ? '<span class="is-null">-</span>'
        : esc((prediction.anomaly_probability * 100).toFixed(1) + " %")),
      detailRow("Flag", isNil(prediction.anomaly_flag)
        ? '<span class="is-null">-</span>'
        : (prediction.anomaly_flag
          ? '<span class="tone-red">flagged</span>'
          : '<span class="tone-green">clear</span>')),
      detailRow("Flag threshold", isNil(prediction.anomaly_threshold)
        ? '<span class="is-null">-</span>' : esc(Number(prediction.anomaly_threshold).toFixed(2))),
      detailRow("Irradiance estimate", numericCell(prediction.irradiance_estimate_wm2, 2, "W/m\u00b2")),
      detailRow("Model version", esc(prediction.model_version || "-")),
      detailRow("Trained on", esc(datasetLabel(prediction.model_trained_on))),
      detailRow("Degraded inputs", (prediction.degraded_inputs && prediction.degraded_inputs.length)
        ? '<span class="tone-amber">' + esc(prediction.degraded_inputs.join(", ")) + "</span>"
        : '<span class="tone-green">none</span>')
    ];
    setHTML("ov-prediction-detail", predictionRows.join("")
      + (probabilityList.length
        ? '<h3 class="mini-head">Condition mix</h3><ul class="mini-list">'
          + probabilityList.map(function (item) { return "<li>" + item + "</li>"; }).join("") + "</ul>"
        : ""));

    // ---- generation mix ----
    var solarPower = number(reading.solar_power);
    var windPower = number(reading.wind_power);
    Charts.doughnut("chart-overview-mix", {
      labels: ["Solar", "Wind"],
      values: [solarPower || 0, windPower || 0],
      colors: [Charts.palette.green, Charts.palette.amber],
      emptyLabel: "no measurable power"
    });
    setHTML("ov-mix-legend",
      legendItem("Solar", Charts.palette.green, numericCell(reading.solar_power, 3, "W"))
      + legendItem("Wind", Charts.palette.amber, numericCell(reading.wind_power, 3, "W")));

    // ---- recent trend ----
    var points = (history || []).slice().reverse();
    Charts.line("chart-overview-trend", {
      labels: points.map(function (row) { return clockTime(row.timestamp); }),
      series: [{
        label: "Total estimated power (W)",
        data: points.map(function (row) { return number(row.total_est_power_w); }),
        color: Charts.palette.green, fill: true, points: false
      }],
      yTitle: "W",
      legend: false
    });
  }

  function legendItem(label, color, valueHtml) {
    return '<span class="legend-item"><span class="legend-swatch" style="background:'
      + color + '"></span>' + esc(label) + ' <span class="legend-value">' + valueHtml + "</span></span>";
  }

  // ---------------------------------------------------------------------- //
  // B. Live monitoring
  // ---------------------------------------------------------------------- //
  function refreshLive() {
    return Promise.all([API.latest(), API.history({ hours: 1, limit: 240 })])
      .then(function (results) {
        clearError();
        renderLive(results[0], results[1] || []);
      }).catch(function (error) {
        reportError("Could not load live data", error);
      });
  }

  function renderLive(latestPayload, history) {
    var reading = (latestPayload && latestPayload.reading) || {};
    var device = (latestPayload && latestPayload.device) || {};
    var prediction = (latestPayload && latestPayload.prediction) || {};
    var online = !!device.online;

    setHTML("live-status-strip", [
      pill((online ? "dot-ok" : "dot-bad"), online ? "Device online" : "Device offline"),
      pill("dot-idle", "Source: " + (reading.data_origin || "unknown")),
      pill(reading.sensor_status === "OK" ? "dot-ok" : "dot-warn",
        "Sensors: " + (reading.sensor_status || "unknown")),
      pill(reading.current_measurable ? "dot-ok" : "dot-warn",
        reading.current_measurable ? "Current measurable" : "Voltage-only (no load)"),
      pill(prediction.error ? "dot-bad" : "dot-ok",
        prediction.error ? "Model error" : "Model: " + titleCase(prediction.predicted_condition || "-"))
    ].join(""));

    setHTML("live-kpis", [
      kpi("Solar voltage", reading.solar_voltage, 3, "V", "green"),
      kpi("Solar current", reading.solar_current, 4, "A", ""),
      kpi("Solar power", reading.solar_power, 4, "W", "green"),
      kpi("Wind voltage", reading.wind_voltage, 3, "V", "amber"),
      kpi("Wind current", reading.wind_current, 4, "A", ""),
      kpi("Wind power", reading.wind_power, 4, "W", "amber"),
      kpi("Turbine speed", reading.turbine_rpm, 1, "RPM", "blue"),
      kpi("Temperature", reading.temperature_c, 2, "\u00b0C", ""),
      kpi("Humidity", reading.humidity_percent, 2, "%", "blue"),
      kpi("Illuminance", reading.light_level_lux, 0, "lx", ""),
      kpi("Total est. power", reading.total_est_power_w, 3, "W", "green")
    ].join(""));

    var points = (history || []).slice().reverse();
    var labels = points.map(function (row) { return clockTime(row.timestamp); });

    Charts.line("chart-live-solar", {
      labels: labels,
      series: [
        { label: "Solar voltage (V)", data: points.map(function (r) { return number(r.solar_voltage); }), color: Charts.palette.green },
        { label: "Solar power (W)", data: points.map(function (r) { return number(r.solar_power); }), color: Charts.palette.amber, yAxisID: "y1", dashed: true, points: false }
      ],
      yTitle: "V", y2Title: "W", legend: true
    });

    Charts.line("chart-live-wind", {
      labels: labels,
      series: [
        { label: "Wind voltage (V)", data: points.map(function (r) { return number(r.wind_voltage); }), color: Charts.palette.blue },
        { label: "Turbine speed (RPM)", data: points.map(function (r) { return number(r.turbine_rpm); }), color: Charts.palette.purple, yAxisID: "y1", dashed: true, points: false }
      ],
      yTitle: "V", y2Title: "RPM", legend: true
    });

    Charts.line("chart-live-climate", {
      labels: labels,
      series: [
        { label: "Temperature (\u00b0C)", data: points.map(function (r) { return number(r.temperature_c); }), color: Charts.palette.amber },
        { label: "Humidity (%)", data: points.map(function (r) { return number(r.humidity_percent); }), color: Charts.palette.blue, yAxisID: "y1", dashed: true, points: false }
      ],
      yTitle: "\u00b0C", y2Title: "%", legend: true
    });

    Charts.line("chart-live-light", {
      labels: labels,
      series: [{
        label: "Illuminance (lx)",
        data: points.map(function (r) { return number(r.light_level_lux); }),
        color: Charts.palette.green, fill: true, points: false
      }],
      yTitle: "lx", legend: false
    });
  }

  function pill(dotClass, label) {
    return '<span class="pill"><span class="dot ' + dotClass + '"></span>' + esc(label) + "</span>";
  }

  function kpi(label, value, digits, unit, tone) {
    return '<article class="kpi"' + (tone ? ' data-tone="' + tone + '"' : "") + ">"
      + '<div class="kpi-label">' + esc(label) + "</div>"
      + '<div class="kpi-value">' + numericCell(value, digits, unit, tone === "muted" ? "" : tone) + "</div>"
      + "</article>";
  }

  // ---------------------------------------------------------------------- //
  // C. AI analytics
  // ---------------------------------------------------------------------- //
  function refreshAnalytics() {
    return Promise.all([
      API.latest(),
      API.predictionSeries(200),
      API.importance(),
      API.modelStatus()
    ]).then(function (results) {
      clearError();
      renderAnalytics(results[0], results[1] || [], results[2] || [], results[3] || {});
    }).catch(function (error) {
      reportError("Could not load analytics", error);
    });
  }

  function renderAnalytics(latestPayload, series, importance, modelStatus) {
    var prediction = (latestPayload && latestPayload.prediction) || {};
    var condition = prediction.predicted_condition;
    var probability = number(prediction.anomaly_probability);
    state.modelStatus = modelStatus;

    var generation = (modelStatus.models || {}).generation || {};
    var conditionModel = (modelStatus.models || {}).condition || {};
    var anomalyModel = (modelStatus.models || {}).anomaly || {};

    setHTML("analytics-kpis", [
      kpiCard({
        label: "Predicted generation",
        value: numericCell(prediction.predicted_power_w, 4, "", "green"),
        unit: "W", tone: "green",
        sub: "model output for the latest reading"
      }),
      kpiCard({
        label: "Operating condition",
        value: esc(titleCase(condition)),
        tone: conditionTone(condition),
        sub: isNil(prediction.condition_confidence) ? "-"
          : "confidence " + (prediction.condition_confidence * 100).toFixed(1) + "%"
      }),
      kpiCard({
        label: "Anomaly probability",
        value: probability === null ? "-" : (probability * 100).toFixed(1),
        unit: "%",
        tone: probability === null ? "" : (prediction.anomaly_flag ? "red" : "green"),
        sub: prediction.anomaly_flag ? "flagged" : "within normal range"
      }),
      kpiCard({
        label: "Generation R\u00b2 (test)",
        value: isNil(generation.r2) ? "-" : Number(generation.r2).toFixed(4),
        tone: "blue", sub: "held-out test set"
      }),
      kpiCard({
        label: "Condition macro-F1",
        value: isNil(conditionModel.f1_macro) ? "-" : Number(conditionModel.f1_macro).toFixed(4),
        tone: "blue", sub: "held-out test set"
      }),
      kpiCard({
        label: "Anomaly F1",
        value: isNil(anomalyModel.f1) ? "-" : Number(anomalyModel.f1).toFixed(4),
        tone: "blue", sub: "held-out test set"
      })
    ].join(""));

    // ---- anomaly gauge ----
    var pct = probability === null ? 0 : Math.max(0, Math.min(1, probability));
    var circumference = 2 * Math.PI * 52;
    var fill = $("gauge-fill");
    if (fill) {
      fill.style.strokeDasharray = String(circumference);
      fill.style.strokeDashoffset = String(circumference * (1 - pct));
      fill.style.stroke = prediction.anomaly_flag ? Charts.palette.red
        : (pct >= state.threshold * 0.6 ? Charts.palette.amber : Charts.palette.green);
    }
    setText("gauge-value-text", probability === null ? "-" : (probability * 100).toFixed(1) + "%");
    var chip = $("analytics-anomaly-chip");
    if (chip) {
      chip.className = "chip " + (prediction.anomaly_flag ? "chip-bad" : "chip-ok");
      chip.textContent = probability === null ? "no score" : (prediction.anomaly_flag ? "flagged" : "clear");
    }
    setHTML("analytics-anomaly-notes", listItems([
      "Threshold: " + state.threshold.toFixed(2),
      "Model: " + (prediction.model_version || "unknown"),
      "Trained on: " + datasetLabel(prediction.model_trained_on),
      "Degraded inputs: " + ((prediction.degraded_inputs && prediction.degraded_inputs.length)
        ? prediction.degraded_inputs.join(", ") : "none")
    ]));

    // ---- actual vs predicted ----
    var ordered = (series || []).slice();
    Charts.line("chart-analytics-trend", {
      labels: ordered.map(function (row) { return clockTime(row.reading_timestamp); }),
      series: [
        {
          label: "Actual (Live / Test)",
          data: ordered.map(function (row) { return row.actual_power_w === null ? null : number(row.actual_power_w); }),
          color: Charts.palette.amber, points: false
        },
        {
          label: "Predicted",
          data: ordered.map(function (row) { return number(row.predicted_power_w); }),
          color: Charts.palette.green, dashed: true, points: false
        }
      ],
      yTitle: "W", legend: true
    });

    // ---- feature importance ----
    var top = (importance || []).slice(0, 10).reverse();
    Charts.bar("chart-analytics-importance", {
      labels: top.map(function (item) { return item.feature; }),
      values: top.map(function (item) { return number(item.importance) || 0; }),
      color: Charts.palette.green,
      horizontal: true
    });

    // ---- condition class scores ----
    var probabilities = prediction.condition_probabilities || {};
    var classLabels = Object.keys(probabilities);
    Charts.bar("chart-analytics-classes", {
      labels: classLabels.map(titleCase),
      values: classLabels.map(function (label) { return number(probabilities[label]) || 0; }),
      color: Charts.palette.amber,
      horizontal: false
    });

    renderAnomalyTable(series);
  }

  function renderAnomalyTable(series) {
    var flagged = (series || []).filter(function (row) { return Number(row.anomaly_flag) === 1; })
      .slice(-25).reverse();
    setText("analytics-anomaly-count", flagged.length + " flagged");
    var body = $("table-anomalies").querySelector("tbody");
    if (!flagged.length) {
      body.innerHTML = '<tr><td class="table-empty" colspan="6">No anomalies flagged in the recent window.</td></tr>';
      return;
    }
    body.innerHTML = flagged.map(function (row) {
      return "<tr>"
        + "<td>" + esc(fullTime(row.reading_timestamp)) + "</td>"
        + "<td>" + esc(row.device_id || "-") + "</td>"
        + "<td>" + originBadge(row.data_origin) + "</td>"
        + "<td>" + esc(titleCase(row.predicted_condition)) + "</td>"
        + '<td class="tone-red">' + (Number(row.anomaly_probability) * 100).toFixed(1) + "%</td>"
        + '<td class="tone-red">flagged</td>'
        + "</tr>";
    }).join("");
  }

  function renderStaticFigures() {
    setHTML("static-figures", STATIC_FIGURES.map(function (pair) {
      return '<figure class="figure-card"><img loading="lazy" src="/reports/graphs/' + pair[0]
        + '" alt="' + esc(pair[1]) + '" /><figcaption>' + esc(pair[1]) + "</figcaption></figure>";
    }).join(""));
  }

  // ---------------------------------------------------------------------- //
  // D. Energy optimisation
  // ---------------------------------------------------------------------- //
  function refreshOptimization() {
    return API.optimization().then(function (result) {
      clearError();
      renderOptimization(result);
    }).catch(function (error) {
      reportError("Could not load the optimisation view", error);
    });
  }

  function renderOptimization(result) {
    var status = result.status;
    var chip = $("optimization-status-chip");
    if (chip) {
      chip.className = "chip " + (status === "surplus" ? "chip-ok"
        : status === "deficit" ? "chip-bad" : status === "balanced" ? "chip-warn" : "chip-quiet");
      chip.textContent = titleCase(status);
    }

    var allocation = result.allocation || {};
    var labels = ["Critical load", "Deferrable load", "Storage", "Reserve", "Deficit"];
    var keys = ["critical_load_w", "deferrable_load_w", "storage_charge_w", "reserve_held_w", "deficit_w"];
    var colors = [Charts.palette.green, Charts.palette.amber, Charts.palette.blue, Charts.palette.purple, Charts.palette.red];
    var values = keys.map(function (key) { return number(allocation[key]) || 0; });
    var hasValues = keys.some(function (key) { return !isNil(allocation[key]); });

    Charts.doughnut("chart-optimization-alloc", {
      labels: hasValues ? labels : [],
      values: hasValues ? values : [],
      colors: colors,
      emptyLabel: "no allocated power"
    });
    setHTML("optimization-legend", hasValues
      ? labels.map(function (label, index) {
        return legendItem(label, colors[index], numericCell(allocation[keys[index]], 3, "W"));
      }).join("")
      : '<span class="legend-item is-null">No measured generation to allocate.</span>');

    var reading = (state.latest && state.latest.reading) || {};
    Charts.doughnut("chart-optimization-source", {
      labels: ["Solar", "Wind"],
      values: [number(reading.solar_power) || 0, number(reading.wind_power) || 0],
      colors: [Charts.palette.green, Charts.palette.amber],
      emptyLabel: "no measurable power"
    });
    setHTML("optimization-source-legend",
      legendItem("Solar", Charts.palette.green, numericCell(reading.solar_power, 3, "W"))
      + legendItem("Wind", Charts.palette.amber, numericCell(reading.wind_power, 3, "W")));

    setHTML("optimization-recommendations", (result.recommendations || []).map(function (text) {
      return "<li>" + esc(text) + "</li>";
    }).join("") || "<li>No recommendations this cycle.</li>");

    var relay = result.relay || {};
    setHTML("optimization-relay", [
      detailRow("Relay control", relay.enabled
        ? '<span class="tone-amber">enabled</span>'
        : '<span class="tone-green">disabled (safe default)</span>'),
      detailRow("Action", esc(relay.action || "hold")),
      detailRow("Measured generation", numericCell(result.generation_w, 3, "W")),
      detailRow("Predicted generation", numericCell(result.predicted_generation_w, 3, "W")),
      detailRow("Reason", '<span class="is-null">' + esc(relay.reason || "-") + "</span>")
    ].join(""));

    setHTML("optimization-assumptions", listItems(result.assumptions || []));
  }

  // ---------------------------------------------------------------------- //
  // E. Historical data
  // ---------------------------------------------------------------------- //
  function refreshHistory() {
    var hoursValue = $("history-hours").value;
    var params = {
      limit: $("history-limit").value,
      device_id: $("history-device").value || undefined
    };
    if (hoursValue !== "all") { params.hours = hoursValue; }

    return API.history(params).then(function (rows) {
      clearError();
      var origin = $("history-origin").value;
      state.history = (rows || []).filter(function (row) {
        return !origin || row.data_origin === origin;
      });
      state.historyPage = 1;
      renderHistoryCharts(state.history);
      renderHistoryTable();
    }).catch(function (error) {
      reportError("Could not load history", error);
    });
  }

  function renderHistoryCharts(rows) {
    var points = rows.slice(0, 600).reverse();
    var labels = points.map(function (row) { return clockSeconds(row.timestamp); });

    Charts.line("chart-history-generation", {
      labels: labels,
      series: [{
        label: "Total estimated power (W)",
        data: points.map(function (r) { return number(r.total_est_power_w); }),
        color: Charts.palette.green, fill: true, points: false
      }],
      yTitle: "W", legend: false
    });

    Charts.line("chart-history-voltage", {
      labels: labels,
      series: [
        { label: "Solar voltage (V)", data: points.map(function (r) { return number(r.solar_voltage); }), color: Charts.palette.green },
        { label: "Wind voltage (V)", data: points.map(function (r) { return number(r.wind_voltage); }), color: Charts.palette.blue }
      ],
      yTitle: "V", legend: true
    });

    Charts.line("chart-history-climate", {
      labels: labels,
      series: [
        { label: "Temperature (\u00b0C)", data: points.map(function (r) { return number(r.temperature_c); }), color: Charts.palette.amber },
        { label: "Humidity (%)", data: points.map(function (r) { return number(r.humidity_percent); }), color: Charts.palette.blue, yAxisID: "y1", dashed: true, points: false }
      ],
      yTitle: "\u00b0C", y2Title: "%", legend: true
    });

    Charts.line("chart-history-rpm", {
      labels: labels,
      series: [{
        label: "Turbine speed (RPM)",
        data: points.map(function (r) { return number(r.turbine_rpm); }),
        color: Charts.palette.purple, points: false
      }],
      yTitle: "RPM", legend: false
    });
  }

  function renderHistoryTable() {
    var rows = state.history;
    var total = rows.length;
    var pages = Math.max(1, Math.ceil(total / state.pageSize));
    state.historyPage = Math.min(state.historyPage, pages);
    var start = (state.historyPage - 1) * state.pageSize;
    var pageRows = rows.slice(start, start + state.pageSize);

    setText("history-count", total + " rows");

    var body = $("table-history").querySelector("tbody");
    if (!total) {
      body.innerHTML = '<tr><td class="table-empty" colspan="11">No readings match these filters.</td></tr>';
    } else {
      body.innerHTML = pageRows.map(function (row) {
        return "<tr>"
          + "<td>" + esc(fullTime(row.timestamp)) + "</td>"
          + "<td>" + esc(row.device_id || "-") + "</td>"
          + "<td>" + originBadge(row.data_origin) + "</td>"
          + "<td>" + numericCell(row.solar_voltage, 2, "") + "</td>"
          + "<td>" + numericCell(row.solar_current, 3, "") + "</td>"
          + "<td>" + numericCell(row.wind_voltage, 2, "") + "</td>"
          + "<td>" + numericCell(row.wind_current, 3, "") + "</td>"
          + "<td>" + numericCell(row.turbine_rpm, 0, "") + "</td>"
          + "<td>" + numericCell(row.temperature_c, 1, "") + "</td>"
          + "<td>" + numericCell(row.humidity_percent, 0, "") + "</td>"
          + "<td>" + esc(titleCase(row.light_status || "-")) + "</td>"
          + "</tr>";
      }).join("");
    }

    setText("page-info", "page " + state.historyPage + " of " + pages);
    $("page-prev").disabled = state.historyPage <= 1;
    $("page-next").disabled = state.historyPage >= pages;
  }

  function loadDeviceFilter() {
    return API.devices().then(function (devices) {
      var select = $("history-device");
      var current = select.value;
      select.innerHTML = '<option value="">All devices</option>' + (devices || []).map(function (device) {
        return '<option value="' + esc(device.device_id) + '">' + esc(device.device_id)
          + (device.online ? " (online)" : "") + "</option>";
      }).join("");
      select.value = current;
    }).catch(function () { /* the filter is non-critical */ });
  }

  // ---------------------------------------------------------------------- //
  // F. Model & system status
  // ---------------------------------------------------------------------- //
  function refreshModel() {
    return Promise.all([API.modelStatus(), API.devices(), API.stats()])
      .then(function (results) {
        clearError();
        renderModel(results[0] || {}, results[1] || [], results[2] || {});
      }).catch(function (error) {
        reportError("Could not load model status", error);
      });
  }

  function renderModel(status, devices, stats) {
    var generation = (status.models || {}).generation || {};
    var conditionModel = (status.models || {}).condition || {};
    var anomalyModel = (status.models || {}).anomaly || {};

    setHTML("model-kpis", [
      kpiCard({ label: "Model version", value: esc(status.model_version || "-"), tone: "blue",
        sub: status.ready ? "loaded" : (status.last_error ? "load error" : "not loaded") }),
      kpiCard({ label: "Training rows", value: esc(String(status.trained_on_rows || 0)),
        tone: "green", sub: "chronological split " + esc(status.split_strategy || "") }),
      kpiCard({ label: "Test rows", value: esc(String(status.test_rows || 0)),
        sub: (status.validation_rows || 0) + " validation rows" }),
      kpiCard({ label: "Generation R\u00b2", value: isNil(generation.r2) ? "-" : Number(generation.r2).toFixed(4), tone: "blue", sub: "test set" }),
      kpiCard({ label: "Condition macro-F1", value: isNil(conditionModel.f1_macro) ? "-" : Number(conditionModel.f1_macro).toFixed(4), tone: "blue", sub: "test set" }),
      kpiCard({ label: "Anomaly F1", value: isNil(anomalyModel.f1) ? "-" : Number(anomalyModel.f1).toFixed(4), tone: "blue", sub: "test set" })
    ].join(""));

    setHTML("model-training-detail", [
      detailRow("Model version", esc(status.model_version || "-")),
      detailRow("Trained at", esc(status.trained_at_unix
        ? fullTime(new Date(status.trained_at_unix * 1000).toISOString()) : "-")),
      detailRow("Training data", esc(datasetLabel(status.training_data_origin))),
      detailRow("Split strategy", esc(status.split_strategy || "-")),
      detailRow("Train / val / test", esc((status.trained_on_rows || 0) + " / "
        + (status.validation_rows || 0) + " / " + (status.test_rows || 0))),
      detailRow("Anomaly rate (train)", isNil(status.anomaly_rate_training) ? "-"
        : esc((status.anomaly_rate_training * 100).toFixed(2) + " %")),
      detailRow("Features", esc(String((status.feature_columns || []).length))),
      detailRow("Loaded", esc(humanDuration(status.seconds_since_load) || "-") + " ago")
    ].join(""));

    var perClass = conditionModel.per_class || {};
    var perClassList = Object.keys(perClass).map(function (label) {
      var stats_ = perClass[label];
      return esc(titleCase(label)) + ": P " + (stats_.precision * 100).toFixed(1)
        + "% \u00b7 R " + (stats_.recall * 100).toFixed(1)
        + "% \u00b7 F1 " + (stats_.f1 * 100).toFixed(1)
        + "% \u00b7 n=" + stats_.support;
    });

    setHTML("model-metrics-detail", [
      detailRow("Generation MAE", numericCell(generation.mae, 4, "W")),
      detailRow("Generation RMSE", numericCell(generation.rmse, 4, "W")),
      detailRow("Generation R\u00b2", isNil(generation.r2) ? '<span class="is-null">-</span>' : esc(Number(generation.r2).toFixed(4))),
      detailRow("Condition accuracy", isNil(conditionModel.accuracy) ? "-" : esc((conditionModel.accuracy * 100).toFixed(2) + " %")),
      detailRow("Condition macro-F1", isNil(conditionModel.f1_macro) ? "-" : esc(Number(conditionModel.f1_macro).toFixed(4))),
      detailRow("Anomaly precision", isNil(anomalyModel.precision) ? "-" : esc((anomalyModel.precision * 100).toFixed(2) + " %")),
      detailRow("Anomaly recall", isNil(anomalyModel.recall) ? "-" : esc((anomalyModel.recall * 100).toFixed(2) + " %"))
    ].join("") + (perClassList.length
      ? '<h3 class="mini-head">Condition classes</h3><ul class="mini-list">'
        + perClassList.map(function (item) { return "<li>" + item + "</li>"; }).join("") + "</ul>"
      : ""));

    var matrix = anomalyModel.confusion_matrix || [[0, 0], [0, 0]];
    Charts.groupedBar("chart-model-confusion", {
      labels: ["Actual normal", "Actual anomaly"],
      datasets: [
        { label: "Predicted normal", data: [matrix[0][0], matrix[1][0]], color: Charts.palette.green },
        { label: "Predicted anomaly", data: [matrix[0][1], matrix[1][1]], color: Charts.palette.red }
      ],
      yTitle: "rows"
    });

    setHTML("model-system-detail", [
      detailRow("Models ready", status.ready
        ? '<span class="tone-green">yes</span>'
        : '<span class="tone-red">no</span>'),
      detailRow("Last error", status.last_error
        ? '<span class="tone-red">' + esc(status.last_error) + "</span>"
        : '<span class="tone-green">none</span>'),
      detailRow("Readings stored", esc(String(stats.total_readings || 0))),
      detailRow("Live readings", esc(String((stats.data_origin_counts || {}).hardware || 0))),
      detailRow("Test readings", esc(String((stats.data_origin_counts || {}).simulated || 0))),
      detailRow("First reading", esc(stats.first_timestamp ? fullTime(stats.first_timestamp) : "-")),
      detailRow("Latest reading", esc(stats.last_timestamp ? fullTime(stats.last_timestamp) : "-"))
    ].join(""));

    setText("model-device-count", (devices || []).length);
    var body = $("table-devices").querySelector("tbody");
    if (!devices || !devices.length) {
      body.innerHTML = '<tr><td class="table-empty" colspan="6">No devices have reported yet.</td></tr>';
    } else {
      body.innerHTML = devices.map(function (device) {
        return "<tr>"
          + "<td>" + esc(device.device_id) + "</td>"
          + "<td>" + (device.online
            ? '<span class="tone-green">online</span>'
            : '<span class="tone-amber">offline</span>') + "</td>"
          + "<td>" + esc(humanDuration(device.seconds_since_last_seen) + " ago") + "</td>"
          + "<td>" + esc(device.last_ip || "-") + "</td>"
          + "<td>" + esc(device.last_sensor_status || "-") + "</td>"
          + "<td>" + esc(String(device.total_readings)) + "</td>"
          + "</tr>";
      }).join("");
    }

    setHTML("model-limitations", listItems(status.limitations || [
      "No model metadata available yet."
    ]));
  }

  // ---------------------------------------------------------------------- //
  // G. Settings
  // ---------------------------------------------------------------------- //
  function loadSettings() {
    return API.settings().then(function (settings) {
      clearError();
      var form = $("settings-form");
      Object.keys(settings).forEach(function (key) {
        var field = form.elements[key];
        if (!field) { return; }
        if (field.type === "checkbox") {
          field.checked = Number(settings[key]) === 1;
        } else if (key === "device_token") {
          field.value = "";
          field.placeholder = settings.device_token ? "*** (set)" : "no token set";
        } else {
          field.value = settings[key] === null || settings[key] === undefined ? "" : settings[key];
        }
      });
      if (!isNil(settings.anomaly_threshold)) {
        state.threshold = Number(settings.anomaly_threshold);
        $("analytics-threshold").value = state.threshold;
      }
    }).catch(function (error) {
      reportError("Could not load settings", error);
    });
  }

  function saveSettings() {
    var form = $("settings-form");
    var payload = {
      sampling_interval_s: Number(form.elements.sampling_interval_s.value),
      dashboard_refresh_s: Number(form.elements.dashboard_refresh_s.value),
      history_refresh_s: Number(form.elements.history_refresh_s.value),
      history_window_h: Number(form.elements.history_window_h.value),
      anomaly_threshold: Number(form.elements.anomaly_threshold.value),
      device_offline_after_s: Number(form.elements.device_offline_after_s.value),
      default_device_id: form.elements.default_device_id.value,
      optimize_load_low_w: Number(form.elements.optimize_load_low_w.value),
      optimize_load_high_w: Number(form.elements.optimize_load_high_w.value),
      optimize_reserve_w: Number(form.elements.optimize_reserve_w.value),
      demo_mode: form.elements.demo_mode.checked ? 1 : 0,
      relay_control_enabled: form.elements.relay_control_enabled.checked ? 1 : 0,
      backend_url: form.elements.backend_url.value
    };
    var token = form.elements.device_token.value.trim();
    if (token && token !== "***") { payload.device_token = token; }

    var button = $("btn-save-settings");
    button.disabled = true;
    return API.saveSettings(payload).then(function () {
      button.disabled = false;
      notify("Settings saved.", "ok");
      state.threshold = Number(payload.anomaly_threshold);
      restartOverviewLoop();
      return loadSettings();
    }).catch(function (error) {
      button.disabled = false;
      notify("Settings rejected: " + error.message, "bad");
      reportError("Settings not saved", error);
    });
  }

  // ---------------------------------------------------------------------- //
  // Navigation
  // ---------------------------------------------------------------------- //
  function navigate(section) {
    if (!SECTIONS[section]) { return; }
    state.section = section;
    stopAllLoops();

    document.querySelectorAll(".nav-item").forEach(function (item) {
      item.classList.toggle("is-active", item.getAttribute("data-section") === section);
    });
    document.querySelectorAll(".section").forEach(function (node) {
      node.classList.toggle("is-active", node.id === "section-" + section);
    });
    setText("page-title", SECTIONS[section].title);
    setText("page-subtitle", SECTIONS[section].subtitle);

    var sidebar = $("sidebar");
    if (sidebar) { sidebar.classList.remove("is-open"); }

    var modelStatus = state.modelStatus;

    switch (section) {
      case "overview":
        restartOverviewLoop();
        break;
      case "live":
        startLoop("live", Number($("live-interval").value) * 1000, state.livePaused ? function () {} : refreshLive);
        break;
      case "analytics":
        refreshAnalytics();
        startLoop("analytics", 15000, refreshAnalytics);
        break;
      case "optimization":
        refreshOptimization();
        startLoop("optimization", 15000, refreshOptimization);
        break;
      case "history":
        loadDeviceFilter();
        startLoop("history", 30000, refreshHistory);
        break;
      case "model":
        refreshModel();
        startLoop("model", 30000, refreshModel);
        break;
      case "settings":
        loadSettings();
        break;
      default:
        break;
    }
    void modelStatus;
  }

  function restartOverviewLoop() {
    stopLoop("overview");
    var seconds = 5;
    if (state.latest && state.latest.settings && state.latest.settings.dashboard_refresh_s) {
      seconds = Number(state.latest.settings.dashboard_refresh_s);
    }
    state.loops.overview = setInterval(refreshOverview, Math.max(2000, seconds * 1000));
  }

  // ---------------------------------------------------------------------- //
  // Test / Live mode
  // ---------------------------------------------------------------------- //
  var MODE_KEY = "microgrid.dataMode";

  function applyModeUi() {
    var mode = state.dataMode === "live" ? "live" : "test";
    var test = $("mode-test");
    var live = $("mode-live");
    if (test) { test.classList.toggle("is-active", mode === "test"); }
    if (live) { live.classList.toggle("is-active", mode === "live"); }
  }

  function setMode(mode, options) {
    state.dataMode = (mode === "live") ? "live" : "test";
    try { localStorage.setItem(MODE_KEY, state.dataMode); } catch (err) { /* ignore */ }
    applyModeUi();

    var select = $("history-origin");
    if (select && !(options && options.keepFilter)) {
      select.value = state.dataMode === "live" ? "hardware" : "simulated";
    }

    var request = state.dataMode === "live" ? API.demoStop() : API.demoStart();
    request.then(function () {
      notify(state.dataMode === "live"
        ? "Live mode: showing readings reported by the node."
        : "Test mode: replaying sample telemetry.", "ok");
    }).catch(function (error) {
      reportError("Could not switch to " + state.dataMode + " mode", error);
    });

    refreshOverview();
    if (state.section === "history") { refreshHistory(); }
  }

  // ---------------------------------------------------------------------- //
  // Wiring
  // ---------------------------------------------------------------------- //
  function bind() {
    document.querySelectorAll(".nav-item").forEach(function (item) {
      item.addEventListener("click", function () {
        navigate(item.getAttribute("data-section"));
        location.hash = item.getAttribute("data-section");
      });
    });

    var toggle = $("menu-toggle");
    if (toggle) {
      toggle.addEventListener("click", function () {
        var sidebar = $("sidebar");
        var open = sidebar.classList.toggle("is-open");
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
      });
    }

    ["mode-test", "mode-live"].forEach(function (id) {
      var node = $(id);
      if (node) {
        node.addEventListener("click", function () {
          var target = node.getAttribute("data-mode");
          if (state.dataMode !== target) { setMode(target); }
        });
      }
    });

    $("btn-refresh").addEventListener("click", function () {
      notify("Refreshing\u2026", "ok");
      refreshOverview();
      if (state.section === "live") { refreshLive(); }
      if (state.section === "analytics") { refreshAnalytics(); }
      if (state.section === "optimization") { refreshOptimization(); }
      if (state.section === "model") { refreshModel(); }
      if (state.section === "history") { refreshHistory(); }
    });

    $("live-interval").addEventListener("change", function () {
      if (state.section === "live") {
        startLoop("live", Number($("live-interval").value) * 1000, refreshLive);
      }
    });

    $("btn-live-pause").addEventListener("click", function (event) {
      state.livePaused = !state.livePaused;
      event.currentTarget.textContent = state.livePaused ? "Resume" : "Pause";
      if (state.livePaused) { stopLoop("live"); } else { refreshLive(); navigate("live"); }
    });

    $("btn-run-prediction").addEventListener("click", function () {
      API.predict({ use_latest: true, anomaly_threshold: state.threshold }).then(function (result) {
        notify("Prediction refreshed: " + titleCase(result.predicted_condition), "ok");
        refreshAnalytics();
      }).catch(function (error) {
        notify("Prediction failed: " + error.message, "bad");
      });
    });

    $("btn-apply-threshold").addEventListener("click", function () {
      var value = Number($("analytics-threshold").value);
      if (!isFinite(value) || value <= 0 || value >= 1) {
        notify("Threshold must be between 0 and 1.", "warn");
        return;
      }
      state.threshold = value;
      API.saveSettings({ anomaly_threshold: value }).then(function () {
        notify("Anomaly threshold set to " + value.toFixed(2), "ok");
        refreshAnalytics();
      }).catch(function (error) {
        notify("Could not save threshold: " + error.message, "bad");
      });
    });

    $("btn-model-reload").addEventListener("click", function () {
      refreshModel().then(function () { notify("Model status refreshed.", "ok"); });
    });

    $("btn-history-load").addEventListener("click", function () { refreshHistory(); });
    ["history-hours", "history-origin", "history-limit", "history-device"].forEach(function (id) {
      $(id).addEventListener("change", function () { refreshHistory(); });
    });
    $("page-prev").addEventListener("click", function () {
      state.historyPage = Math.max(1, state.historyPage - 1);
      renderHistoryTable();
    });
    $("page-next").addEventListener("click", function () {
      state.historyPage = state.historyPage + 1;
      renderHistoryTable();
    });

    $("btn-save-settings").addEventListener("click", function (event) {
      event.preventDefault();
      saveSettings();
    });
    $("settings-form").addEventListener("submit", function (event) {
      event.preventDefault();
      saveSettings();
    });

    window.addEventListener("hashchange", function () {
      var target = location.hash.replace("#", "");
      if (target && SECTIONS[target] && target !== state.section) { navigate(target); }
    });
  }

  function boot() {
    if (!API) { return; }
    if (!Charts.available) {
      notify("Chart library failed to load; numbers still update.", "warn");
    }
    renderStaticFigures();
    bind();

    var saved = "test";
    try { saved = localStorage.getItem(MODE_KEY) || "test"; } catch (err) { /* ignore */ }
    state.dataMode = saved === "live" ? "live" : "test";
    applyModeUi();

    loadSettings().then(function () {
      var start = location.hash.replace("#", "");
      navigate(SECTIONS[start] ? start : "overview");
      setMode(state.dataMode, { keepFilter: true });
    });

    // The overview loop keeps the header pills and sidebar current from any tab.
    refreshOverview().then(restartOverviewLoop).catch(restartOverviewLoop);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
