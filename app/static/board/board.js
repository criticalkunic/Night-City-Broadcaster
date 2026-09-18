"use strict";
const $=id=>document.getElementById(id);
let state=null,config={},lastArt="",legendKey="",diceKey="";
function fit(){const scale=Math.min(innerWidth/1920,innerHeight/1080);$("stage").style.transform=`scale(${scale})`;}
addEventListener("resize",fit);fit();
function dieTile(d,active,stolen=false){
 const tile=document.createElement("div");tile.className="die"+(active?" active":"")+(stolen?" stolen":"");
 tile.title=(stolen?"Stolen ":"")+d.type.toUpperCase();tile.innerHTML=dieShapeSVG(d.type);
 const value=document.createElement("span");value.textContent=active&&d.last_roll!=null?d.last_roll:d.type.toUpperCase();tile.append(value);return tile;
}
function render(){
 applyOverlayTheme(config);
 if(!state)return;
 $("player-name").textContent=state.match.player1_name||"SOLO";
 $("match-status").textContent=state.awaiting_first_play&&!state.latest_cards?.["1"]?"READY FOR FIRST PLAY":state.match.started?"MATCH LIVE":"BOARD LIVE";
 const tracked=config.board_dice_mode!=="camera";
 $("cred").hidden=!tracked||config.show_dice===false;$("cred-value").textContent=state.match.player1_cred??0;
 const card=state.latest_cards?.["1"];
 const showArt=config.show_card_art!==false&&!!card?.image;
 $("latest").hidden=!showArt;
 const artKey=showArt?card.image+card.timestamp:"";
 if(artKey!==lastArt){lastArt=artKey;if(showArt){$("latest-art").onload=()=>glitchCard($("latest-art"));$("latest-art").src=card.image;}else $("latest-art").removeAttribute("src");}
 $("eddies").hidden=config.board_show_eddies===false;
 const dockEddies=!$("eddies").hidden;
 const footer=document.querySelector("footer"),side=$("side"),eddies=$("eddies");
 const stage=$("stage");
 document.querySelector('.economy').hidden=config.show_dice===false;
 document.querySelector('.reserve').hidden=config.board_show_fixer===false;
 document.querySelector('.legends').hidden=config.show_legends===false;
 footer.hidden=config.show_legends===false&&!dockEddies;
 stage.classList.toggle('no-gigs',config.show_dice===false);
 stage.classList.toggle('no-fixer',config.board_show_fixer===false);
 stage.classList.toggle('no-footer',footer.hidden);
 footer.classList.toggle('no-legends',config.show_legends===false);

 for(const selector of ['.economy','.reserve']){
  const panel=document.querySelector(selector);if(panel.parentElement!==stage)stage.append(panel);
 }
 stage.classList.toggle('camera-economy',!tracked);
 const destination=footer;
 if(eddies.parentElement!==destination)destination.append(eddies);
 footer.classList.toggle("with-eddies",dockEddies);
 side.hidden=!showArt;
 document.querySelector(".arena").classList.toggle("no-side",!showArt);
 $("stage").classList.toggle("play-focus",config.board_focus==="play");
 const legends=state.legends?.["1"]||[];
 const key=JSON.stringify(legends);
 if(key!==legendKey){
  legendKey=key;$("flips").textContent=legends.filter(l=>l.revealed).length+" / 3 FLIPPED";
  renderLegendCards($("legends"),legends,true);
 }
 const dice=Object.values(state.dice),own=DIE_ORDER.map(type=>dice.find(d=>d.owner===1&&d.type===type)||{type});
 const stolen=dice.filter(d=>d.owner===2&&d.location==="p1_gig").sort((a,b)=>DIE_ORDER.indexOf(a.type)-DIE_ORDER.indexOf(b.type));
 const dkey=JSON.stringify([dice,config.show_roll_values]);
 if(dkey!==diceKey){diceKey=dkey;
  $("gigs").replaceChildren(...own.map(d=>dieTile(d,d.location==="p1_gig")));
  $("stolen").replaceChildren(...DIE_ORDER.map(type=>{const d=stolen.find(d=>d.type===type);return dieTile(d||{type},!!d,true);}));
  $("fixer").replaceChildren(...own.filter(d=>d.location==="p1_fixer").map(d=>dieTile({...d,last_roll:null},true)));
 }
 $("gigs").hidden=!tracked;$("fixer").hidden=!tracked;$("stolen-row").hidden=!tracked||config.show_dice===false||(config.hide_empty_captured_gigs!==false&&!stolen.length);
 document.querySelector(".economy").classList.toggle("no-captured",$("stolen-row").hidden);
 $("gig-camera").hidden=tracked;$("fixer-camera").hidden=tracked;
 $("gig-caption").textContent=tracked?"YOUR GIGS":"YOUR GIGS + CAPTURED GIGS";
 $("reserve-count").textContent=tracked?own.filter(d=>d.location==="p1_fixer").length+" / 6 READY":"LIVE CAMERA";
}
$("latest-art").onerror=()=>{$("latest").hidden=true;};
for(const img of document.querySelectorAll("[data-feed]"))startBoardFeed(img,img.dataset.feed);
function connect(){
 const ws=new WebSocket((location.protocol==="https:"?"wss://":"ws://")+location.host+"/ws");
 ws.onopen=async()=>{try{const response=await fetch("/api/config");if(response.ok){config=await response.json();render();}}catch{}};
 ws.onmessage=e=>{const data=JSON.parse(e.data);if(data.state)state=data.state;if(data.config)config=data.config;render();};
 ws.onclose=()=>setTimeout(connect,1500);
}
connect();
