"use strict";
const $=id=>document.getElementById(id);
const fields=["broadcast_corrected","show_matched_art","show_card_art","show_legends","show_dice","hide_empty_captured_gigs","board_show_eddies","board_show_fixer"];
let config={},saving=false;
function render(){
 $("minimal-position").value=config.minimal_position||"bottom-right";
 $("full-board-settings").hidden=config.overlay_style!=="board";
 $("minimal-settings").hidden=config.overlay_style==="board";
 $("overlay-theme").value=config.overlay_theme||"cyberpunk";
 $("preview-layout").value=config.overlay_style||"compact";
 $("preview-shell").classList.toggle("board-preview",config.overlay_style==="board");
 for(const key of fields){$(key).checked=["show_matched_art","broadcast_corrected"].includes(key)?config[key]===true:config[key]!==false;$(key).disabled=saving;}
 for(const id of ["overlay_scale","scale-number"]){$(id).value=config.overlay_scale??100;$(id).disabled=saving;}
 $("scale-reset").disabled=saving;
 for(const key of ["board_dice_mode","board_focus"]){$(key).value=config[key]||(key==="board_focus"?"balanced":"tracked");$(key).disabled=saving;}
}
async function saveScale(value){
 const scale=Number(value);
 if(!Number.isFinite(scale)||scale<25||scale>150){$("status").textContent="Enter a scale between 25 and 150%.";return;}
 saving=true;render();
 try{
  const response=await fetch("/api/config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({config:{overlay_scale:Math.round(scale)}})});
  if(!response.ok)throw new Error("Could not save scale");
  config=await response.json();$("status").textContent="Overlay scale saved: "+config.overlay_scale+"%.";
 }catch(error){$("status").textContent=error.message;}
 finally{saving=false;render();}
}
$("overlay_scale").oninput=()=>{$("scale-number").value=$("overlay_scale").value;};
$("overlay_scale").onchange=()=>saveScale($("overlay_scale").value);
$("scale-number").onchange=()=>saveScale($("scale-number").value);
$("scale-reset").onclick=()=>saveScale(100);
async function load(){
 try{const response=await fetch("/api/config");if(!response.ok)throw new Error("Settings unavailable");config=await response.json();render();$("status").textContent="Settings apply to OBS immediately.";}
 catch(error){$("status").textContent=error.message;}
}
for(const key of fields){
 $(key).disabled=true;
 $(key).onchange=async()=>{
  const next={[key]:$(key).checked};saving=true;render();
  try{const response=await fetch("/api/config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({config:next})});if(!response.ok)throw new Error("Could not save settings");config=await response.json();$("status").textContent="Saved.";}
  catch(error){$("status").textContent=error.message;}
  finally{saving=false;render();}
 };
}
$("obs-url").value=location.origin+"/broadcast/live";
$("copy").onclick=async()=>{
 try{await navigator.clipboard.writeText($("obs-url").value);$("status").textContent="OBS overlay link copied.";}
 catch{$("obs-url").select();$("status").textContent="Copy the selected OBS overlay URL.";}
};
function connect(){
 const ws=new WebSocket((location.protocol==="https:"?"wss://":"ws://")+location.host+"/ws");
 ws.onopen=load;
 ws.onmessage=e=>{const data=JSON.parse(e.data);if(data.config&&!saving){config=data.config;render();}};
 ws.onclose=()=>setTimeout(connect,1500);
}
connect();

for(const key of ["board_dice_mode","board_focus"]){
 $(key).onchange=async()=>{
  const next=$(key).value;saving=true;render();
  try{const response=await fetch("/api/config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({config:{[key]:next}})});if(!response.ok)throw new Error("Could not save board settings");config=await response.json();$("status").textContent="Board layout saved.";}
  catch(error){$("status").textContent=error.message;}
  finally{saving=false;render();}
 };
}
$("preview-layout").onchange=async()=>{
 const style=$("preview-layout").value;
 $("preview-layout").disabled=true;
 try{const response=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({config:{overlay_style:style}})});if(!response.ok)throw Error('Could not switch overlay');config=await response.json();render();$('status').textContent='Active overlay switched. OBS and virtual camera follow this selection.';}catch(error){$('status').textContent=error.message;render();}finally{$('preview-layout').disabled=false;}
};

$('overlay-theme').onchange=async()=>{
 const theme=$('overlay-theme').value;$('overlay-theme').disabled=true;
 try{const response=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({config:{overlay_theme:theme}})});if(!response.ok)throw Error('Could not save color scheme');config=await response.json();render();$('status').textContent='Color scheme saved.';}
 catch(error){$('status').textContent=error.message;render();}
 finally{$('overlay-theme').disabled=false;}
};

$('minimal-position').onchange=async()=>{
 const position=$('minimal-position').value;$('minimal-position').disabled=true;
 try{const response=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({config:{minimal_position:position}})});if(!response.ok)throw Error('Could not save position');config=await response.json();render();$('status').textContent='Stream position saved.';}
 catch(error){$('status').textContent=error.message;render();}
 finally{$('minimal-position').disabled=false;}
};
