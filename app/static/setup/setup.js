/* Camera setup: edit camera rectangles, homography corners, and ROIs.
 * Mouse: drag/click on the canvases. Keyboard/screen reader: the numeric
 * inputs edit the exact same values. Nothing applies until Save Calibration. */
"use strict";

const $ = (id) => document.getElementById(id);
const P1 = "#23d2c3", P2 = "#ff4d5e", ACCENT = "#ffd23f";

let showcaseMode = false;
let cal = null;      // {cameras, regions} — local working copy
let target = "p1_rect";
let guideTargets = null;
let cameraResolution = null;

/* Target registry: where each editable element lives and how to edit it. */
const TARGETS = {
  p1_board: {label:"Board area",kind:"rect",canvas:"p1_corrected",get:()=>cal.cameras.showcase_board_region},
  p1_rect: { label: "Camera framing", kind: "rect", canvas: "raw",
             get: () => cal.regions.player1.source_rect },
  p1_corners: { label: "Straighten the board", kind: "corners", canvas: "p1_crop",
                get: () => cal.regions.player1.homography_points,
                set: (v) => cal.regions.player1.homography_points = v },
  p1_card: { label: "Played cards", kind: "rect", canvas: "p1_corrected",
             get: () => cal.regions.player1.regions.card_play_region },
  p1_eddie: { label: "Eddies", kind: "rect", canvas: "p1_corrected",
              get: () => cal.regions.player1.regions.eddie_region },
  p1_fixer: { label: "Fixer", kind: "rect", canvas: "p1_corrected",
              get: () => cal.regions.player1.regions.fixer_region },
  p1_gig: { label: "Gigs", kind: "rect", canvas: "p1_corrected",
            get: () => cal.regions.player1.regions.gig_region },
  p1_legend: { label: "Legends", kind: "rect", canvas: "p1_corrected",
               get: () => cal.regions.player1.regions.legend_region },
};

const HELP = {
  rect: "Drag a corner handle to resize, drag inside the box to move it, or drag on " +
        "empty space to draw a new box. Choose another area from the menu when finished.",
  corners: "Drag the four corner handles onto the four corners of your game mat " +
           "(1 top-left, 2 top-right, 3 bottom-right, 4 bottom-left). " +
           "Save to apply the new perspective.",
};

const VIEWS = ["raw", "p1_crop", "p1_corrected"];

/* ---------------- API ---------------- */

async function api(path, body) {
  const opts = body !== undefined
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : { method: "POST" };
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) { /* keep */ }
    setSaveStatus(detail, true);
    throw new Error(detail);
  }
  return res.json();
}

function setSaveStatus(msg, isError = false) {
  const el = $("save-status");
  el.textContent = msg;
  el.style.color = isError ? "#ff4d5e" : "#3ddc84";
  clearTimeout(el._t);
  el._t = setTimeout(() => (el.textContent = ""), 4000);
}

async function loadCalibration() {
  const res = await fetch("/api/vision/calibration");
  cal = await res.json();
  cal.cameras.showcase_board_region ||= {x:0,y:0,width:1,height:1};
  $("rotate-source-180").checked=cal.cameras.rotate_source_180===true;
  for(const key of ['brightness','contrast']){
    $('vision-'+key).value=cal.cameras.vision_adjustments?.[key]??(key==='contrast'?1:0);
    $(key+'-value').textContent=$('vision-'+key).value;
  }
  renderNumericInputs();
}

/* ---------------- streams + status ---------------- */

function attachStreams() {
  for (const view of VIEWS) {
    const img=$(`img-${view}`);
    if(!img.dataset.streaming){img.dataset.streaming="1";startBoardFeed(img,view);}
  }
}

async function pollStatus() {
  try {
    const res = await fetch("/api/vision/status");
    const st = await res.json();
    const el = $("vision-status");
    if (st.resolution) cameraResolution = st.resolution;
    if (st.running) {
      el.className = "running";
      el.textContent = `Camera on · ${st.fps} FPS · ${st.pixel_format||'unknown format'}` +
        (st.resolution ? ` @ ${st.resolution[0]}x${st.resolution[1]}` : "") +

        (st.capture_warning ? " · "+st.capture_warning : "") +
        (st.paused ? " (paused)" : "");
    } else if (st.error) {
      el.className = "error";
      el.textContent = `Camera error — ${st.error}`;
    } else {
      el.className = "";
      el.textContent = "Camera off";
    }
    $("btn-vision-start").disabled = false;
    $("btn-vision-stop").disabled = !st.running;
  } catch (e) {
    $("vision-status").className = "error";
    $("vision-status").textContent = "Cannot connect to the app";
  }
}

