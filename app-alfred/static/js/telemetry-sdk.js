(function () {
  if (!window.__TELEMETRY__) return;

  var cfg = window.__TELEMETRY__;
  var endpoint = (cfg.endpoint || "").trim();
  if (!endpoint) return;

  function getCookie(name) {
    var match = document.cookie.match(new RegExp("(?:^|; )" + name.replace(/([$()*+./?[\\]^{|}-])/g, "\\$1") + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : null;
  }

  function setCookie(name, value, days) {
    var expires = "";
    if (days) {
      var d = new Date();
      d.setTime(d.getTime() + days * 24 * 60 * 60 * 1000);
      expires = "; expires=" + d.toUTCString();
    }
    document.cookie = name + "=" + value + expires + "; path=/; SameSite=Lax";
  }

  var userId = cfg.userId == null ? null : Number(cfg.userId);
  var sessionId = getCookie("telemetry_session");
  if (!sessionId) {
    sessionId = (Math.random().toString(36).slice(2, 10) + Date.now().toString(36) + Math.random().toString(36).slice(2, 6)).replace(/[^a-zA-Z0-9]/g, "x");
    setCookie("telemetry_session", sessionId, 365);
  }

  var batch = [];
  var batchTimer = null;
  var MAX_BATCH = 20;
  var FLUSH_MS = 5000;
  var SCROLL_THROTTLE = 500;
  var lastScrollSend = 0;
  var depthsSent = {};
  var tabHidden = false;
  var startTs = Date.now();
  var sessionSeconds = 0;
  var rafPending = false;

  function serialize(data) {
    try { return JSON.stringify(data); } catch (e) { return null; }
  }

  function sendBeacon(payload) {
    if (!navigator.sendBeacon) {
      trySendXhr(payload);
      return;
    }
    var blob = new Blob([payload], { type: "application/json" });
    navigator.sendBeacon(endpoint, blob);
  }

  function trySendXhr(payload) {
    try {
      var xhr = new XMLHttpRequest();
      xhr.open("POST", endpoint, true);
      xhr.setRequestHeader("Content-Type", "application/json");
      xhr.send(payload);
    } catch (e) { /* swallow */ }
  }

  function flush(immediate) {
    if (batch.length === 0) return;
    var payload = serialize({ events: batch });
    if (!payload) { batch = []; return; }
    if (immediate || navigator.sendBeacon) {
      sendBeacon(payload);
    } else {
      trySendXhr(payload);
    }
    batch = [];
    if (batchTimer) { clearTimeout(batchTimer); batchTimer = null; }
  }

  function enqueue(event) {
    event.event_id = event.event_id || (Math.random().toString(36).slice(2, 10) + Date.now().toString(36) + Math.random().toString(36).slice(2, 6)).replace(/[^a-zA-Z0-9]/g, "x");
    event.user_id = event.user_id != null ? Number(event.user_id) : null;
    event.session_id = sessionId;
    batch.push(event);
    if (batch.length >= MAX_BATCH) {
      flush(true);
    } else if (!batchTimer) {
      batchTimer = setTimeout(function () { flush(true); }, FLUSH_MS);
    }
  }

  function track(type, props) {
    var evt = { event_type: type, url: location.href, referrer: document.referrer || null, properties: props || {}, timestamp: Date.now() };
    if (userId !== null) { evt.user_id = userId; }
    enqueue(evt);
  }

  function onIdle(callback) {
    if (window.requestIdleCallback) {
      window.requestIdleCallback(callback);
    } else if (window.requestAnimationFrame) {
      window.requestAnimationFrame(callback);
    } else {
      setTimeout(callback, 0);
    }
  }

  function pageView(isFirst) {
    var props = { title: document.title, path: location.pathname, is_first: !!isFirst };
    if (isFirst) {
      props.device_info = collectDevice();
      var now = Date.now();
      sessionSeconds = Math.floor((now - startTs) / 1000);
      track("session_start", props);
      if (userId !== null) {
        onIdle(function () { track("user_first_seen", { url: location.href, title: document.title }); });
      }
    } else {
      track("page_view", props);
    }
  }

  function collectDevice() {
    try {
      return {
        screen: (screen.width || 0) + "x" + (screen.height || 0),
        timezone: Intl && Intl.DateTimeFormat ? Intl.DateTimeFormat().resolvedOptions().timeZone : null,
      };
    } catch (e) { return {}; }
  }

  function scheduleHeartbeat() {
    setInterval(function () {
      if (tabHidden) return;
      var now = Date.now();
      sessionSeconds += 30;
      track("heartbeat", { session_seconds: sessionSeconds });
    }, 30000);
  }

  function onScroll() {
    var now = Date.now();
    if (now - lastScrollSend < SCROLL_THROTTLE) return;
    lastScrollSend = now;

    var h = document.documentElement.scrollHeight - window.innerHeight;
    if (h <= 0) return;
    var pct = Math.min(100, Math.floor((window.scrollY / h) * 100));
    var pctKey = pct - (pct % 25);
    if (pctKey <= 0 || pctKey > 100 || depthsSent[pctKey]) return;
    depthsSent[pctKey] = true;

    if (rafPending) return;
    rafPending = true;
    requestAnimationFrame(function () {
      rafPending = false;
      track("scroll_depth", { depth_pct: pctKey, url: location.href });
    });
  }

  function onVisibility() {
    if (document.visibilityState === "hidden") {
      tabHidden = true;
      var now = Date.now();
      sessionSeconds = Math.floor((now - startTs) / 1000);
      track("page_exit", { duration_ms: now - startTs });
      flush(true);
    } else {
      tabHidden = false;
    }
  }

  function interceptFetch() {
    var origFetch = window.fetch;
    window.fetch = function () {
      var t0 = Date.now();
      var args = arguments;
      var url = typeof args[0] === "string" ? args[0] : (args[0] && args[0].url) || "";
      var method = "GET";
      if (args[1]) {
        method = (args[1].method || method).toUpperCase();
      }
      return origFetch.apply(this, args).then(function (res) {
        onIdle(function () {
          track("api_call", { url: url, method: method, status: res.status, duration_ms: Date.now() - t0 });
        });
        return res;
      });
    };
  }

  function interceptXhr() {
    window.XMLHttpRequest = function () {
      var xhr = new XMLHttpRequest();
      var open = xhr.open;
      xhr.open = function (method, url) {
        this._method = (method || "GET").toUpperCase();
        this._url = String(url || "");
        this._t0 = Date.now();
        return open.apply(this, arguments);
      };
      var send = xhr.send;
      xhr.send = function () {
        var self = this;
        this.addEventListener("load", function () {
          if (self._url) {
            onIdle(function () {
              track("api_call", { url: self._url, method: self._method || "GET", status: self.status, duration_ms: Date.now() - (self._t0 || Date.now()) });
            });
          }
        });
        return send.apply(this, arguments);
      };
      return xhr;
    };
  }

  function init() {
    pageView(true);
    scheduleHeartbeat();

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("beforeunload", function () {
      var now = Date.now();
      sessionSeconds = Math.floor((now - startTs) / 1000);
      track("page_exit", { duration_ms: now - startTs });
      flush(false);
    });

    window.addEventListener("popstate", function () {
      pageView(false);
    }, false);

    var origPushState = history.pushState;
    history.pushState = function () {
      origPushState.apply(this, arguments);
      pageView(false);
    };

    interceptFetch();
    interceptXhr();

    document.addEventListener("click", function (e) {
      var el = e.target.closest("[data-track]");
      if (!el) return;
      var name = (el.getAttribute("data-track") || "").trim();
      var text = (el.innerText || el.textContent || "").trim().slice(0, 120);
      if (!name) return;
      track("feature_click", { feature_name: name, element_text: text });
    });

    window.addEventListener("pagehide", function (e) {
      flush(e.persisted ? false : true);
    });

    setTimeout(function () { flush(true); }, FLUSH_MS + 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
