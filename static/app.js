const statusEl = document.querySelector("#status");
const testsBody = document.querySelector("#tests-body");
const packetLog = document.querySelector("#packet-log");
const metricTx = document.querySelector("#metric-tx");
const metricRx = document.querySelector("#metric-rx");
const metricLoss = document.querySelector("#metric-loss");
const metricSnr = document.querySelector("#metric-snr");
const metricLatency = document.querySelector("#metric-latency");
const connectionState = document.querySelector("#connection-state");
const connectionType = document.querySelector("#connection-type");
const bleDeviceList = document.querySelector("#ble-device-list");
const moonDot = document.querySelector("#moon-dot");
const themeButtons = document.querySelectorAll("[data-theme-option]");
const receptionMapEl = document.querySelector("#reception-map");
const receptionFields = {
  coverage: document.querySelector("#map-coverage"),
  txVisibility: document.querySelector("#map-tx-visibility"),
  best: document.querySelector("#map-best"),
  detail: document.querySelector("#map-detail"),
};
const moonFields = {
  az: document.querySelector("#moon-az"),
  el: document.querySelector("#moon-el"),
  range: document.querySelector("#moon-range"),
  delay: document.querySelector("#moon-delay"),
  doppler: document.querySelector("#moon-doppler"),
  margin: document.querySelector("#moon-margin"),
  score: document.querySelector("#moon-score"),
  phase: document.querySelector("#moon-phase"),
  velocity: document.querySelector("#moon-velocity"),
  path: document.querySelector("#moon-path"),
  wavelength: document.querySelector("#moon-wavelength"),
  rx: document.querySelector("#moon-rx"),
  verdict: document.querySelector("#moon-verdict"),
  assumption: document.querySelector("#moon-assumption"),
  horizon: document.querySelector("#horizon"),
  horizonDetail: document.querySelector("#horizon-detail"),
  eirp: document.querySelector("#pred-eirp"),
  totalLoss: document.querySelector("#pred-total-loss"),
  fspl: document.querySelector("#pred-fspl"),
  reflection: document.querySelector("#pred-reflection"),
  elevationPenalty: document.querySelector("#pred-elevation"),
  requiredGain: document.querySelector("#pred-required"),
  windowBest: document.querySelector("#pred-window-best"),
  windowSet: document.querySelector("#pred-window-set"),
};

let currentTestId = null;
let latestReceptionMap = null;
let lastReceptionMapAt = 0;
let leafletMap = null;
let receptionLayer = null;
let stationLayer = null;
const themeStorageKey = "moontastic-theme";

function setTheme(theme) {
  const nextTheme = ["light", "dark", "night"].includes(theme) ? theme : "light";
  document.documentElement.dataset.theme = nextTheme;
  for (const button of themeButtons) {
    button.setAttribute("aria-pressed", String(button.dataset.themeOption === nextTheme));
  }
  localStorage.setItem(themeStorageKey, nextTheme);
  renderReceptionMap(latestReceptionMap);
}

function initializeTheme() {
  setTheme(localStorage.getItem(themeStorageKey) || "light");
  for (const button of themeButtons) {
    button.addEventListener("click", () => {
      setTheme(button.dataset.themeOption);
    });
  }
}