$("btn-vision-start").addEventListener("click", async () => {
  const type = $("src-type").value;
  const device = $("src-device").value.trim();
  const source = type !== "camera"
    ? { type, index: 0, path: device }
    : /^\d+$/.test(device)
      ? { type: "camera", index: parseInt(device, 10), path: "" }
      : { type: "camera", index: 0, path: device };
  source.capture_mode=$("capture-mode").value;
  source.exposure_mode=$("exposure-mode").value;
  try { await api("/api/vision/start", { source }); }
  catch(error){$("vision-status").textContent=error.message;return;}
  // Persist the chosen source so start.sh runs pick it up next time.
  cal.cameras.source = source;
  await api("/api/vision/calibration", { cameras: cal.cameras });
  attachStreams();
  pollStatus();
});

$("btn-vision-stop").addEventListener("click", async () => {
  await api("/api/vision/stop");
  pollStatus();
});

$("src-type").addEventListener("change", () => {
  $("src-device-label").textContent = $("src-type").value === "video"
    ? "Video file path"
    : $("src-type").value === "stream" ? "Stream URL" : "Device (index or /dev/video*)";
  if ($("src-type").value !== "camera") document.querySelector(".camera-options").open = true;
  $("camera-list").disabled = $("src-type").value !== "camera";
  $("capture-mode").disabled = $("src-type").value !== "camera";
  $("exposure-mode").disabled = $("src-type").value !== "camera";
});

/* ---------------- target selection ---------------- */

function initTargetSelect() {
  const sel = $("target-select");
  sel.replaceChildren();
  for (const [id, t] of Object.entries(TARGETS)) {
    if(showcaseMode ? !["p1_rect","p1_corners","p1_board"].includes(id) : id==="p1_board")continue;
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = t.label;
    sel.appendChild(opt);
  }
  sel.onchange = () => {
    target = sel.value;
    renderNumericInputs();
  };
}

function renderNumericInputs() {
  if (!cal) return;
  const t = TARGETS[target];
  for(const view of VIEWS){document.querySelector(`[data-view="${view}"]`).hidden=view!==t.canvas;}
  $("target-help").textContent = HELP[t.kind];
  $("btn-clear-corners").classList.toggle("hidden", t.kind !== "corners");
  const box = $("numeric-inputs");
  box.innerHTML = "";

  if (t.kind === "rect") {
    const rect = t.get();
    for (const key of ["x", "y", "width", "height"]) {
      box.appendChild(numField(`${t.label} ${key}`, rect[key], (v) => { rect[key] = v; }));
    }
  } else {
    const points = t.get() || [];
    const names = ["top-left", "top-right", "bottom-right", "bottom-left"];
    names.forEach((name, i) => {
      for (const axis of [0, 1]) {
        const label = `${name} ${axis === 0 ? "x" : "y"}`;
        const value = points[i] ? points[i][axis] : "";
        box.appendChild(numField(label, value, (v) => {
          const pts = t.get() || [[0, 0], [1, 0], [1, 1], [0, 1]];
          while (pts.length < 4) pts.push([0, 0]);
          pts[i][axis] = v;
          t.set(pts);
        }));
      }
    });
  }
}

function numField(label, value, onChange) {
  const wrap = document.createElement("div");
  const id = `nf-${label.replace(/[^a-z0-9]+/gi, "-")}`;
  const lab = document.createElement("label");
  lab.htmlFor = id;
  lab.textContent = label;
  const input = document.createElement("input");
  input.type = "number";
  input.id = id;
  input.min = "0";
  input.max = "1";
  input.step = "0.005";
  input.value = value === "" ? "" : Number(value).toFixed(3);
  input.addEventListener("change", () => {
    const v = Math.min(1, Math.max(0, parseFloat(input.value) || 0));
    input.value = v.toFixed(3);
    onChange(v);
  });
  wrap.appendChild(lab);
  wrap.appendChild(input);
  return wrap;
}

$("btn-clear-corners").addEventListener("click", () => {
  const t = TARGETS[target];
  if (t.kind === "corners") {
    t.set(null);
    renderNumericInputs();
  }
});

/* ---------------- canvas editing ---------------- */

function canvasNorm(canvas, event) {
  const rect = canvas.getBoundingClientRect();
  return [
    Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)),
    Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height)),
  ];
}

/* Drag model: every editable shape exposes four corner handles.
 * - grab a handle  -> move that corner (rects keep the opposite corner fixed)
 * - grab inside    -> move the whole rect
 * - grab empty     -> draw a new rect (rect targets only)                    */

