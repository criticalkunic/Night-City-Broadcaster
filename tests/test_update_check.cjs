const assert=require('node:assert/strict');
const {EventEmitter}=require('node:events');
const {availableUpdate,checkForUpdate}=require('../desktop/update-check.cjs');
const release={tag_name:'v1.0.3',html_url:'https://github.com/criticalkunic/Night-City-Broadcaster/releases/tag/v1.0.3',draft:false,prerelease:false};
assert.equal(availableUpdate('1.0.2',release).version,'1.0.3');
assert.equal(availableUpdate('1.0.3',release),null);
assert.equal(availableUpdate('1.0.4',release),null);
assert.equal(availableUpdate('1.9.0',{...release,tag_name:'v1.10.0'}).version,'1.10.0');
assert.equal(availableUpdate('1.0.2',{...release,prerelease:true}),null);
assert.equal(availableUpdate('1.0.2',{...release,draft:true}),null);
assert.equal(availableUpdate('1.0.2',{...release,tag_name:'v2.0.0-beta'}),null);
assert.equal(availableUpdate('1.0.2',{...release,html_url:'https://example.com/download'}),null);
function response(status,body,error=false){
 return (url,options,callback)=>{
  assert(url.endsWith('/releases/latest'));
  assert(options.headers['User-Agent'].startsWith('Night-City-Broadcaster/'));
  const req=new EventEmitter();req.destroy=()=>{};
  queueMicrotask(()=>{
   if(error){req.emit('error',new Error('offline'));return;}
   const res=new EventEmitter();res.statusCode=status;res.resume=()=>{};res.setEncoding=()=>{};
   callback(res);res.emit('data',body);res.emit('end');
  });
  return req;
 };
}
(async()=>{
 assert.equal((await checkForUpdate('1.0.2',response(200,JSON.stringify(release)))).version,'1.0.3');
 assert.equal(await checkForUpdate('1.0.2',response(403,'')),null);
 assert.equal(await checkForUpdate('1.0.2',response(200,'not json')),null);
 assert.equal(await checkForUpdate('1.0.2',response(200,'',true)),null);
 let destroyed=false;
 assert.equal(await checkForUpdate('1.0.2',()=>{const req=new EventEmitter();req.destroy=()=>{destroyed=true;};return req;}),null);
 assert(destroyed);
 console.log('Update checks passed: version ordering, stable releases, trusted download URL, failures and timeout.');
})().catch(error=>{console.error(error);process.exitCode=1;});
