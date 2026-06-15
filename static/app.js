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
  for (const sample of samples) {
    const bar = document.createElement("div");
    const elevation = Math.max(0, Number(sample.elevation_deg));
    bar.className = `horizon-bar${sample.visible ? " visible" : ""}`;
    bar.style.height = `${Math.max(4, elevation * 0.8)}px`;
    bar.title = `${sample.at} ${sample.elevation_deg} deg`;
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
  refreshMoon().catch(showError);
});

document.querySelector("#moon-form").addEventListener("change", () => {
  refreshMoon().catch(showError);
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

updateTransportFields();
refreshStatus().catch(showError);
setInterval(() => refreshStatus().catch(showError), 3000);
