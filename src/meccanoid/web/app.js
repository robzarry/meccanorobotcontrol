// Meccanoid control panel. Talks to the server over a WebSocket at /ws:
// sends {type: ...} commands, receives {type: "state"} after every change.
"use strict";

const JOINTS = [
  { servo: 3, name: "Left shoulder" },
  { servo: 4, name: "Left elbow" },
  { servo: 2, name: "Right shoulder" },
  { servo: 1, name: "Right elbow" },
];
const EXTRA_SLOTS = [0, 5, 6, 7];
const SERVO_COLORS = ["#2a2e35", "#ff3b3b", "#37d461", "#ffd43b",
                      "#3b82ff", "#e64ce6", "#3be0e6", "#ffffff"];
const SERVO_COLOR_NAMES = ["Off", "Red", "Green", "Yellow", "Blue", "Magenta", "Cyan", "White"];
const EYE_PRESETS = [
  ["White", 7, 7, 7], ["Red", 7, 0, 0], ["Orange", 7, 3, 0], ["Yellow", 7, 7, 0],
  ["Green", 0, 7, 0], ["Cyan", 0, 7, 7], ["Blue", 0, 0, 7], ["Purple", 5, 0, 7], ["Off", 0, 0, 0],
];
const DRIVE_REPEAT_MS = 200;   // server stops the wheels after 600 ms of silence
const SLIDER_THROTTLE_MS = 60;

const $ = (sel) => document.querySelector(sel);
let ws = null;
let state = null;
let dragging = null;   // the slider the user is holding, so updates don't fight them

// ---------- connection ----------

function openSocket() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "state") render(msg);
    else if (msg.type === "error") toast(msg.message);
  };
  ws.onclose = () => {
    state = null;
    renderOffline("Server unreachable");
    stopDriving(false);
    setTimeout(openSocket, 1500);
  };
}

function send(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
}

const throttles = new Map();
function sendThrottled(key, msg) {
  const t = throttles.get(key) || { last: 0, timer: null, pending: null };
  throttles.set(key, t);
  t.pending = msg;
  const wait = SLIDER_THROTTLE_MS - (Date.now() - t.last);
  if (wait <= 0) {
    t.last = Date.now();
    send(t.pending);
  } else if (!t.timer) {
    t.timer = setTimeout(() => {
      t.timer = null;
      t.last = Date.now();
      send(t.pending);
    }, wait);
  }
}

let toastTimer = null;
function toast(text) {
  const el = $("#toast");
  el.textContent = text;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), 3500);
}

// ---------- building the controls ----------

function slider(container, { label, min, max, value, onInput }) {
  const wrap = document.createElement("label");
  wrap.className = "slider";
  wrap.innerHTML = `<span>${label} <output></output></span><input type="range">`;
  const input = wrap.querySelector("input");
  const out = wrap.querySelector("output");
  Object.assign(input, { min, max, value });
  out.textContent = value;
  input.addEventListener("pointerdown", () => (dragging = input));
  input.addEventListener("pointerup", () => (dragging = null));
  input.addEventListener("input", () => {
    out.textContent = input.value;
    onInput(Number(input.value));
  });
  container.append(wrap);
  return {
    set(v) {
      if (dragging !== input) { input.value = v; out.textContent = v; }
    },
  };
}

function swatches(container, colors, onPick, small = false) {
  const buttons = colors.map(([title, css], i) => {
    const b = document.createElement("button");
    b.className = "swatch" + (small ? " small" : "");
    b.style.background = css;
    b.title = title;
    b.setAttribute("aria-label", title);
    b.addEventListener("click", () => onPick(i));
    container.append(b);
    return b;
  });
  return { select(i) { buttons.forEach((b, j) => b.classList.toggle("sel", i === j)); } };
}

