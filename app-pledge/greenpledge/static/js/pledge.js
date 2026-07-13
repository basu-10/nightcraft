(function () {
  "use strict";

  // ---- Earth SVG (built once per host, unique ids via prefix) -------------
  function buildEarth(p) {
    return `
<svg viewBox="0 0 320 320" class="earth-svg" role="img" aria-label="A stylized, living Earth">
  <defs>
    <radialGradient id="ocean-${p}" cx="38%" cy="33%" r="78%">
      <stop offset="0%" stop-color="#46c0ec"/>
      <stop offset="52%" stop-color="#1c7fb6"/>
      <stop offset="100%" stop-color="#0a2c46"/>
    </radialGradient>
    <linearGradient id="land-${p}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#62c96f"/>
      <stop offset="100%" stop-color="#2f7d3a"/>
    </linearGradient>
    <radialGradient id="atmo-${p}" cx="50%" cy="50%" r="50%">
      <stop offset="76%" stop-color="rgba(120,220,255,0)"/>
      <stop offset="92%" stop-color="rgba(150,230,255,0.4)"/>
      <stop offset="100%" stop-color="rgba(150,230,255,0)"/>
    </radialGradient>
    <radialGradient id="shine-${p}" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="rgba(255,255,255,0.55)"/>
      <stop offset="42%" stop-color="rgba(255,255,255,0.08)"/>
      <stop offset="100%" stop-color="rgba(255,255,255,0)"/>
    </radialGradient>
    <clipPath id="globe-${p}"><circle cx="160" cy="160" r="120"/></clipPath>
  </defs>

  <g class="earth">
    <circle class="atmo" cx="160" cy="160" r="132" fill="url(#atmo-${p})"/>

    <g clip-path="url(#globe-${p})">
      <g class="earth-spin">
        <circle cx="160" cy="160" r="120" fill="url(#ocean-${p})"/>

        <g class="landmass" fill="url(#land-${p})">
          <path d="M72 118 q22 -30 56 -22 q30 6 25 34 q-7 26 -36 29 q-40 5 -52 -21 q-9 -16 7 -24 z"/>
          <path d="M150 198 q27 -10 53 4 q22 14 7 35 q-21 22 -53 13 q-27 -8 -23 -35 q3 -16 16 -33 z"/>
          <path d="M208 108 q25 -6 35 15 q8 21 -13 31 q-27 12 -39 -11 q-8 -23 17 -35 z"/>
          <path d="M96 214 q18 -4 26 11 q6 16 -11 22 q-20 6 -27 -13 q-3 -15 12 -20 z"/>
        </g>

        <!-- trees (appear early) -->
        <g class="life t20">
          <g transform="translate(108 126)"><rect x="-1.5" y="0" width="3" height="7" fill="#6b4a2b"/><circle cx="0" cy="-3" r="6.5" fill="#2f7d3a"/></g>
          <g transform="translate(168 214)"><rect x="-1.5" y="0" width="3" height="7" fill="#6b4a2b"/><circle cx="0" cy="-3" r="7" fill="#2c7235"/></g>
          <g transform="translate(226 132)"><rect x="-1.5" y="0" width="3" height="7" fill="#6b4a2b"/><circle cx="0" cy="-3" r="6" fill="#318438"/></g>
          <g transform="translate(120 175)"><rect x="-1.2" y="0" width="2.4" height="6" fill="#6b4a2b"/><circle cx="0" cy="-3" r="5.5" fill="#2f7d3a"/></g>
        </g>

        <!-- more forest as it grows -->
        <g class="life t70">
          <g transform="translate(140 150)"><rect x="-1.5" y="0" width="3" height="7" fill="#6b4a2b"/><circle cx="0" cy="-3" r="6" fill="#2c7235"/></g>
          <g transform="translate(196 168)"><rect x="-1.5" y="0" width="3" height="7" fill="#6b4a2b"/><circle cx="0" cy="-3" r="6.5" fill="#318438"/></g>
          <g transform="translate(110 205)"><rect x="-1.5" y="0" width="3" height="7" fill="#6b4a2b"/><circle cx="0" cy="-3" r="6" fill="#2f7d3a"/></g>
          <g transform="translate(238 168)"><rect x="-1.5" y="0" width="3" height="7" fill="#6b4a2b"/><circle cx="0" cy="-3" r="6" fill="#2c7235"/></g>
        </g>

        <!-- ocean life -->
        <g class="life t50" fill="#cdeeff">
          <path d="M118 178 q9 -7 20 0 q-7 7 -20 0 z M130 178 l6 -3 v6 z"/>
          <path d="M196 150 q8 -6 17 0 q-6 6 -17 0 z M206 150 l5 -2.5 v5 z"/>
        </g>
      </g>

      <!-- clouds (separate parallax) -->
      <g class="clouds" fill="rgba(255,255,255,0.85)">
        <ellipse cx="118" cy="116" rx="26" ry="10"/>
        <ellipse cx="204" cy="168" rx="30" ry="11"/>
        <ellipse cx="150" cy="226" rx="22" ry="9"/>
      </g>

      <!-- specular highlight (fixed) -->
      <ellipse cx="122" cy="118" rx="74" ry="62" fill="url(#shine-${p})" clip-path="url(#globe-${p})"/>
    </g>

    <!-- birds in the sky -->
    <g class="life t45" fill="none" stroke="#214a34" stroke-width="2.2" stroke-linecap="round">
      <path d="M58 74 q8 -8 16 0 q8 -8 16 0"/>
      <path d="M236 96 q7 -7 14 0 q7 -7 14 0"/>
    </g>

    <!-- sparkles -->
    <g class="life t90" fill="#eafff2">
      <circle cx="252" cy="62" r="2.2"/>
      <circle cx="66" cy="238" r="2.2"/>
      <circle cx="266" cy="198" r="1.8"/>
      <circle cx="48" cy="120" r="1.6"/>
    </g>
  </g>
</svg>`;
  }

  var heroHost = document.getElementById("heroEarth");
  var futureHost = document.getElementById("futureEarth");
  if (!heroHost || !futureHost) return;

  heroHost.innerHTML = buildEarth("hero");
  futureHost.innerHTML = buildEarth("future");

  var heroEarth = heroHost.querySelector(".earth");
  var futureEarth = futureHost.querySelector(".earth");
  futureEarth.style.setProperty("--vib", "1");

  function setVib(el, v) {
    el.style.setProperty("--vib", v.toFixed(4));
  }

  function easeInOut(t) {
    return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
  }
  function easeOut(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---- Community count-up (graceful with zeros) --------------------------
  var nf = new Intl.NumberFormat("en-US");
  Array.prototype.forEach.call(document.querySelectorAll(".stat-num"), function (el) {
    var target = Number(el.dataset.target || 0);
    if (target === 0) {
      el.textContent = "0";
      return;
    }
    if (reduce) {
      el.textContent = nf.format(target);
      return;
    }
    var t0 = performance.now();
    (function step(now) {
      var p = Math.min(1, (now - t0) / 1200);
      el.textContent = nf.format(Math.round(target * easeOut(p)));
      if (p < 1) requestAnimationFrame(step);
    })(t0);
  });

  // ---- Cinematic play ----------------------------------------------------
  var playBtn = document.getElementById("playBtn");
  var caption = document.getElementById("caption");
  var futureSection = document.getElementById("future");

  function finishCinematic() {
    heroEarth.classList.remove("playing");
    revealFuture();
  }

  function startCinematic() {
    playBtn.classList.add("is-hidden");

    if (reduce) {
      setVib(heroEarth, 1);
      finishCinematic();
      return;
    }

    heroEarth.classList.add("playing");
    var dur = 10500;
    var t0 = performance.now();
    (function frame(now) {
      var p = Math.min(1, (now - t0) / dur);
      setVib(heroEarth, easeInOut(p));
      if (p < 1) requestAnimationFrame(frame);
      else finishCinematic();
    })(t0);
  }

  function revealFuture() {
    futureSection.hidden = false;
    requestAnimationFrame(function () {
      futureSection.classList.add("show");
    });
    updateFromSlider();
    setTimeout(function () {
      futureSection.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    }, 140);
  }

  if (playBtn) playBtn.addEventListener("click", startCinematic);

  // ---- Slider-driven future ---------------------------------------------
  var slider = document.getElementById("slider");
  var participantsNum = document.getElementById("participantsNum");
  var co2El = document.getElementById("co2");
  var treesEl = document.getElementById("trees");
  var carsEl = document.getElementById("cars");
  var homesEl = document.getElementById("homes");
  var flightsEl = document.getElementById("flights");

  function getPeople(sliderVal) {
    // slider 0 -> 10K, 250 -> 100K, 500 -> 1M, 750 -> 10M, 1000 -> 100M
    return Math.round(10000 * Math.pow(10, (sliderVal / 1000) * 4));
  }

  var PER_PERSON = 100;   // kg CO2 avoided per participant, per year
  var TREE = 22;          // kg CO2 absorbed by one tree, per year
  var CAR = 4651;         // kg CO2 emitted by one car, per year
  var HOME = 676;         // kg CO2 for one home's clean-energy supply, per year
  var FLIGHT = 5495;      // kg CO2 per flight (NYC-LA)

  function fmt(n) {
    return nf.format(Math.round(n));
  }

  function updateFromSlider() {
    var sliderVal = Number(slider.value);
    var N = getPeople(sliderVal);
    var v = 1 + 0.5 * (sliderVal / 1000);
    setVib(futureEarth, v);

    var co2 = N * PER_PERSON;
    participantsNum.textContent = fmt(N);
    co2El.textContent = fmt(co2);
    treesEl.textContent = fmt(co2 / TREE);
    carsEl.textContent = fmt(co2 / CAR);
    homesEl.textContent = fmt(co2 / HOME);
    flightsEl.textContent = fmt(co2 / FLIGHT);
  }

  if (slider) slider.addEventListener("input", updateFromSlider);
})();
