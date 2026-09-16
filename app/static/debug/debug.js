/* Vision debug: live pipeline views + capture controls. Read-only otherwise. */
"use strict";

const $ = (id) => document.getElementById(id);
const STREAMS = {
  raw: "/api/vision/frame/raw.jpg?rois=1",
  p1_crop: "/api/vision/frame/p1_crop.jpg?rois=0",
  p1_corrected: "/api/vision/frame/p1_corrected.jpg?rois=1",
};

function attachStreams() {
  for (const [view, url] of Object.entries(STREAMS)) {
    $(`img-${view}`).src = url + "&t=" + Date.now();
  }
}

async function api(path, body) {
  const opts = body !== undefined
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : { method: "POST" };
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) { /* keep */ }
    flash(detail, true);
    throw new Error(detail);
  }
  return res.json();
}

function flash(msg, isError = false) {
  const el = $("st-msg");
  el.textContent = msg;
  el.style.color = isError ? "#ff4d5e" : "#3ddc84";
  clearTimeout(el._t);
  el._t = setTimeout(() => (el.textContent = ""), 4000);
}

async function pollStatus() {
  try {
    const res = await fetch("/api/vision/status");
    const st = await res.json();
    const run = $("st-run");
    if (st.running && st.paused) { run.textContent = "PAUSED"; run.className = "paused"; }
    else if (st.running) { run.textContent = "RUNNING"; run.className = "running"; }
    else if (st.error) { run.textContent = "ERROR"; run.className = "error"; }
    else { run.textContent = "STOPPED"; run.className = ""; }
    $("st-fps").textContent = st.running ? `${st.fps} fps` : "";
    $("st-res").textContent = st.resolution ? `${st.resolution[0]}x${st.resolution[1]}` : "";
    $('st-format').textContent=st.running?`${st.backend||'unknown'} · ${st.pixel_format||'unknown'} · driver reports ${st.native_fps} FPS${st.exposure!=null?' · exposure '+st.exposure+' (log₂ seconds), auto '+st.auto_exposure:''}`:'';
    const feeds=Object.entries(st.broadcast_feeds||{});
    $('feed-performance').textContent=feeds.length?feeds.map(([area,feed])=>`${area}: ${feed.fps} feed FPS · ${feed.encode_ms} ms processing · ${feed.users} viewers`).join(' | '):'Open a preview or OBS source to measure broadcast processing.';
    const src = st.source || {};
    $("st-src").textContent = src.type
      ? `src: ${src.type === "video" ? src.path : (src.path || `camera ${src.index}`)}`
      : "";
    if (st.error) $("st-src").textContent = st.error;
    $("btn-pause").disabled = !st.running || st.paused;
    $("btn-resume").disabled = !st.running || !st.paused;
    $("btn-stop").disabled = !st.running;
  } catch (e) {
    $("st-run").textContent = "SERVER UNREACHABLE";
    $("st-run").className = "error";
  }
}

$("btn-start").addEventListener("click", async () => {
  await api("/api/vision/start", {});   // uses the saved calibration source
  attachStreams();
  pollStatus();
});
$("btn-stop").addEventListener("click", async () => { await api("/api/vision/stop"); pollStatus(); });
$("btn-pause").addEventListener("click", async () => { await api("/api/vision/pause"); pollStatus(); });
$("btn-resume").addEventListener("click", async () => { await api("/api/vision/resume"); pollStatus(); });
$("btn-save-frame").addEventListener("click", async () => {
  const res = await api("/api/vision/save_frame", { view: $("save-view").value });
  flash(`Saved: ${res.saved}`);
});
$("btn-scan").addEventListener("click", async () => {
  const res = await api("/api/vision/scan");
  flash(res.actions.length ? res.actions.join(" · ") : "Scan: nothing to change");
});

/* ---------------- card detection (Milestone 3) ---------------- */

let cropTick = 0;
let tuningLoaded = false;
let recTuningLoaded = false;

function renderLegends(player, det) {
  const slots = det.legends?.[String(player)] || [];
  const threshold = det.recognition?.min_confidence ?? 0.45;
  const active = !!det.players?.[String(player)];
  const grid = $("legend-diagnostics-grid");
  if (!grid.children.length) {
    for (let i = 0; i < 3; i++) {
      const tile = document.createElement("article");
      const title = document.createElement("h3");title.textContent = "Legend " + (i + 1);
      const image = new Image();image.id = "legend-camera-" + i;image.alt = "Live webcam crop for legend " + (i + 1);
      const status = document.createElement("p");status.id = "legend-state-" + i;
      tile.append(title, image, status);grid.append(tile);
    }
  }
  $("legend-region-preview").src = "/api/vision/legend-region/1.jpg?t=" + cropTick++;
  const summary = [];
  for (let i = 0; i < 3; i++) {
    const finding = slots[i], match = finding?.match;
    let message = !active ? "Vision stopped" : !finding ? "Waiting for detection" :
      !finding.present ? "No card / dark region" : !finding.face_up ? "Face-down candidate" :
      match && match.confidence >= threshold ? "Accepted: " + match.name + " · " + Math.round(match.confidence * 100) + "%" :
      match ? "Rejected guess: " + match.name + " · " + Math.round(match.confidence * 100) + "% · retrying" :
      "Face-up candidate · awaiting identification";
    $("legend-state-" + i).textContent = message + (active && finding ? " · stable checks " + finding.streak : "");
    $("legend-camera-" + i).src = "/api/vision/legend-slots/1/" + i + ".jpg?t=" + cropTick++;
    summary.push((i + 1) + ": " + message);
  }
  $("legends-p" + player).textContent = summary.join(" · ");
  $("legend-diagnostics-status").textContent = "Acceptance threshold: " + Math.round(threshold * 100) + "%. Face-up / face-down is a visual estimate, not proof of card identity.";
}