const jointSliders = {};
for (const { servo, name } of JOINTS) {
  jointSliders[servo] = slider($("#joints"), {
    label: name, min: 0, max: 255, value: 128,
    onInput: (v) => sendThrottled(`joint${servo}`, { type: "joint", servo, position: v }),
  });
}
for (const servo of EXTRA_SLOTS) {
  jointSliders[servo] = slider($("#joints-extra"), {
    label: `Slot ${servo}`, min: 0, max: 255, value: 128,
    onInput: (v) => sendThrottled(`joint${servo}`, { type: "joint", servo, position: v }),
  });
}

const eyeCss = (r, g, b) => `rgb(${[r, g, b].map((v) => Math.round((v * 255) / 7)).join(",")})`;
const eyePresets = swatches(
  $("#eye-swatches"),
  EYE_PRESETS.map(([n, r, g, b]) => [n, eyeCss(r, g, b)]),
  (i) => { const [, r, g, b] = EYE_PRESETS[i]; send({ type: "eyes", r, g, b }); },
);
const eyeSliders = ["Red", "Green", "Blue"].map((label, ch) =>
  slider($("#eye-sliders"), {
    label, min: 0, max: 7, value: 7,
    onInput: (v) => {
      const rgb = [...(state?.eyes || [7, 7, 7])];
      rgb[ch] = v;
      sendThrottled("eyes", { type: "eyes", r: rgb[0], g: rgb[1], b: rgb[2] });
    },
  }));

const chestButtons = [0, 1, 2, 3].map((i) => {
  const b = document.createElement("button");
  b.className = "btn toggle";
  b.textContent = i + 1;
  b.setAttribute("aria-label", `Chest light ${i + 1}`);
  b.addEventListener("click", () => send({ type: "chest", index: i, on: !state?.chest[i] }));
  $("#chest-toggles").append(b);
  return b;
});

const servoColorPickers = {};
for (const { servo, name } of JOINTS) {
  const row = document.createElement("div");
  row.className = "servo-row";
  row.innerHTML = `<span>${name}</span><div class="swatches"></div>`;
  $("#servo-colors").append(row);
  servoColorPickers[servo] = swatches(
    row.querySelector(".swatches"),
    SERVO_COLORS.map((css, i) => [SERVO_COLOR_NAMES[i], css]),
    (color) => send({ type: "servo_color", servo, color }),
    true,
  );
}

document.querySelectorAll("[data-cmd]").forEach((el) =>
  el.addEventListener("click", () => {
    if (el.dataset.cmd === "stop") stopDriving(true);
    else send({ type: el.dataset.cmd });
  }));

$("#connect").addEventListener("click", () =>
  send({ type: state?.connected ? "disconnect" : "connect" }));

const speed = $("#speed");
speed.addEventListener("input", () => ($("#speed-out").textContent = speed.value));

// ---------- driving (hold to move) ----------

const DIRECTIONS = { forward: [1, 1], back: [-1, -1], left: [-1, 1], right: [1, -1] };
let driveTimer = null;
let driveDir = null;

function startDriving(dir) {
  if (driveDir === dir) return;
  driveDir = dir;
  document.querySelectorAll("[data-drive]").forEach((b) =>
    b.classList.toggle("held", b.dataset.drive === dir));
  const tick = () => {
    const s = Number(speed.value);
    const [l, r] = DIRECTIONS[driveDir];
    send({ type: "drive", left: l * s, right: r * s });
  };
  tick();
  clearInterval(driveTimer);
  driveTimer = setInterval(tick, DRIVE_REPEAT_MS);
}

function stopDriving(sendStop = true) {
  clearInterval(driveTimer);
  driveTimer = null;
  driveDir = null;
  document.querySelectorAll("[data-drive]").forEach((b) => b.classList.remove("held"));
  if (sendStop) send({ type: "stop" });
}

document.querySelectorAll("[data-drive]").forEach((b) => {
  b.addEventListener("pointerdown", (e) => {
    b.setPointerCapture(e.pointerId);
    startDriving(b.dataset.drive);
  });
  for (const ev of ["pointerup", "pointercancel", "lostpointercapture"]) {
    b.addEventListener(ev, () => { if (driveDir) stopDriving(); });
  }
  b.addEventListener("contextmenu", (e) => e.preventDefault());
});