const MIN_SIZE = 0.02;
let drag = null; // {mode:'corner'|'move'|'new', idx, orig, start}

function rectCorners(rect) {
  return [
    [rect.x, rect.y],
    [rect.x + rect.width, rect.y],
    [rect.x + rect.width, rect.y + rect.height],
    [rect.x, rect.y + rect.height],
  ];
}

function nearestHandle(points, pos, canvas) {
  const threshold = 14 / canvas.clientWidth; // ~14px grab radius
  let best = -1, bestDist = threshold;
  points.forEach(([x, y], i) => {
    const d = Math.hypot(x - pos[0], y - pos[1]);
    if (d < bestDist) { best = i; bestDist = d; }
  });
  return best;
}

function insideRect(rect, [x, y]) {
  return x >= rect.x && x <= rect.x + rect.width && y >= rect.y && y <= rect.y + rect.height;
}

function setRectFromCorners(rect, a, b) {
  rect.x = Math.max(0, Math.min(a[0], b[0]));
  rect.y = Math.max(0, Math.min(a[1], b[1]));
  rect.width = Math.max(MIN_SIZE, Math.abs(b[0] - a[0]));
  rect.height = Math.max(MIN_SIZE, Math.abs(b[1] - a[1]));
}

function initCanvases() {
  for (const view of VIEWS) {
    const canvas = $(`cv-${view}`);

    canvas.addEventListener("pointerdown", (e) => {
      const t = TARGETS[target];
      if (t.canvas !== view) return;
      const pos = canvasNorm(canvas, e);
      canvas.setPointerCapture(e.pointerId);

      if (t.kind === "corners") {
        let points = t.get();
        if (!points) { // first interaction: seed an inset quad to grab
          points = [[0.05, 0.05], [0.95, 0.05], [0.95, 0.95], [0.05, 0.95]];
          t.set(points);
        }
        const idx = nearestHandle(points, pos, canvas);
        drag = { mode: "corner", idx: idx >= 0 ? idx : nearestForced(points, pos), start: pos };
        movePoint(t, drag.idx, pos);
        return;
      }

      const rect = t.get();
      const idx = nearestHandle(rectCorners(rect), pos, canvas);
      if (idx >= 0) {
        const corners = rectCorners(rect);
        drag = { mode: "corner", idx, opposite: corners[(idx + 2) % 4], start: pos };
        setRectFromCorners(rect, drag.opposite, pos);
      } else if (insideRect(rect, pos)) {
        drag = { mode: "move", orig: { ...rect }, start: pos };
      } else {
        drag = { mode: "new", start: pos };
        setRectFromCorners(rect, pos, pos);
      }
    });

    canvas.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const t = TARGETS[target];
      if (t.canvas !== view) return;
      const pos = canvasNorm(canvas, e);
      if (t.kind === "corners") {
        movePoint(t, drag.idx, pos);
        return;
      }
      const rect = t.get();
      if (drag.mode === "corner") {
        setRectFromCorners(rect, drag.opposite, pos);
      } else if (drag.mode === "move") {
        const dx = pos[0] - drag.start[0], dy = pos[1] - drag.start[1];
        rect.x = Math.min(1 - drag.orig.width, Math.max(0, drag.orig.x + dx));
        rect.y = Math.min(1 - drag.orig.height, Math.max(0, drag.orig.y + dy));
      } else {
        setRectFromCorners(rect, drag.start, pos);
      }
    });

    const finish = () => {
      if (!drag) return;
      drag = null;
      renderNumericInputs();
    };
    canvas.addEventListener("pointerup", finish);
    canvas.addEventListener("pointercancel", finish);
  }
}

function nearestForced(points, pos) {
  // No handle within grab radius: still move the closest one.
  let best = 0, bestDist = Infinity;
  points.forEach(([x, y], i) => {
    const d = Math.hypot(x - pos[0], y - pos[1]);
    if (d < bestDist) { best = i; bestDist = d; }
  });
  return best;
}

function movePoint(t, idx, pos) {
  const points = t.get();
  points[idx] = [pos[0], pos[1]];
  t.set(points);
}

/* ---------------- overlay drawing ---------------- */

function drawLoop() {
  if (cal) {
    const view=TARGETS[target].canvas;
    if(view==="raw")drawRaw();
    else if(view==="p1_crop")drawCorners(1);
    else drawRois(1);
  }
  requestAnimationFrame(() => setTimeout(drawLoop, 100));
}

function syncCanvas(view) {
  const img = $(`img-${view}`);
  const canvas = $(`cv-${view}`);
  const w = img.clientWidth, h = img.clientHeight;
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, w, h);
  return [ctx, w, h];
}

