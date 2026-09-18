const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const panel={clientWidth:640},frame={parentElement:panel,style:{}};
let callback;
vm.runInNewContext(fs.readFileSync('app/static/shared/broadcast-preview.js','utf8'),{
 document:{querySelectorAll:()=>[frame]},ResizeObserver:class{constructor(fn){callback=fn;}observe(el){assert.equal(el,panel);}}
});
assert.equal(frame.style.width,'1920px');assert.equal(frame.style.height,'1080px');
assert.equal(frame.style.transform,'scale(0.3333333333333333)');
panel.clientWidth=960;callback();assert.equal(frame.style.transform,'scale(0.5)');
assert.equal(frame.style.width,'1920px');
console.log('Preview: fixed 1080p viewport and responsive scaling passed.');
