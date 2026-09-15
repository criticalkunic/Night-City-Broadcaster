const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
class El{
 constructor(){this.children=[];this.animations=[];}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=items;}
 getAnimations(){return this.animations;}
 animate(){const a={cancel(){this.cancelled=true;}};this.animations.push(a);return a;}
}
const ctx=vm.createContext({document:{createElement:()=>new El()},Image:El});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/static/shared/card-effects.js'),'utf8'),ctx);
const box=new El();ctx.renderLegendCards(box,[{revealed:false,image:'/secret'}],true);
const img=box.children[0].children[0];assert.equal(img.src,'/static/assets/card-back.webp');
ctx.renderLegendCards(box,[{revealed:true,image:'/front'}],true);
assert.equal(img.animations.length,1);const reveal=img.animations[0];
ctx.renderLegendCards(box,[{revealed:true,image:'/front'}],true);assert.equal(img.animations.length,1);
ctx.renderLegendCards(box,[{revealed:false,image:'/secret'}],true);
reveal.onfinish();assert.equal(img.src,'/static/assets/card-back.webp','An interrupted reveal cannot expose a hidden legend');
const hide=img.animations[1];hide.onfinish();assert.equal(img.src,'/static/assets/card-back.webp');
console.log('Legend effects passed: change-only animation, stable nodes, immediate privacy, stale callback guard.');
ctx.renderLegendCards(box,[{revealed:true,image:'/front',upside_down:true}],true);
assert.equal(img.className,'upside-down');
ctx.renderLegendCards(box,[{revealed:true,image:'/front',upside_down:false}],true);
assert.equal(img.className,'');
ctx.document.documentElement={dataset:{}};
ctx.applyOverlayTheme({overlay_theme:'arasaka'});assert.equal(ctx.document.documentElement.dataset.theme,'arasaka');
ctx.applyOverlayTheme({overlay_theme:'cyberpunk'});assert.equal(ctx.document.documentElement.dataset.theme,'cyberpunk');

ctx.applyOverlayTheme({overlay_theme:'edgerunners'});assert.equal(ctx.document.documentElement.dataset.theme,'edgerunners');