function strokeRect(ctx, rect, w, h, color, active) {
  ctx.strokeStyle = color;
  ctx.lineWidth = active ? 3 : 1.5;
  ctx.setLineDash(active ? [] : [6, 4]);
  ctx.strokeRect(rect.x * w, rect.y * h, rect.width * w, rect.height * h);
  ctx.setLineDash([]);
}

function drawHandles(ctx, points, w, h) {
  ctx.fillStyle = ACCENT;
  ctx.strokeStyle = "#101216";
  for (const [x, y] of points) {
    ctx.beginPath();
    ctx.arc(x * w, y * h, 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.stroke();
  }
}

function drawRaw() {
  const [ctx, w, h] = syncCanvas("raw");
  strokeRect(ctx, cal.regions.player1.source_rect, w, h, P1, target === "p1_rect");
  if (target === "p1_rect") drawHandles(ctx, rectCorners(cal.regions.player1.source_rect), w, h);
}

function drawCorners(player) {
  const [ctx, w, h] = syncCanvas(`p${player}_crop`);
  const points = cal.regions[`player${player}`].homography_points;
  if (!points || !points.length) return;
  const color = player === 1 ? P1 : P2;
  ctx.strokeStyle = ACCENT;
  ctx.fillStyle = color;
  if (points.length === 4) {
    ctx.beginPath();
    points.forEach(([x, y], i) => i ? ctx.lineTo(x * w, y * h) : ctx.moveTo(x * w, y * h));
    ctx.closePath();
    ctx.lineWidth = 2;
    ctx.stroke();
  }
  points.forEach(([x, y], i) => {
    ctx.beginPath();
    ctx.arc(x * w, y * h, 9, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#101216";
    ctx.font = "bold 11px monospace";
    ctx.fillText(String(i + 1), x * w - 3, y * h + 4);
    ctx.fillStyle = color;
  });
  if (target === `p${player}_corners`) drawHandles(ctx, points, w, h);
}

const ROI_KEYS = { board_region:"board", eddie_region: "eddie", card_play_region: "card", fixer_region: "fixer", gig_region: "gig", legend_region: "legend" };

function drawRois(player) {
  const [ctx, w, h] = syncCanvas(`p${player}_corrected`);
  const regions = showcaseMode ? {board_region:cal.cameras.showcase_board_region} : cal.regions[`player${player}`].regions;
  const colors = { card_play_region: ACCENT, fixer_region: P1, gig_region: P2, legend_region: "#c064ff" };
  for (const [name, rect] of Object.entries(regions)) {
    const id = `p${player}_${ROI_KEYS[name] || name}`;
    if (guideTargets && !guideTargets.includes(id)) continue;
    const active = target === id;
    strokeRect(ctx, rect, w, h, colors[name] || "#ccc", active);
    ctx.fillStyle = colors[name] || "#ccc";
    ctx.font = "11px monospace";
    ctx.fillText(name.replace("_region", ""), rect.x * w + 4, rect.y * h + 12);
    if (active) drawHandles(ctx, rectCorners(rect), w, h);
  }
}

/* ---------------- save / reload ---------------- */
async function saveSetup() {
  if (target === 'p1_corners') {
    const status = await fetch('/api/vision/status').then(r=>r.json());
    const resolution = status.resolution || cameraResolution;
    if (!resolution) throw Error('Start your camera before saving perspective.');
    cal.cameras.corrected_size = CameraSetupGeometry.correctedSize(
      resolution, cal.regions.player1.source_rect, cal.regions.player1.homography_points);
  }
  await api('/api/vision/calibration', {cameras:cal.cameras, regions:cal.regions});
  setSaveStatus('Camera setup saved.');
}


$("btn-save").addEventListener("click", async () => {
  try { await saveSetup(); } catch(error) { setSaveStatus(error.message,true); }
});

$("btn-reload").addEventListener("click", async () => {
  await loadCalibration();
  setSaveStatus("Unsaved changes discarded.");
});

/* ---------------- boot ---------------- */

initTargetSelect();
initCanvases();
loadCalibration().then(async () => {
  try{const cfg=await (await fetch('/api/config')).json();showcaseMode=cfg.activity_mode==='showcase';}catch{}
  applySetupActivity();
  const src = cal.cameras.source || {};
  $("src-type").value = src.type || "camera";
  $("capture-mode").value = src.capture_mode || "auto";
  $("exposure-mode").value = src.exposure_mode || "motion";
  $("src-device").value = src.type !== "camera" && src.type ? (src.path || "") : (src.path || String(src.index ?? 0));
  $("src-type").dispatchEvent(new Event("change"));
  refreshSources();
  window.initCameraGuide({
    getActivity:()=>showcaseMode?"showcase":"play",
    selectTarget(id){
      target=id;$("target-select").value=id;
      if(id==='p1_corners'&&!cal.regions.player1.homography_points){
        cal.regions.player1.homography_points=[[0.05,0.05],[0.95,0.05],[0.95,0.95],[0.05,0.95]];
      }
      renderNumericInputs();
    },
    save:saveSetup,
    setVisibleTargets(ids){guideTargets=ids;},
    async cameraReady(){const r=await fetch('/api/vision/status');if(!r.ok)return false;const s=await r.json();return s.running&&!s.paused&&s.resolution&&s.fps>0;}
  });
}).catch(error=>setSaveStatus('Could not load camera setup. Reload this page to try again.',true));
attachStreams();

pollStatus();
setInterval(pollStatus, 1500);
drawLoop();

async function refreshSources(){
 try{
  const data=await (await fetch('/api/vision/sources')).json(),select=$("camera-list");
  select.replaceChildren(new Option('Enter device manually…',''),...data.devices.map(d=>new Option(d.name+' ('+d.path+')',d.path)));
  const current=$("src-device").value;select.value=/^\d+$/.test(current)?'/dev/video'+current:current;
 }catch(error){$("vision-status").textContent='Could not list cameras: '+error.message;}
}
$("camera-list").onchange=()=>{if($("camera-list").value){$("src-type").value='camera';$("src-device").value=$("camera-list").value;}};
$("refresh-sources").onclick=refreshSources;
refreshSources();

async function saveVisionImage(){
  try{
    const current=await (await fetch('/api/vision/calibration')).json();
    current.cameras.vision_adjustments={brightness:Number($('vision-brightness').value),contrast:Number($('vision-contrast').value)};
    await api('/api/vision/calibration',{cameras:current.cameras});
    cal.cameras.vision_adjustments=current.cameras.vision_adjustments;
    setSaveStatus('Recognition image saved.');
  }catch(error){setSaveStatus(error.message,true);}
}
for(const key of ['brightness','contrast']){
  $('vision-'+key).oninput=()=>{$(key+'-value').textContent=$('vision-'+key).value;};
  $('vision-'+key).onchange=saveVisionImage;
}
$('vision-reset').onclick=()=>{
  for(const key of ['brightness','contrast']){$('vision-'+key).value=key==='contrast'?1:0;$(key+'-value').textContent=$('vision-'+key).value;}
  saveVisionImage();
};

$('rotate-source-180').onchange=async()=>{
  const toggle=$('rotate-source-180');toggle.disabled=true;
  try{
    const response=await fetch('/api/vision/calibration');
    if(!response.ok)throw new Error('Could not load camera settings');
    const current=await response.json();
    current.cameras.rotate_source_180=toggle.checked;
    const saved=await api('/api/vision/calibration',{cameras:current.cameras});
    cal.cameras=saved.cameras;
    $('rotation-status').textContent='Rotation saved. Check and reposition your board areas.';
  }catch(error){
    toggle.checked=cal.cameras.rotate_source_180===true;
    $('rotation-status').textContent='Could not save rotation: '+error.message;
  }finally{toggle.disabled=false;}
};

function applySetupActivity(){
 initTargetSelect();
 if(showcaseMode&&!['p1_rect','p1_corners','p1_board'].includes(target))target='p1_board';
 if(!showcaseMode&&target==='p1_board')target='p1_card';
 $('target-select').value=target;
 let panel=$('showcase-detection-settings');
 if(!panel){panel=document.createElement('section');panel.id='showcase-detection-settings';panel.innerHTML='<label><input type="checkbox" id="showcase-detect"> Show latest detected card</label><p>Cards inside your board area can appear on the right. Click a deck card to select it manually; a new detection takes over. This does not change your match zones.</p>';document.querySelector('.guide-launch').after(panel);$('showcase-detect').onchange=async()=>{try{await api('/api/showcase/present',{action:'detection',enabled:$('showcase-detect').checked});}catch(e){$('showcase-detect').checked=!$('showcase-detect').checked;}};}
 panel.hidden=!showcaseMode;
 if(showcaseMode)fetch('/api/showcase').then(r=>r.json()).then(d=>{$('showcase-detect').checked=d.detect_latest;}).catch(()=>{});
 if(cal)renderNumericInputs();
}
window.addEventListener('activity-mode-change',e=>{showcaseMode=e.detail==='showcase';if(cal)applySetupActivity();});
