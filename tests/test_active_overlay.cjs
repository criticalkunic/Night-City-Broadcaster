const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const body={children:[],replaceChildren(...items){this.children=items;}};
const ctx=vm.createContext({URLSearchParams,document:{body,createElement:()=>({})},location:{protocol:'http:',host:'localhost',search:'?renderer=qa'},WebSocket:class {},setTimeout(){}});
vm.runInContext(fs.readFileSync('app/static/shared/active-overlay.js','utf8'),ctx);
ctx.selectOverlay({overlay_style:'compact'});
const first=body.children[0];assert(first.src.endsWith('/overlay/index.html?renderer=qa&camera=raw'));
ctx.selectOverlay({overlay_style:'compact'});assert.equal(body.children[0],first);
ctx.selectOverlay({overlay_style:'board'});assert.equal(body.children.length,1);assert.notEqual(body.children[0],first);
assert(body.children[0].src.endsWith('/board/index.html?renderer=qa&camera=raw'));
console.log('Active overlay passed: one renderer, stable updates, token preserved.');

ctx.selectOverlay({overlay_style:'compact',broadcast_corrected:true});
assert(body.children[0].src.endsWith('/overlay/index.html?renderer=qa&camera=corrected'));
const corrected=body.children[0];
ctx.selectOverlay({overlay_style:'compact',broadcast_corrected:true});
assert.equal(body.children[0],corrected);
ctx.selectOverlay({overlay_style:'compact',broadcast_corrected:false});
assert.notEqual(body.children[0],corrected);
assert(body.children[0].src.endsWith('camera=raw'));