function renderMatch(player, result, det) {
  const box = $(`match-p${player}`);
  const match = result && result.match;
  if (!match) {
    box.innerHTML = result && result.present
      ? `<span class="weak">recognition: ${det.recognizer_ready ? "no match yet" : "index building…"}</span>`
      : "";
    return;
  }
  const minConf = det.recognition ? det.recognition.min_confidence : 0.45;
  const confident = match.confidence >= minConf;
  const sub = match.subtitle ? ` · ${match.subtitle}` : "";
  box.innerHTML =
    `<span class="${confident ? "ok" : "weak"}">${(match.confidence * 100).toFixed(0)}%</span> ` +
    `<span class="name">${match.name}</span>${sub}` +
    `<br><span class="weak">inliers ${match.inliers}/${match.runner_up_inliers ?? 0} · votes ${match.votes ?? 0}` +
    ` · thumb ${match.thumb_score}${match.rotated ? " · rotated" : ""}` +
    `${match.source ? ` · via ${match.source}` : ""}${confident ? "" : " · below min confidence"}</span>`;
}

async function pollDetection() {
  try {
    const res = await fetch("/api/vision/detection");
    const det = await res.json();
    $("det-fps").textContent = det.fps ? `· ${det.fps} detections/s` : "";
    if (!tuningLoaded && det.config) {
      tuningLoaded = true;
      for (const input of $("tuning").querySelectorAll("input")) {
        if (det.config[input.name] !== undefined) input.value = det.config[input.name];
      }
    }
    if (!recTuningLoaded && det.recognition) {
      recTuningLoaded = true;
      for (const input of $("rec-tuning").querySelectorAll("input")) {
        const value = det.recognition[input.name];
        if (value === undefined) continue;
        if (input.type === "checkbox") input.checked = !!value; else input.value = value;
      }
    }
    $("rec-ready").textContent = det.recognizer_ready ? "· index ready" : "· index building…";
    for (const player of [1]) {
      const result = det.players[String(player)];
      const stats = $(`stats-p${player}`);
      const visible=result?.visible_cards||[];
      $("visible-play-cards").textContent=(result?.candidates??0)+" candidates in play area · recognized: "+
        (visible.length?visible.map(card=>card.name+" ("+Math.round(card.confidence*100)+"%)").join(", "):"none yet");
      renderMatch(player, result, det);
      renderLegends(player, det);
      if (!result) {
        $(
          "crop-p" + player).hidden = true;
        $("btn-crop-p" + player).disabled = true;
        $("btn-rec-p" + player).disabled = true;
        stats.innerHTML = `<div><dt>state</dt><dd class="no">vision stopped</dd></div>`;
        continue;
      }
      stats.innerHTML =
        `<div><dt>card present</dt><dd class="${result.present ? "yes" : "no"}">${result.present ? "YES" : "no"}</dd></div>` +
        `<div><dt>stable</dt><dd class="${result.stable ? "yes" : "no"}">${result.stable ? "YES" : "no"} (${result.stable_frames}/${det.config.stable_frames})</dd></div>` +
        `<div><dt>area (roi)</dt><dd>${result.area_frac ?? "—"}</dd></div>` +
        `<div><dt>area (view)</dt><dd>${result.view_area_frac ?? "—"}</dd></div>` +
        `<div><dt>detect time</dt><dd>${result.ms} ms</dd></div>`;
      $("crop-p" + player).hidden = !result.present;
      $("btn-crop-p" + player).disabled = !result.present;
      $("btn-rec-p" + player).disabled = !result.present;
      if (result.present) {
        // Refresh the crop image (cache-busted) only while a card is present.
        $(`crop-p${player}`).src = `/api/vision/detection/crop/${player}.jpg?t=${cropTick++}`;
      }
      // ROI candidate view: grey outlines rejected, green = accepted quad.
      $(`detdbg-p${player}`).src = `/api/vision/detection/debug/${player}.jpg?t=${cropTick++}`;
    }
  } catch (e) { /* status poll reports unreachable */ }
}

