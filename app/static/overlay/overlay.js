"use strict";
const $=id=>document.getElementById(id);
const DIE_ORDER = ["d4", "d6", "d8", "d10", "d12", "d20"];
const DIE_SIDES = { d4: 4, d6: 6, d8: 8, d10: 10, d12: 12, d20: 20 };
/* Die silhouettes as drawn in the Cyberpunk TCG rulebook (100x100 viewBox):
 * d4 narrow shield, d6 square, d8 tall hexagon, d10 diamond, d12 decagon,
 * d20 hexagon with a faint ghost hexagon behind it. */
const DIE_POLYGONS = {
  d4: "50,4 80,18 80,82 50,96 20,82 20,18",
  d6: "14,14 86,14 86,86 14,86",
  d8: "50,4 84,24 84,76 50,96 16,76 16,24",
  d10: "50,4 90,50 50,96 10,50",
  d12: "50.0,6.0 75.9,14.4 91.8,36.4 91.8,63.6 75.9,85.6 50.0,94.0 24.1,85.6 8.2,63.6 8.2,36.4 24.1,14.4",
  d20: "50,6 88,28 88,72 50,94 12,72 12,28",
};
const DIE_GHOSTS = { d20: "28,10 72,10 94,50 72,90 28,90 6,50" };

function dieShapeSVG(type) {
  const ghost = DIE_GHOSTS[type]
    ? `<polygon class="ghost" points="${DIE_GHOSTS[type]}"></polygon>` : "";
  return `<svg class="die-shape" viewBox="0 0 100 100" aria-hidden="true">${ghost}` +
    `<polygon class="body" points="${DIE_POLYGONS[type]}"></polygon></svg>`;
}

let gigKey="",previousDice=new Map();
function fitMinimalOverlay(){
 const rail=$("rail"),requested=Number(config.overlay_scale??100);
 const scale=Number.isFinite(requested)?Math.max(25,Math.min(150,requested))/100:1;
 rail.style.transform="scale("+Math.min(scale,Math.max(.1,(innerWidth-40)/(rail.offsetWidth||1)),Math.max(.1,(innerHeight-40)/(rail.offsetHeight||1)))+")";
}
addEventListener("resize",fitMinimalOverlay);
let state=null, config={show_dice:false,show_card_art:true,show_roll_values:true}, cardKey="";
function render(){
 applyOverlayTheme(config);
 const position=["bottom-right","bottom-left","top-right","top-left"].includes(config.minimal_position)?config.minimal_position:"bottom-right";
 $("rail").dataset.position=position;

 if(!state)return;
 const card=state.latest_cards["1"];
 $("latest").hidden=!card?.image || !config.show_card_art;
 if(card){
  const key=config.show_card_art ? card.image+"|"+card.timestamp : "";
  if(key!==cardKey){cardKey=key;const art=$("art");art.replaceChildren();
   if(config.show_card_art&&card.image){const img=new Image();img.alt=card.name;img.onload=()=>glitchCard(img);img.src=card.image;img.onerror=()=>{img.remove();$("latest").hidden=true;};art.append(img);}
  }
 }else{$("art").replaceChildren();cardKey="";}
 const legends=state.legends?.["1"] || [];
 $("legends").hidden=config.show_legends===false;
 $("hud").hidden=config.show_legends===false&&!config.show_dice;
 $("legend-count").textContent=legends.filter(l=>l.revealed).length+" / 3 FLIPPED";
 renderLegendCards($("legend-list"),legends);
 const gigs=Object.values(state.dice).filter(d=>d.location==="p1_gig");
 $("gigs").hidden=!config.show_dice;
 $("captured-gigs").hidden=!config.show_dice||(config.hide_empty_captured_gigs!==false&&!gigs.some(d=>d.owner===2));
 $("total").textContent=gigs.reduce((sum,d)=>sum+(d.last_roll||0),0)+" CRED";
 const key=JSON.stringify([state.dice,config.show_roll_values]);
 if(key!==gigKey){
  gigKey=key;
  const dice=Object.values(state.dice);
  const slots=DIE_ORDER.map(type=>dice.find(d=>d.owner===1&&d.type===type)||{owner:1,type});
  const captured=DIE_ORDER.map(type=>gigs.find(d=>d.owner===2&&d.type===type)||{owner:2,type});
  const makeDie=d=>{
   const active=d.location==="p1_gig";
   const el=document.createElement("div");
   el.className="gslot own"+(active?" active":"")+(d.owner===2?" captured":"");
   const identity=d.owner+":"+d.type,value=JSON.stringify([d.location,d.last_roll]);
   if(previousDice.has(identity)&&previousDice.get(identity)!==value)el.classList.add("changed");
   previousDice.set(identity,value);
   el.title=(d.owner===2?"Stolen ":"")+d.type.toUpperCase()+(active?" gig":" available");
   el.innerHTML=dieShapeSVG(d.type);
   const label=document.createElement("span");
   label.textContent=active&&d.last_roll!=null?d.last_roll:d.type.toUpperCase();
   el.append(label);return el;
  };
  $("gig-list").replaceChildren(...slots.map(makeDie));
  $("captured-list").replaceChildren(...captured.map(makeDie));

 }

 fitMinimalOverlay();
}
function connect(){
 const ws=new WebSocket((location.protocol==="https:"?"wss://":"ws://")+location.host+"/ws");
 ws.onopen=async()=>{try{config=await (await fetch("/api/config")).json();render();}catch{}};
 ws.onmessage=e=>{const data=JSON.parse(e.data);if(data.state)state=data.state;if(data.config)config=data.config;render();};
 ws.onclose=()=>setTimeout(connect,1500);
}
connect();
