"use strict";
let activeStyle=null;
function selectOverlay(config){
 const style=config.overlay_style==='board'?'board':'compact';
 if(style===activeStyle)return;
 activeStyle=style;
 const frame=document.createElement('iframe');
 frame.title=style==='board'?'Full board overlay':'Minimalist overlay';
 frame.src=(style==='board'?'/static/board/index.html':'/static/overlay/index.html')+location.search;
 document.body.replaceChildren(frame);
}
function connectOverlay(){
 const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');
 ws.onopen=async()=>{try{const r=await fetch('/api/config');if(r.ok)selectOverlay(await r.json());}catch{}};
 ws.onmessage=e=>{const data=JSON.parse(e.data);if(data.config)selectOverlay(data.config);};
 ws.onclose=()=>setTimeout(connectOverlay,1500);
}
connectOverlay();
