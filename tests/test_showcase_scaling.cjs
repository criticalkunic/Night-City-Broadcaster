const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const context={window:{}};
vm.runInNewContext(fs.readFileSync('app/static/showcase/drawing.js','utf8'),context);
const transform=context.window.showcaseBoardTransform;
test('auto-fill covers a wide frame without distorting a 4:3 source',()=>{
 assert.equal(transform({},true,800,600,1920,1080),'translate(0%,0%) scale(1.3333333333333333,1.3333333333333333)');
 assert.equal(transform({},true,1920,1080,1920,1080),'translate(0%,0%) scale(1,1)');
});
test('fit, zoom, aspect adjustment and positioning remain independent',()=>{
 assert.equal(transform({corrected_fit:'contain',corrected_width:110,corrected_height:90,corrected_zoom:120,corrected_x:5,corrected_y:-10},true,800,600,1920,1080),'translate(5%,-10%) scale(1.32,1.08)');
 assert.equal(transform({corrected_width:150},false,800,600,1920,1080),'none');
});
test('missing frame dimensions do not cause invalid transforms',()=>{
 assert.equal(transform({},true,0,0,0,0),'translate(0%,0%) scale(1,1)');
});
