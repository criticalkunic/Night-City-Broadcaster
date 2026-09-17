const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(){this.children=[];this.dataset={};this.attrs={};this.classList={add:()=>{},toggle:()=>{}};}
 append(...nodes){this.children.push(...nodes)} replaceChildren(...nodes){this.children=nodes}
 setAttribute(k,v){this.attrs[k]=v}addEventListener(k,fn){this[k]=fn}
 showModal(){this.open=true}close(){this.open=false}focus(){this.focused=true}
}
(async()=>{
 const ids={};for(const id of ['gig-picker','gig-picker-close','gig-picker-error','gig-picker-title','gig-values','gig-controls','own-gig-tray','captured-gig-tray'])ids[id]=new Element();
 let fail=false,resolve,hold=false;const calls=[];
 const c={window:{},document:{getElementById:id=>ids[id],createElement:()=>new Element()}};
 vm.createContext(c);vm.runInContext(fs.readFileSync('app/static/board/dice.js','utf8')+fs.readFileSync('app/static/operator/gigs.js','utf8'),c);
 c.request=async(id,value)=>{calls.push([id,value]);if(fail)throw Error('Offline');if(hold)await new Promise(r=>resolve=r);};c.notice=()=>{};
 vm.runInContext('controls=initGigControls({request,notice})',c);const ui=c.controls;
 ui.render({});assert.equal(ids['own-gig-tray'].children.length,6);assert.equal(ids['captured-gig-tray'].children.length,6);
 for(const [i,sides] of [4,6,8,10,12,20].entries()){
  ids['own-gig-tray'].children[i].onclick();assert.equal(ids['gig-values'].children.length,sides+1);
  assert.equal(ids['gig-values'].children[sides-1].dataset.value,String(sides));
 }
 await ids['gig-values'].children[19].onclick();assert.deepEqual(calls.at(-1),['p1-d20',20]);assert.equal(ids['gig-picker'].open,false);
 ids['captured-gig-tray'].children[0].onclick();await ids['gig-values'].children[3].onclick();assert.deepEqual(calls.at(-1),['p2-d4',4]);
 ui.render({'p2-d4':{location:'p1_gig',last_roll:4}});ids['captured-gig-tray'].children[0].onclick();assert.equal(ids['gig-values'].children[3].attrs['aria-pressed'],'true');
 await ids['gig-values'].children[4].onclick();assert.deepEqual(calls.at(-1),['p2-d4',null]);
 ids['own-gig-tray'].children[1].onclick();fail=true;await ids['gig-values'].children[0].onclick();assert.equal(ids['gig-picker'].open,true);assert.equal(ids['gig-picker-error'].textContent,'Offline');assert.equal(ids['gig-picker-close'].disabled,false);
 fail=false;hold=true;const before=calls.length,pending=ids['gig-values'].children[0].onclick();await ids['gig-values'].children[1].onclick();assert.equal(calls.length,before+1);resolve();await pending;
 ui.setTheme('edgerunners');assert.equal(ids['gig-controls'].dataset.theme,'edgerunners');assert.equal(ids['gig-picker'].dataset.theme,'edgerunners');
 console.log('Visual gigs: both trays, every die range, ownership, removal, current value, errors, duplicate prevention and themes passed.');
})().catch(e=>{console.error(e);process.exit(1)});
