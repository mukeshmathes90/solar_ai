/* ==========================================================================
   api.js - thin client for the microgrid REST API.
   Every response uses the { status, data, error } envelope; this layer unwraps
   it, surfaces the server's error details, and never fabricates a value when a
   request fails.
   ========================================================================== */
(function () {
  "use strict";

  var DEFAULT_TIMEOUT = 12000;

  function ApiError(message, code, details, status) {
    this.name = "ApiError";
    this.message = message;
    this.code = code || "request_failed";
    this.details = details || [];
    this.status = status || 0;
  }
  ApiError.prototype = Object.create(Error.prototype);
  ApiError.prototype.constructor = ApiError;

  function withTimeout(url, options, timeout) {
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, timeout);
    options = options || {};
    options.signal = controller.signal;
    return fetch(url, options).finally(function () { clearTimeout(timer); });
  }

  function request(path, options) {
    options = options || {};
    var timeout = options.timeout || DEFAULT_TIMEOUT;
    var init = { method: options.method || "GET", headers: {} };
    if (options.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.body);
    }
    return withTimeout(path, init, timeout).then(function (response) {
      return response.text().then(function (text) {
        var payload = null;
        if (text) {
          try { payload = JSON.parse(text); } catch (err) { payload = null; }
        }
        if (!response.ok) {
          var envelope = (payload && payload.error) || {};
          throw new ApiError(
            envelope.message || ("Request failed with HTTP " + response.status),
            envelope.code || "http_" + response.status,
            envelope.details || [],
            response.status
          );
        }
        if (payload && payload.status === "error") {
          throw new ApiError(
            (payload.error && payload.error.message) || "Server reported an error",
            (payload.error && payload.error.code) || "server_error",
            (payload.error && payload.error.details) || [],
            response.status
          );
        }
        return payload ? payload.data : null;
      });
    }, function (err) {
      if (err && err.name === "AbortError") {
        throw new ApiError("Request timed out after " + timeout + " ms.", "timeout");
      }
      throw new ApiError("Cannot reach the backend: " + (err && err.message), "network");
    });
  }

  window.MicrogridAPI = {
    ApiError: ApiError,
    health:        function () { return request("/api/health"); },
    overview:      function () { return request("/api/overview"); },
    latest:        function (deviceId) {
      var q = deviceId ? ("?device_id=" + encodeURIComponent(deviceId)) : "";
      return request("/api/readings/latest" + q);
    },
    history: function (params) {
      var query = [];
      Object.keys(params || {}).forEach(function (key) {
        var value = params[key];
        if (value !== undefined && value !== null && value !== "") {
          query.push(encodeURIComponent(key) + "=" + encodeURIComponent(value));
        }
      });
      return request("/api/readings/history" + (query.length ? "?" + query.join("&") : ""));
    },
    devices:       function () { return request("/api/devices"); },
    stats:         function () { return request("/api/stats"); },
    modelStatus:   function () { return request("/api/model/status"); },
    importance:    function () { return request("/api/model/importance"); },
    predict:       function (body) { return request("/api/predict", { method: "POST", body: body }); },
    predictions:   function (limit) { return request("/api/predictions/history?limit=" + (limit || 50)); },
    predictionSeries: function (limit) { return request("/api/predictions/series?limit=" + (limit || 300)); },
    optimization:  function () { return request("/api/optimization"); },
    settings:      function () { return request("/api/settings"); },
    saveSettings:  function (body) { return request("/api/settings", { method: "PUT", body: body }); },
    demoStatus:    function () { return request("/api/demo/status"); },
    demoStart:     function () { return request("/api/demo/start", { method: "POST", body: {} }); },
    demoStop:      function () { return request("/api/demo/stop", { method: "POST", body: {} }); },
    demoTick:      function () { return request("/api/demo/tick", { method: "POST", body: {} }); },
    demoSeed:      function (count, spacing) {
      return request("/api/demo/seed", { method: "POST", body: { count: count, spacing_seconds: spacing } });
    }
  };
})();
