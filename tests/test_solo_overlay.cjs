/* Run the real overlay renderer against state transitions, without a browser. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
class Element {
  constructor(){this.classList={toggle(){},remove(){},add(){}};this.style={};this.dataset={};this.children=[];this.textContent="";this.hidden=false;this.className="";}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;this.textContent="";}
  remove(){}
}
const elements = new Map();
const context = vm.createContext({
 document:{getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},createElement(){return new Element();}},
 Image:Element, WebSocket:class {}, location:{protocol:"http:",host:"localhost"},
 addEventListener(){}, innerWidth:1920,innerHeight:1080, setTimeout(){}, fetch(){throw new Error("Unexpected fetch");}
});
vm.runInContext(fs.readFileSync(require("node:path").join(__dirname,"../app/static/shared/card-effects.js"),"utf8"),context);
vm.runInContext(fs.readFileSync(require("node:path").join(__dirname,"../app/static/overlay/overlay.js"),"utf8"),context);
function render(state,config={show_dice:true,show_card_art:true,show_roll_values:true}){
 context.testState=state;context.testConfig=config;
 vm.runInContext("state=testState;config=testConfig;render()",context);
}
const state={match:{player1_name:"V"},latest_cards:{"1":null,"2":{name:"Opponent secret"}},dice:{
 own:{owner:1,type:"d6",location:"p1_gig",last_roll:4},
 hidden:{owner:2,type:"d20",location:"p2_gig",last_roll:19},
 stolen:{owner:2,type:"d8",location:"p1_gig",last_roll:7}
}};
render(state);
assert.equal(elements.get("latest").hidden,true);
assert.equal(elements.get("total").textContent,"11 CRED");
assert.equal(elements.get("gig-list").children.length,6);
assert.equal(elements.get("captured-list").children[2].className,"gslot own active captured");
assert.equal(elements.get("captured-list").children[2].children[0].textContent,7);
assert(elements.get("gig-list").children.every(el=>el.innerHTML.includes("die-shape")));
assert.equal(elements.get("gig-list").children[0].children[0].textContent,"D4");
state.latest_cards["1"]={name:"Johnny",subtitle:"Rocking Renegade",image:"/cards/images/test.webp",timestamp:"1"};
render(state);
assert.equal(elements.get("latest").hidden,false);
assert.equal(elements.has("name"),false,"Latest card has no name caption");
assert.equal(elements.has("player"),false,"Latest card has no player label");
const firstImage=elements.get("art").children[0];
render(state);
assert.equal(elements.get("art").children[0],firstImage,"Unrelated state must not replay the card animation");
render(state,{show_dice:false,show_card_art:false});
assert.equal(elements.get("gigs").hidden,true);
assert.equal(elements.get("art").children.length,0);
state.dice.stolen.location="p2_fixer";
render(state);
assert.equal(elements.get("gig-list").children.length,6);
assert.equal(elements.get("total").textContent,"4 CRED");
assert.equal(elements.get("captured-list").children.length,6);
assert(elements.get("captured-list").children.every(el=>el.className==="gslot own captured"));
assert.deepEqual(elements.get("captured-list").children.map(el=>el.children[0].textContent),["D4","D6","D8","D10","D12","D20"]);
assert.equal(elements.get("gigs").hidden,false);
state.latest_cards["1"]=null;render(state);
assert.equal(elements.get("latest").hidden,true);
console.log("Overlay tests passed: latest card, stable image, hidden opponent gigs, stolen/returned gigs, optional panels.");

state.legends={"1":[{name:"Secret",image:"/secret.webp",revealed:false},{name:"Revealed",image:"/revealed.webp",revealed:true},{}],
"2":[{name:"Opponent legend",image:"/opponent.webp",revealed:true}]};
render(state);
assert.equal(elements.get("legend-count").textContent,"1 / 3 FLIPPED");
assert.equal(elements.get("legend-list").children[0].children[0].src,"/static/assets/card-back.webp");
assert.equal(elements.get("legend-list").children[0].children[0].alt,"Face-down legend 1");
assert.equal(elements.get("legend-list").children[1].children[0].src,"/revealed.webp");
state.legends["1"][1].revealed=false;
render(state);
assert.equal(elements.get("legend-count").textContent,"0 / 3 FLIPPED");
assert.equal(elements.get("legend-list").children[1].children[0].src,"/static/assets/card-back.webp");
render(state,{show_legends:false});
assert.equal(elements.get("legends").hidden,true);
const html=fs.readFileSync(require("node:path").join(__dirname,"../app/static/overlay/index.html"),"utf8");
const latest=html.split('<section id="latest"')[1].split("</section>")[0];
assert(!latest.includes("eyebrow")&&!latest.includes("caption")&&!latest.includes('id="name"'));
console.log("Legend tests passed: hidden identity, flips, flip count, optional display, artwork-only latest card.");

render(state,{overlay_scale:65});
assert.equal(elements.get("rail").style.transform,"scale(0.65)");
render(state,{overlay_scale:999});
assert.equal(elements.get("rail").style.transform,"scale(1.5)");
render(state,{overlay_scale:"invalid"});
assert.equal(elements.get("rail").style.transform,"scale(1)");

for(const corner of ["bottom-right","bottom-left","top-right","top-left"]){render(state,{minimal_position:corner});assert.equal(elements.get("rail").dataset.position,corner);}
render(state,{minimal_position:"bad"});assert.equal(elements.get("rail").dataset.position,"bottom-right");
state.dice.stolen.location='p2_fixer';
render(state,{show_dice:true,hide_empty_captured_gigs:true,show_roll_values:false});
assert.equal(elements.get('captured-gigs').hidden,true);
assert.equal(elements.get('gig-list').children[1].children[0].textContent,4);
render(state,{show_dice:true,hide_empty_captured_gigs:false});
assert.equal(elements.get('captured-gigs').hidden,false);
state.dice.stolen.location='p1_gig';
render(state,{show_dice:true,hide_empty_captured_gigs:true});
assert.equal(elements.get('captured-gigs').hidden,false);
render(state,{show_dice:false,hide_empty_captured_gigs:false});
assert.equal(elements.get('captured-gigs').hidden,true);
