const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
async function run(seen){
 let panel;const requests=[];
 const document={createElement:tag=>({tag,style:{},setAttribute(){},append(...children){this.children=children;},remove(){this.removed=true;}}),querySelector:()=>({prepend:p=>panel=p})};
 vm.runInNewContext(fs.readFileSync('app/static/shared/setup-guide-offer.js','utf8'),{document,fetch:async(url,opts)=>{requests.push(opts);return{ok:true,json:async()=>({camera_guide_seen:seen})};}});
 await new Promise(setImmediate);return{panel,requests};
}
(async()=>{
 const first=await run(false);assert(first.panel);assert.equal(first.panel.children[2].href,'/setup?guide=1');
 await first.panel.children[3].onclick();assert(first.panel.removed);assert(JSON.parse(first.requests.at(-1).body).config.camera_guide_seen);
 assert.equal((await run(true)).panel,undefined);
 console.log('First-use offer, persisted dismissal, and explicit guide link passed.');
})().catch(e=>{console.error(e);process.exit(1);});