const KEYS = {
  ArrowUp: "forward", w: "forward", ArrowDown: "back", s: "back",
  ArrowLeft: "left", a: "left", ArrowRight: "right", d: "right",
};
const heldKeys = [];
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT") return;
  if (e.key === " " || e.key === "Escape") { e.preventDefault(); stopDriving(); return; }
  const dir = KEYS[e.key];
  if (!dir) return;
  e.preventDefault();
  if (!heldKeys.includes(e.key)) heldKeys.push(e.key);
  startDriving(dir);
});
document.addEventListener("keyup", (e) => {
  const i = heldKeys.indexOf(e.key);
  if (i < 0) return;
  heldKeys.splice(i, 1);
  if (heldKeys.length) startDriving(KEYS[heldKeys[heldKeys.length - 1]]);
  else stopDriving();
});
// Switching tabs or apps mid-drive must not leave the robot rolling.
window.addEventListener("blur", () => { heldKeys.length = 0; if (driveDir) stopDriving(); });
document.addEventListener("visibilitychange", () => { if (document.hidden && driveDir) stopDriving(); });

// ---------- rendering state ----------

function renderOffline(text) {
  document.body.classList.add("offline");
  $("#status").className = "status";
  $("#status-text").textContent = text;
  $("#connect").textContent = "Connect";
  $("#connect").disabled = !ws || ws.readyState !== WebSocket.OPEN;
}

function render(s) {
  state = s;
  $("#mode").hidden = !s.mock;
  $("#connect").disabled = s.busy;
  if (s.busy) {
    $("#status").className = "status busy";
    $("#status-text").textContent = s.connected ? "Disconnecting…" : "Connecting…";
  } else if (s.connected) {
    document.body.classList.remove("offline");
    $("#status").className = "status on";
    $("#status-text").textContent = s.mock ? "Mock connected" : "Connected";
    $("#connect").textContent = "Disconnect";
  } else {
    renderOffline("Robot offline");
  }
  if (!s.connected) document.body.classList.add("offline");

  s.joints.forEach((v, servo) => jointSliders[servo]?.set(v));
  s.eyes.forEach((v, ch) => eyeSliders[ch].set(v));
  eyePresets.select(EYE_PRESETS.findIndex(([, r, g, b]) =>
    r === s.eyes[0] && g === s.eyes[1] && b === s.eyes[2]));
  chestButtons.forEach((b, i) => b.classList.toggle("on", s.chest[i]));
  for (const { servo } of JOINTS) servoColorPickers[servo].select(s.servo_colors[servo]);

  drawRobot(s);
}

// Positions are 0-255 with 128 as centre. The drawing maps that to ±90°;
// it is illustrative only, the real joint travel is still to be measured.
const angle = (p) => ((p - 128) / 128) * 90;

function drawRobot(s) {
  const j = s.joints;
  $("#arm-left").setAttribute("transform", `rotate(${angle(j[3])} 52 96)`);
  $("#forearm-left").setAttribute("transform", `rotate(${angle(j[4])} 52 138)`);
  $("#arm-right").setAttribute("transform", `rotate(${-angle(j[2])} 188 96)`);
  $("#forearm-right").setAttribute("transform", `rotate(${-angle(j[1])} 188 138)`);

  const eye = eyeCss(...s.eyes);
  $("#eye-l").style.fill = eye;
  $("#eye-r").style.fill = eye;
  document.querySelectorAll("#chest .chest-led").forEach((c, i) =>
    c.classList.toggle("on", s.chest[i]));
  for (const servo of [1, 2, 3, 4]) {
    const color = s.servo_colors[servo];
    $(`#led-${servo}`).style.fill = color ? SERVO_COLORS[color] : "";
  }
  const arrow = (v) => (v > 0 ? "▲" : v < 0 ? "▼" : "");
  $("#wheel-l").textContent = arrow(s.wheels[0]);
  $("#wheel-r").textContent = arrow(s.wheels[1]);
}

renderOffline("Connecting…");
openSocket();
