"use strict";
const $=id=>document.getElementById(id);
let state=null,config={},searchVersion=0,searchTimer;
const gigControls=initGigControls({request:(id,value)=>api("/solo/gigs/"+id,{value}),notice});
function notice(message){$("notice").textContent=message;}
async function api(path,body){
 const response=await fetch("/api"+path,body===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
 const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:JSON.stringify(data.detail));
 if(data.state)receive(data);return data;
}
function action(fn){return async e=>{e?.preventDefault();try{await fn(e);}catch(error){notice(error.message);}};}
function receive(data){state=data.state;syncRememberedPlayerName(state);$("undo-card").disabled=!data.history.can_undo_card;$("undo-card").textContent="Previous play ("+(data.history.card_undo_count||0)+" / 100)";$("undo").disabled=!data.history.can_undo;$("redo").disabled=!data.history.can_redo;render();}
function render(){
 if(!state)return;
 const card=state.latest_cards["1"];
 $("current-name").textContent=card?.name||"Waiting for your first play";
 $("current-source").textContent=card?(card.source==="vision"?"Recognized from webcam":"Manually selected"):"Start your webcam or choose a card above.";
 $("current-art").hidden=!card?.image;if(card?.image)$("current-art").src=card.image;
 if(document.activeElement!==$("player-name"))$("player-name").value=state.match.player1_name;
 renderLegends();
 gigControls.render(state.dice);
}
function showConfig(){
 gigControls.setTheme(config.overlay_theme);
 $("show-legends").checked=config.show_legends!==false;
 $("show-gigs").checked=!!config.show_dice;$("show-art").checked=!!config.show_card_art;
}
for(const [id,key] of [["show-legends","show_legends"],["show-gigs","show_dice"],["show-art","show_card_art"]]){
 $(id).onchange=action(async()=>{const previous=config[key];try{config=await api("/config",{config:{...config,[key]:$(id).checked}});showConfig();}catch(e){config[key]=previous;showConfig();throw e;}});
}
$("search").oninput=()=>{
 clearTimeout(searchTimer);const version=++searchVersion;const query=$("search").value.trim();
 $("results").replaceChildren();if(!query)return;
 searchTimer=setTimeout(action(async()=>{
  const data=await api("/cards/search?q="+encodeURIComponent(query)+"&limit=12");if(version!==searchVersion)return;
  $("results").replaceChildren();
  for(const card of data.results){
   const button=document.createElement("button");const text=document.createElement("span");text.textContent=card.name+(card.subtitle?" — "+card.subtitle:"");
   if(card.image){const image=new Image();image.src=card.image;image.alt="";button.append(image);}
   button.append(text);button.onclick=action(async()=>{await api("/card/latest",{player:1,card_id:card.id});++searchVersion;$("results").replaceChildren();$("search").value="";notice("Latest card updated.");});$("results").append(button);
  }
  if(!data.results.length)$("results").textContent="No matching cards.";
 }),180);
};
$("name-form").onsubmit=action(async()=>{const data=await api("/match/names",{player1_name:$("player-name").value});rememberPlayerName(data.state.match.player1_name);notice("Name saved on this browser.");});
$("undo").onclick=action(()=>api("/undo",{}));$("redo").onclick=action(()=>api("/redo",{}));
$("clear").onclick=action(()=>api("/solo/card/clear",{}));
$("reset").onclick=action(async()=>{await api("/solo/match/new",{});notice("New match started. Cards, legends, and gigs cleared. Undo restores the previous match. Card tracking continues automatically.");});
$("camera").onclick=action(async()=>{await api("/vision/start",{});await status();});
$("stop").onclick=action(async()=>{await api("/vision/stop",{});await status();});
$("overlay-url").value=location.origin+"/broadcast/live";
$("copy").onclick=action(async()=>{try{await navigator.clipboard.writeText($("overlay-url").value);notice("OBS URL copied.");}catch{$("overlay-url").select();notice("Select and copy the highlighted OBS URL.");}});
async function status(){
 try{const data=await api("/vision/status");$("vision").textContent=data.error?"Camera: "+data.error:data.running?"Webcam running"+(data.paused?" · paused":"")+" · "+data.fps+" fps":"Webcam stopped · configure your board in Camera setup.";}catch{$("vision").textContent="Camera status unavailable.";}
}
function connect(){
 const ws=new WebSocket((location.protocol==="https:"?"wss://":"ws://")+location.host+"/ws");
 ws.onopen=()=>{playerNameInitialized=false;api("/config").then(data=>{config=data;showConfig();}).catch(e=>notice(e.message));};
 ws.onmessage=e=>{const data=JSON.parse(e.data);if(data.state)receive(data);if(data.config){config=data.config;showConfig();}};
 ws.onclose=()=>{setTimeout(connect,1500);};
}
connect();status();setInterval(status,5000);

function renderLegends(){
 $("legend-slots").replaceChildren();
 for(let slot=0;slot<3;slot++){
  const legend=state.legends["1"][slot];
  const row=document.createElement("div");row.className="legend-row";
  const image=new Image();image.src=legend.revealed&&legend.image?legend.image:"/static/assets/card-back.webp";image.alt="";
  const description=document.createElement("span");
  description.textContent="Legend "+(slot+1)+" · "+(legend.name||"Unassigned")+" · "+(legend.revealed?"Flipped":"Face down");
  const flip=document.createElement("button");flip.textContent=legend.revealed?"Turn face down":"Flip legend";flip.disabled=!legend.card_id;
  flip.onclick=action(()=>api("/legends/1/"+slot,{revealed:!legend.revealed}));
  const clear=document.createElement("button");clear.textContent="Clear";clear.disabled=!legend.card_id;
  clear.onclick=action(()=>api("/legends/1/"+slot,{card_id:""}));
  row.append(image,description,flip,clear);$("legend-slots").append(row);
 }
}
let legendSearchVersion=0,legendTimer;
$("legend-search").oninput=()=>{
 clearTimeout(legendTimer);const version=++legendSearchVersion,query=$("legend-search").value.trim();
 $("legend-results").replaceChildren();if(!query)return;
 legendTimer=setTimeout(action(async()=>{
  const data=await api("/cards/search?type=Legend&limit=12&q="+encodeURIComponent(query));
  if(version!==legendSearchVersion)return;
  $("legend-results").replaceChildren();
  for(const card of data.results){
   const button=document.createElement("button");button.textContent=card.name+(card.subtitle?" — "+card.subtitle:"");
   button.onclick=action(async()=>{
    // Clear any previous reveal before assigning another card to this slot.
    await api("/solo/legends/"+$("legend-slot").value,{card_id:card.id});
    ++legendSearchVersion;$("legend-results").replaceChildren();$("legend-search").value="";
    notice("Legend assigned face down. Flip it when revealed.");
   });
   $("legend-results").append(button);
  }
  if(!data.results.length)$("legend-results").textContent="No matching legends.";
 }),180);
};

$("undo-card").onclick=action(()=>api("/solo/card/undo",{}));
