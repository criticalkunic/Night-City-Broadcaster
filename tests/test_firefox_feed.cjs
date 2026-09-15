const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
let timers=[],sockets=[],visible=true,id=0,revoked=[];
class Socket{constructor(){this.sent=[];this.readyState=1;sockets.push(this);}send(x){this.sent.push(x);}close(){this.closed=true;}}
const img={getClientRects:()=>visible?[{}]:[],removeAttribute(){delete this.src;}};
const context=vm.createContext({document:{hidden:false},navigator:{userAgent:'Firefox/140.0'},location:{protocol:'http:',host:'localhost',search:''},URLSearchParams,URL:{createObjectURL:()=>`blob:${++id}`,revokeObjectURL:x=>revoked.push(x)},WebSocket:Socket,Date,setTimeout:fn=>timers.push(fn)});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/static/board/camera-feed.js'),'utf8'),context);
context.startBoardFeed(img,'raw');const socket=sockets[0];socket.onopen();assert.deepEqual(socket.sent,['next']);
socket.onmessage({data:{}});assert.equal(img.src,'blob:1');assert.equal(socket.sent.length,1,'No request until image loads');
img.onload();assert.equal(socket.sent.length,2);
socket.onmessage({data:{}});img.onload();assert.deepEqual(revoked,['blob:1']);
visible=false;timers.shift()();assert.equal(socket.closed,true);assert.deepEqual(revoked,['blob:1','blob:2']);
console.log('Firefox feed passed: decode acknowledgements, bounded images, URL cleanup, hidden disconnect.');
