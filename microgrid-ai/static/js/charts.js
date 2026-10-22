/* ==========================================================================
   charts.js - a small themed wrapper over Chart.js.
   Every chart is created once and then updated in place so the 5-second
   refresh does not flash.  All colours come from the same palette as the CSS.
   ========================================================================== */
(function () {
  "use strict";

  var CHART = window.Chart;
  if (!CHART) {
    window.MicrogridCharts = { available: false, line: noop, doughnut: noop, bar: noop, groupedBar: noop, destroyAll: noop };
    return;
  }

  var palette = {
    green: "#2ECC71",
    greenDim: "#1F9E56",
    amber: "#F5A623",
    amberDim: "#C6821A",
    red: "#FF5C5C",
    blue: "#5AA9E6",
    purple: "#A78BFA",
    muted: "#8B949E",
    mutedDim: "#4A525C"
  };

  CHART.defaults.color = palette.muted;
  CHART.defaults.font.family = '"Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';
  CHART.defaults.font.size = 11;
  CHART.defaults.borderColor = "#2A323C";
  CHART.defaults.plugins.legend.display = false;

  var registry = {};

  function hexA(hex, alpha) {
    var value = hex.replace("#", "");
    if (value.length === 3) {
      value = value.split("").map(function (c) { return c + c; }).join("");
    }
    var r = parseInt(value.substring(0, 2), 16);
    var g = parseInt(value.substring(2, 4), 16);
    var b = parseInt(value.substring(4, 6), 16);
    return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
  }

  function tooltipStyle() {
    return {
      backgroundColor: "#20262F",
      borderColor: "#2A323C",
      borderWidth: 1,
      titleColor: "#E6EDF3",
      bodyColor: "#B9C2CC",
      padding: 10,
      cornerRadius: 8,
      boxPadding: 4,
      displayColors: true,
      usePointStyle: true
    };
  }

  function baseScales(opts) {
    opts = opts || {};
    var x = {
      grid: { color: "rgba(255,255,255,0.045)", drawTicks: false },
      border: { color: "#2A323C" },
      ticks: {
        color: palette.muted, font: { size: 10 }, maxRotation: 0,
        autoSkip: true, maxTicksLimit: 7, padding: 4
      }
    };
    var y = {
      beginAtZero: opts.beginAtZero !== false,
      position: "left",
      grid: { color: "rgba(255,255,255,0.05)", drawTicks: false },
      border: { display: false },
      ticks: { color: palette.muted, font: { size: 10 }, padding: 6 }
    };
    if (opts.yTitle) {
      y.title = { display: true, text: opts.yTitle, color: "#6B7480", font: { size: 10 } };
    }
    if (opts.yMax !== undefined) { y.max = opts.yMax; }
    if (opts.yMin !== undefined) { y.min = opts.yMin; }
    var scales = { x: x, y: y };
    if (opts.y2Title) {
      scales.y1 = {
        beginAtZero: true,
        position: "right",
        grid: { display: false },
        border: { display: false },
        ticks: { color: palette.muted, font: { size: 10 }, padding: 6 },
        title: { display: true, text: opts.y2Title, color: "#6B7480", font: { size: 10 } }
      };
    }
    return scales;
  }

  function baseOptions(opts) {
    opts = opts || {};
    var options = {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 340, easing: "easeOutQuart" },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          display: !!opts.legend,
          position: "top",
          align: "end",
          labels: {
            color: palette.muted,
            boxWidth: 10,
            boxHeight: 10,
            usePointStyle: true,
            pointStyle: "rectRounded",
            padding: 12,
            font: { size: 11 }
          }
        },
        tooltip: tooltipStyle()
      }
    };
    if (opts.horizontal) {
      options.indexAxis = "y";
      options.interaction = { mode: "nearest", axis: "y", intersect: false };
      options.scales = {
        x: {
          beginAtZero: true,
          grid: { color: "rgba(255,255,255,0.05)", drawTicks: false },
          border: { display: false },
          ticks: { color: palette.muted, font: { size: 10 }, padding: 6 }
        },
        y: {
          grid: { display: false },
          border: { color: "#2A323C" },
          ticks: { color: palette.muted, font: { size: 10 }, padding: 6 }
        }
      };
    } else {
      options.scales = baseScales(opts);
    }
    return options;
  }

  function render(canvasId, spec, animate) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) { return null; }

    var existing = registry[canvasId];
    if (existing && existing.config.type === spec.type) {
      existing.data = spec.data;
      if (spec.options) {
        existing.options = spec.options;
      }
      existing.update(animate === false ? "none" : "active");
      return existing;
    }
    if (existing) { existing.destroy(); }

    var chart = new CHART(canvas.getContext("2d"), {
      type: spec.type,
      data: spec.data,
      options: spec.options
    });
    registry[canvasId] = chart;
    return chart;
  }

  function lineSeries(entry) {
    return {
      label: entry.label,
      data: entry.data,
      borderColor: entry.color,
      backgroundColor: entry.fill ? hexA(entry.color, 0.13) : entry.color,
      borderWidth: entry.width || 2,
      pointRadius: entry.points === false ? 0 : 2,
      pointHoverRadius: 4,
      pointBackgroundColor: entry.color,
      pointBorderColor: entry.color,
      tension: 0.32,
      fill: entry.fill || false,
      spanGaps: true,
      yAxisID: entry.yAxisID || "y",
      borderDash: entry.dashed ? [5, 4] : undefined
    };
  }

  function line(canvasId, config) {
    config = config || {};
    var datasets = (config.series || []).map(lineSeries);
    var options = baseOptions({
      yTitle: config.yTitle,
      y2Title: config.y2Title,
      yMax: config.yMax,
      yMin: config.yMin,
      beginAtZero: config.beginAtZero,
      legend: config.legend !== undefined ? config.legend : (datasets.length > 1)
    });
    return render(canvasId, {
      type: "line",
      data: { labels: config.labels || [], datasets: datasets },
      options: options
    }, config.animate);
  }

  function doughnut(canvasId, config) {
    config = config || {};
    var labels = config.labels || [];
    var values = config.values || [];
    var colors = config.colors || [];
    var total = values.reduce(function (sum, value) {
      return sum + (Number(value) || 0);
    }, 0);

    var data;
    if (!labels.length || total <= 0) {
      data = {
        labels: [config.emptyLabel || "no measurable value"],
        datasets: [{
          data: [1],
          backgroundColor: [hexA(palette.mutedDim, 0.55)],
          borderColor: ["#161B22"],
          borderWidth: 2
        }]
      };
    } else {
      data = {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: colors,
          borderColor: "#161B22",
          borderWidth: 2,
          hoverOffset: 5
        }]
      };
    }

    var options = {
      responsive: true,
      maintainAspectRatio: false,
      cutout: config.cutout || "62%",
      animation: { duration: 340, easing: "easeOutQuart" },
      plugins: {
        legend: { display: false },
        tooltip: Object.assign(tooltipStyle(), {
          callbacks: {
            label: function (ctx) {
              var value = Number(ctx.parsed) || 0;
              if (total <= 0) { return " no measurable value"; }
              var pct = total ? (value / total * 100) : 0;
              return " " + ctx.label + ": " + value.toFixed(3) + " W (" + pct.toFixed(1) + "%)";
            }
          }
        })
      }
    };
    return render(canvasId, { type: "doughnut", data: data, options: options }, config.animate);
  }

  function bar(canvasId, config) {
    config = config || {};
    var horizontal = !!config.horizontal;
    var color = config.color || palette.green;
    var values = config.values || [];
    var max = values.length ? Math.max.apply(null, values) : 0;

    var data = {
      labels: config.labels || [],
      datasets: [{
        label: config.label || "",
        data: values,
        backgroundColor: values.map(function (value) {
          var ratio = max > 0 ? (Number(value) / max) : 0;
          return hexA(color, 0.32 + 0.55 * Math.max(0, Math.min(1, ratio)));
        }),
        borderColor: hexA(color, 0.85),
        borderWidth: 1,
        borderRadius: 5,
        maxBarThickness: horizontal ? 16 : 46
      }]
    };
    var options = baseOptions({
      horizontal: horizontal,
      legend: false,
      beginAtZero: true
    });
    return render(canvasId, { type: "bar", data: data, options: options }, config.animate);
  }

  function groupedBar(canvasId, config) {
    config = config || {};
    var colors = config.colors || [palette.green, palette.amber, palette.blue, palette.red];
    var datasets = (config.datasets || []).map(function (entry, index) {
      var color = entry.color || colors[index % colors.length];
      return {
        label: entry.label,
        data: entry.data,
        backgroundColor: hexA(color, 0.55),
        borderColor: color,
        borderWidth: 1,
        borderRadius: 5,
        maxBarThickness: config.horizontal ? 16 : 54
      };
    });

    var options = baseOptions({
      horizontal: config.horizontal,
      legend: true,
      beginAtZero: true,
      yTitle: config.yTitle
    });
    options.plugins.legend.display = true;
    if (config.stacked) {
      options.scales.x.stacked = true;
      options.scales.y.stacked = true;
    }
    return render(canvasId, {
      type: "bar",
      data: { labels: config.labels || [], datasets: datasets },
      options: options
    }, config.animate);
  }

  function destroyAll() {
    Object.keys(registry).forEach(function (key) {
      try { registry[key].destroy(); } catch (err) { /* already gone */ }
      delete registry[key];
    });
  }

  function noop() { return null; }

  window.MicrogridCharts = {
    available: true,
    palette: palette,
    hexA: hexA,
    line: line,
    doughnut: doughnut,
    bar: bar,
    groupedBar: groupedBar,
    destroyAll: destroyAll
  };
})();