$("tuning").addEventListener("submit", async (e) => {
  e.preventDefault();
  const detection = {};
  for (const input of $("tuning").querySelectorAll("input")) {
    detection[input.name] = parseFloat(input.value);
  }
  const cal = await (await fetch("/api/vision/calibration")).json();
  await api("/api/vision/calibration", { cameras: { ...cal.cameras, detection } });
  $("tuning-msg").textContent = "Applied (live)";
  setTimeout(() => ($("tuning-msg").textContent = ""), 3000);
});

$("rec-tuning").addEventListener("submit", async (e) => {
  e.preventDefault();
  const recognition = {};
  for (const input of $("rec-tuning").querySelectorAll("input")) {
    recognition[input.name] = input.type === "checkbox" ? input.checked : parseFloat(input.value);
  }
  const cal = await (await fetch("/api/vision/calibration")).json();
  await api("/api/vision/calibration", { cameras: { ...cal.cameras, recognition } });
  $("rec-tuning-msg").textContent = "Applied (live)";
  setTimeout(() => ($("rec-tuning-msg").textContent = ""), 3000);
});

for (const player of [1]) {
  $(`btn-rec-p${player}`).addEventListener("click", async () => {
    try {
      const res = await api(`/api/vision/recognize/${player}`, {});
      const m = res.match;
      flash(m
        ? `P${player}: ${m.name} ${(m.confidence * 100).toFixed(0)}%${res.applied ? " → latest card" : res.confident ? " (already latest)" : " (below min confidence)"}`
        : `P${player}: no match`);
    } catch (err) {
      flash(`Recognize failed: ${err.message || err}`);
    }
  });
}

$("btn-crop-p1").addEventListener("click", async () => {
  const res = await api("/api/vision/save_crop", { player: 1 });
  flash(`Saved: ${res.saved}`);
});


attachStreams();
setInterval(attachStreams, 1000);
pollStatus();
setInterval(pollStatus, 1000);
pollDetection();
setInterval(pollDetection, 500);


let artworkCapture=null,artSearchVersion=0;
$('art-capture').onclick=async()=>{
  $('art-capture').disabled=true;
  try{const data=await api('/api/vision/save_crop',{player:1});artworkCapture=data.saved.split('/').pop();$('art-sample').src='/api/vision/artwork/capture/'+encodeURIComponent(artworkCapture);$('art-sample').hidden=false;$('art-message').textContent='Check this frozen crop contains the entire upright card before labeling it.';}
  catch(error){$('art-message').textContent=error.message;artworkCapture=null;}
  finally{$('art-capture').disabled=false;$('art-learn').disabled=!artworkCapture||!$('art-card').value;}
};
$('art-search').oninput=async()=>{
  const version=++artSearchVersion;
  try{const response=await fetch('/api/cards/search?q='+encodeURIComponent($('art-search').value)+'&limit=30');if(!response.ok)throw Error('Card search failed');const data=await response.json();if(version!==artSearchVersion)return;
    const blank=document.createElement('option');blank.value='';blank.textContent='Choose the exact card…';
    $('art-card').replaceChildren(blank,...data.results.map(card=>{const option=document.createElement('option');option.value=card.id;option.textContent=card.name+(card.subtitle?' — '+card.subtitle:'');return option;}));$('art-learn').disabled=true;
  }catch(error){$('art-message').textContent=error.message;}
};
$('art-card').onchange=()=>{$('art-learn').disabled=!artworkCapture||!$('art-card').value;};
$('art-learn').onclick=async()=>{
  $('art-learn').disabled=true;$('art-message').textContent='Learning artwork…';
  try{const data=await api('/api/vision/artwork/learn',{card_id:$('art-card').value,capture:artworkCapture});$('art-message').textContent=data.learned+': '+data.message;artworkCapture=null;}
  catch(error){$('art-message').textContent=error.message;$('art-learn').disabled=false;}
};


async function pollArtworkDownload(){
 try{
  const response=await fetch('/api/cards/artwork/status');
  if(!response.ok)throw Error('Artwork status unavailable');
  const data=await response.json();
  $('download-artwork').disabled=data.running;
  $('update-catalog').disabled=data.running;
  $('download-artwork-status').textContent=data.message+' '+(data.added ? data.added+' new cards added · ' : '')+data.completed+'/'+data.total+' cards checked · '+data.downloaded+' images downloaded'+(data.finished_at?' · Last finished '+new Date(data.finished_at).toLocaleString():'')+(data.errors.length?' · '+data.errors.length+' errors: '+data.errors.slice(0,3).join('; '):'');
 }catch(error){$('download-artwork-status').textContent=error.message;}
}
async function startCardDownload(endpoint){
 $('download-artwork').disabled=true;
 $('update-catalog').disabled=true;
 try{await api(endpoint,{});await pollArtworkDownload();}
 catch(error){$('download-artwork-status').textContent=error.message;$('download-artwork').disabled=false;$('update-catalog').disabled=false;}
}
$('download-artwork').onclick=()=>startCardDownload('/api/cards/artwork/download');
$('update-catalog').onclick=()=>startCardDownload('/api/cards/catalog/update');
pollArtworkDownload();setInterval(pollArtworkDownload,3000);