function updateTransportFields() {
  const selected = connectionType.value;
  for (const field of document.querySelectorAll(".transport-field")) {
    const visible = field.classList.contains(`transport-${selected}`);
    field.classList.toggle("is-hidden", !visible);
  }
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

function formPayload(form) {
  const data = new FormData(form);
  return Object.fromEntries(data.entries());
}

function fmt(value, fallback = "-") {
  return value === null || value === undefined || value === "" ? fallback : value;
}

function updateMetrics(summary = {}) {
  metricTx.textContent = fmt(summary.tx, "0");
  metricRx.textContent = fmt(summary.rx, "0");
  metricLoss.textContent = summary.packet_loss_percent === null || summary.packet_loss_percent === undefined
    ? "-"
    : `${summary.packet_loss_percent}%`;
  metricSnr.textContent = fmt(summary.avg_snr);
  metricLatency.textContent = fmt(summary.avg_latency_ms);
}

function renderPackets(packets = []) {
  packetLog.innerHTML = "";
  if (!packets.length) {
    packetLog.innerHTML = `<div class="packet">No packets recorded yet</div>`;
    return;
  }
  for (const packet of packets.slice().reverse()) {
    const row = document.createElement("div");
    row.className = "packet";
    row.innerHTML = `
      <span class="dir-${packet.direction}">${packet.direction.toUpperCase()}</span>
      <span>${fmt(packet.created_at)}</span>
      <span>${fmt(packet.payload)}</span>
      <span>${packet.latency_ms === null || packet.latency_ms === undefined ? "-" : `${packet.latency_ms} ms`}</span>
      <span>SNR ${fmt(packet.snr)}</span>
      <span>RSSI ${fmt(packet.rssi)}</span>
    `;
    packetLog.append(row);
  }
}

async function loadTest(testId) {
  if (!testId) {
    updateMetrics();
    renderPackets();
    return;
  }
  const test = await requestJson(`/api/tests/${testId}`);
  updateMetrics(test.summary);
  renderPackets(test.packets);
}

async function refreshTests() {
  const tests = await requestJson("/api/tests");
  testsBody.innerHTML = "";
  for (const test of tests) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${test.id}</td>
      <td>${test.name}</td>
      <td>${test.status}</td>
      <td>${test.target}</td>
      <td>${fmt(test.tx_count, 0)}</td>
      <td>${fmt(test.rx_count, 0)}</td>
      <td>${fmt(test.avg_snr)}</td>
      <td>${test.avg_latency_ms === null || test.avg_latency_ms === undefined ? "-" : `${test.avg_latency_ms} ms`}</td>
      <td>${test.started_at}</td>
    `;
    row.addEventListener("click", () => {
      currentTestId = test.id;
      loadTest(test.id).catch(showError);
    });
    testsBody.append(row);
  }
  if (!currentTestId && tests[0]) {
    currentTestId = tests[0].id;
  }
}

function showError(error) {
  statusEl.textContent = error.message;
  statusEl.style.color = "var(--error)";
  connectionState.textContent = error.message;
  connectionState.style.color = "var(--error)";
}

function queryFromForm(form) {
  return new URLSearchParams(formPayload(form)).toString();
}

function initializeReceptionMap() {
  if (!receptionMapEl) {
    return;
  }
  if (typeof L === "undefined") {
    receptionFields.detail.textContent = "Real map library unavailable. Check network access for Leaflet and OpenStreetMap tiles.";
    return;
  }

  leafletMap = L.map(receptionMapEl, {
    worldCopyJump: true,
    minZoom: 2,
    maxZoom: 8,
  }).setView([20, 0], 2);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 8,
  }).addTo(leafletMap);

  receptionLayer = L.layerGroup().addTo(leafletMap);
  stationLayer = L.layerGroup().addTo(leafletMap);
}

function probabilityColor(probability, opacity = null) {
  const p = Math.max(0, Math.min(1, Number(probability)));
  if (document.documentElement.dataset.theme === "night") {
    const red = Math.round(96 + p * 159);
    const green = Math.round(8 + p * 32);
    const blue = Math.round(8 + p * 24);
    const alpha = opacity ?? 0.16 + p * 0.58;
    return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
  }
  const red = Math.round(239 * p + 45 * (1 - p));
  const green = Math.round(68 * p + 212 * (1 - p));
  const blue = Math.round(68 * p + 191 * (1 - p));
  const alpha = opacity ?? 0.18 + p * 0.62;
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

function renderReceptionMap(map) {
  if (!map || !leafletMap || !receptionLayer || !stationLayer) {
    return;
  }

  receptionLayer.clearLayers();
  stationLayer.clearLayers();

  for (const point of map.points) {
    if (point.probability <= 0) {
      continue;
    }
    const probability = Math.round(point.probability * 100);
    const marker = L.circleMarker([point.lat, point.lon], {
      radius: 4 + point.probability * 12,
      color: probabilityColor(point.probability, 0.95),
      fillColor: probabilityColor(point.probability, 0.6),
      fillOpacity: 0.62,
      opacity: 0.95,
      weight: 1,
    });
    marker.bindTooltip(`${probability}% estimate<br>${point.lat}, ${point.lon}<br>Moon ${point.moon_elevation_deg} deg`);
    marker.on("mouseover click", () => updateReceptionDetail(point));
    marker.addTo(receptionLayer);
  }

  L.circleMarker([map.station.latitude, map.station.longitude], {
    radius: 9,
    color: "#ffffff",
    fillColor: probabilityColor(1, 0.95),
    fillOpacity: 1,
    opacity: 1,
    weight: 2,
  })
    .bindTooltip("Your TX station")
    .addTo(stationLayer);

  leafletMap.invalidateSize();
}

function updateReceptionDetail(point) {
  if (!point) {
    return;
  }
  const probability = Math.round(point.probability * 100);
  receptionFields.detail.textContent = `${point.lat}, ${point.lon} - ${probability}% reception estimate, Moon elevation ${point.moon_elevation_deg} deg`;
}

function updateReceptionSummary(map) {
  receptionFields.coverage.textContent = `${map.coverage_percent}%`;
  receptionFields.txVisibility.textContent = map.tx.moon_visible
    ? `${map.tx.moon_elevation_deg} deg`
    : "Below horizon";
  if (map.best.length) {
    const best = map.best[0];
    receptionFields.best.textContent = `${Math.round(best.probability * 100)}% at ${best.lat}, ${best.lon}`;
  } else {
    receptionFields.best.textContent = "None";
  }
  receptionFields.detail.textContent = map.assumption;
}

async function refreshReceptionMap(force = false) {
  const now = Date.now();
  if (!force && latestReceptionMap && now - lastReceptionMapAt < 60000) {
    return;
  }
  const form = document.querySelector("#moon-form");
  const map = await requestJson(`/api/reception-map?${queryFromForm(form)}&step_degrees=10`);
  latestReceptionMap = map;
  lastReceptionMapAt = now;
  updateReceptionSummary(map);
  renderReceptionMap(map);
}

function positionMoonDot(moon) {
  const az = Number(moon.azimuth_deg);
  const el = Math.max(0, Math.min(90, Number(moon.elevation_deg)));
  const radius = (90 - el) / 90 * 96;
  const angle = (az - 90) * Math.PI / 180;
  const x = 110 + Math.cos(angle) * radius;
  const y = 110 + Math.sin(angle) * radius;
  moonDot.style.left = `${x}px`;
  moonDot.style.top = `${y}px`;
  moonDot.style.opacity = moon.visible ? "1" : "0.35";
}

function renderHorizon(samples = []) {
  moonFields.horizon.innerHTML = "";
  moonFields.horizon.style.gridTemplateColumns = `repeat(${samples.length}, minmax(8px, 1fr))`;
  moonFields.horizonDetail.textContent = "Select a horizon bar for time and elevation";
  for (const sample of samples) {
    const bar = document.createElement("div");
    const elevation = Math.max(0, Number(sample.elevation_deg));
    const detail = `${fmtTime(sample.at)} - ${sample.elevation_deg} deg elevation${sample.visible ? " above horizon" : " below horizon"}`;
    bar.className = `horizon-bar${sample.visible ? " visible" : ""}`;
    bar.style.height = `${Math.max(4, elevation * 0.8)}px`;
    bar.tabIndex = 0;
    bar.setAttribute("role", "button");
    bar.setAttribute("aria-label", detail);
    bar.dataset.detail = detail;
    bar.addEventListener("mouseenter", () => {
      moonFields.horizonDetail.textContent = detail;
    });
    bar.addEventListener("focus", () => {
      moonFields.horizonDetail.textContent = detail;
    });
    bar.addEventListener("click", () => {
      moonFields.horizonDetail.textContent = detail;
    });
    moonFields.horizon.append(bar);
  }
}

function fmtDb(value) {
  return value === null || value === undefined ? "-" : `${value} dB`;
}

function fmtDbm(value) {
  return value === null || value === undefined ? "-" : `${value} dBm`;
}

function fmtTime(value) {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

async function refreshMoon() {
  const form = document.querySelector("#moon-form");
  const prediction = await requestJson(`/api/moon?${queryFromForm(form)}`);
  const moon = prediction.moon;
  const link = prediction.link;
  moonFields.az.textContent = `${moon.azimuth_deg} deg`;
  moonFields.el.textContent = `${moon.elevation_deg} deg`;
  moonFields.range.textContent = moon.range_km.toLocaleString();
  moonFields.delay.textContent = moon.round_trip_ms;
  moonFields.doppler.textContent = link.doppler_hz;
  moonFields.margin.textContent = link.margin_db;
  moonFields.score.textContent = `${link.score}/100`;
  moonFields.phase.textContent = `${moon.phase_name} ${Math.round(moon.phase_fraction * 100)}%, ${moon.phase_age_days}d`;
  moonFields.velocity.textContent = moon.radial_velocity_km_s;
  moonFields.path.textContent = moon.round_trip_path_km.toLocaleString();
  moonFields.wavelength.textContent = link.wavelength_m;
  moonFields.rx.textContent = fmtDbm(link.predicted_rx_dbm);
  moonFields.verdict.textContent = link.verdict;
  moonFields.assumption.textContent = link.assumption;
  moonFields.eirp.textContent = `${link.eirp_dbm} dBm / ${link.eirp_w} W`;
  moonFields.totalLoss.textContent = fmtDb(link.moonbounce_loss_db);
  moonFields.fspl.textContent = fmtDb(link.two_way_fspl_db);
  moonFields.reflection.textContent = fmtDb(link.reflection_loss_db);
  moonFields.elevationPenalty.textContent = fmtDb(link.elevation_penalty_db);
  moonFields.requiredGain.textContent = `${link.required_combined_gain_for_0db_margin_dbi} dBi`;
  moonFields.windowBest.textContent = prediction.window.best
    ? `${prediction.window.best.elevation_deg} deg at ${fmtTime(prediction.window.best.at)}`
    : "-";
  moonFields.windowSet.textContent = fmtTime(prediction.window.next_set);
  positionMoonDot(moon);
  renderHorizon(prediction.window.samples);
}

async function refreshStatus() {
  const status = await requestJson("/api/status");
  statusEl.style.color = "";
  connectionState.style.color = "";
  statusEl.textContent = `${status.interface.type.toUpperCase()} ${status.interface.connected ? "connected" : "idle"}${status.running ? " - running" : ""}`;
  connectionState.textContent = describeConnection(status.interface);
  if (!document.querySelector("#connection-form").contains(document.activeElement)) {
    syncConnectionForm(status.interface);
  }
  if (status.current_test_id) {
    currentTestId = status.current_test_id;
  }
  await refreshTests();
  await loadTest(currentTestId);
  await refreshMoon();
  await refreshReceptionMap();
}

function describeConnection(info) {
  if (info.type === "tcp") {
    return `TCP ${info.tcp_host || "host not set"} ${info.connected ? "connected" : "idle"}`;
  }
  if (info.type === "serial") {
    return `Serial ${info.serial_port || "port not set"} ${info.connected ? "connected" : "idle"}`;
  }
  if (info.type === "ble") {
    return `Bluetooth ${info.ble_address || "auto"} ${info.connected ? "connected" : "idle"}`;
  }
  return `Simulator ${info.connected ? "connected" : "idle"}`;
}

function syncConnectionForm(info) {
  connectionType.value = info.type || "sim";
  document.querySelector("[name='tcp_host']").value = info.tcp_host || document.querySelector("[name='tcp_host']").value;
  document.querySelector("[name='serial_port']").value = info.serial_port || document.querySelector("[name='serial_port']").value;
  document.querySelector("[name='ble_address']").value = info.ble_address || document.querySelector("[name='ble_address']").value;
  updateTransportFields();
}

document.querySelector("#test-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const test = await requestJson("/api/tests", {
      method: "POST",
      body: JSON.stringify(formPayload(event.currentTarget)),
    });
    currentTestId = test.id;
    await refreshStatus();
  } catch (error) {
    showError(error);
  }
});

document.querySelector("#stop-btn").addEventListener("click", async () => {
  try {
    await requestJson("/api/tests/current/stop", { method: "POST", body: "{}" });
    await refreshStatus();
  } catch (error) {
    showError(error);
  }
});

document.querySelector("#refresh-btn").addEventListener("click", () => {
  refreshStatus().catch(showError);
});

connectionType.addEventListener("change", updateTransportFields);

document.querySelector("#connection-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    connectionState.textContent = "Connecting";
    const status = await requestJson("/api/connection", {
      method: "POST",
      body: JSON.stringify(formPayload(event.currentTarget)),
    });
    connectionState.textContent = describeConnection(status);
    syncConnectionForm(status);
    await refreshStatus();
  } catch (error) {
    showError(error);
  }
});

document.querySelector("#disconnect-btn").addEventListener("click", async () => {
  try {
    const status = await requestJson("/api/connection/disconnect", { method: "POST", body: "{}" });
    connectionState.textContent = describeConnection(status);
    syncConnectionForm(status);
    await refreshStatus();
  } catch (error) {
    showError(error);
  }
});

document.querySelector("#ble-scan-btn").addEventListener("click", async () => {
  try {
    bleDeviceList.innerHTML = `<button type="button" class="device-pill">Scanning</button>`;
    const devices = await requestJson("/api/connection/ble/scan");
    bleDeviceList.innerHTML = "";
    if (!devices.length) {
      bleDeviceList.innerHTML = `<button type="button" class="device-pill">No BLE devices found</button>`;
      return;
    }
    for (const device of devices) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "device-pill";
      button.textContent = `${device.name || "Meshtastic"} ${device.address || ""}`.trim();
      button.addEventListener("click", () => {
        document.querySelector("[name='ble_address']").value = device.address || device.name || "";
      });
      bleDeviceList.append(button);
    }
  } catch (error) {
    showError(error);
  }
});

document.querySelector("#moon-refresh-btn").addEventListener("click", () => {
  refreshMoon().then(() => refreshReceptionMap(true)).catch(showError);
});

document.querySelector("#moon-form").addEventListener("change", () => {
  refreshMoon().then(() => refreshReceptionMap(true)).catch(showError);
});

document.querySelector("#reception-refresh-btn").addEventListener("click", () => {
  refreshReceptionMap(true).catch(showError);
});

window.addEventListener("resize", () => {
  if (leafletMap) {
    leafletMap.invalidateSize();
  }
});

document.querySelector("#send-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await requestJson("/api/send", {
      method: "POST",
      body: JSON.stringify(formPayload(event.currentTarget)),
    });
    event.currentTarget.reset();
    await refreshStatus();
  } catch (error) {
    showError(error);
  }
});

initializeTheme();
initializeReceptionMap();
updateTransportFields();
refreshStatus().catch(showError);
setInterval(() => refreshStatus().catch(showError), 3000);
