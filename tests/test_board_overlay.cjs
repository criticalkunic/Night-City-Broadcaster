const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
class Element{
 constructor(){this.children=[];this.style={};this.hidden=false;this.classList={toggle(){}};}
 append(...children){this.children.push(...children);for(const child of children)child.parentElement=this;}
 replaceChildren(...children){this.children=children;}
 removeAttribute(key){delete this[key];}
}
const elements=new Map();const el=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const ctx=vm.createContext({document:{getElementById:el,querySelector:el,querySelectorAll:()=>[],createElement:()=>new Element()},Image:Element,innerWidth:1920,innerHeight:1080,addEventListener(){},WebSocket:class{},location:{protocol:'http:',host:'localhost'},setTimeout(){}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/static/shared/card-effects.js'),'utf8'),ctx);
for(const file of ['dice.js','board.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/static/board',file),'utf8'),ctx);
const state={match:{player1_name:'V',player1_cred:11},latest_cards:{'1':null},legends:{'1':[{revealed:false,name:'Private',image:'/private.webp'},{revealed:true,name:'Visible',image:'/visible.webp'},{}]},dice:{}};
for(const owner of [1,2])for(const type of ['d4','d6','d8','d10','d12','d20'])state.dice[owner+type]={owner,type,location:'p'+owner+'_fixer',last_roll:null};
state.dice['1d6'].location='p1_gig';state.dice['1d6'].last_roll=4;
state.dice['2d8'].location='p1_gig';state.dice['2d8'].last_roll=7;
function render(config={}){ctx.input=state;ctx.settings=config;vm.runInContext('state=input;config=settings;render()',ctx);}
render();assert.equal(el('latest').hidden,true);assert.equal(el('gigs').children.length,6);assert.equal(el('stolen').children.length,6);assert.equal(el('reserve-count').textContent,'5 / 6 AVAILABLE');assert.equal(el('fixer').children.length,5);assert.equal(el('.reserve').parentElement,el('stage'));assert.equal(el('.economy').parentElement,el('stage'));assert.equal(el('eddies').parentElement,el('footer'));assert.equal(el('legends').children[0].children[0].src,'/static/assets/card-back.webp');assert.equal(el('legends').children[1].children[0].src,'/visible.webp');assert.equal(el('gig-camera').hidden,true);
state.dice['2d8'].location='p2_fixer';render();assert.equal(el('stolen-row').hidden,true);
render({board_dice_mode:'camera'});assert.equal(el('gigs').hidden,true);assert.equal(el('fixer').hidden,true);assert.equal(el('gig-camera').hidden,false);assert.equal(el('cred').hidden,true);
render({board_show_eddies:false});assert.equal(el('side').hidden,true);
state.latest_cards['1']={image:'/new.webp',name:'New',timestamp:'1'};render();assert.equal(el('latest').hidden,false);assert.equal(el('latest-art').src,'/new.webp');
assert.equal(el('stage').style.transform,'scale(1)');console.log('Board overlay passed: fixer derivation, stolen-only opponent dice, legend privacy, modes, and adaptive panels.');

render({show_card_art:false,show_dice:false,show_legends:false,board_show_fixer:false,board_show_eddies:false});
assert.equal(el('latest').hidden,true);assert.equal(el('.economy').hidden,true);assert.equal(el('.legends').hidden,true);assert.equal(el('.reserve').hidden,true);assert.equal(el('footer').hidden,true);
render({show_dice:true,hide_empty_captured_gigs:false});assert.equal(el('stolen-row').hidden,false);assert.equal(el('stolen').children.length,6);
render({show_dice:true,hide_empty_captured_gigs:true});assert.equal(el('stolen-row').hidden,true);
state.dice['2d8'].location='p1_gig';render({show_dice:true,hide_empty_captured_gigs:true,board_dice_mode:'camera'});assert.equal(el('stolen-row').hidden,false);assert.equal(el('stolen').children[2].children[0].textContent,7);
