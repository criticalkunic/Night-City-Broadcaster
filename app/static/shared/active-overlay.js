"use strict";
let activeStyle=null;
function selectOverlay(config){
 const style=config.overlay_style==='board'?'board':'compact';
 const selection=style+':'+(config.broadcast_corrected===true);
 if(selection===activeStyle)return;
 activeStyle=selection;
 const frame=document.createElement('iframe');
 frame.title=style==='board'?'Full board overlay':'Minimalist overlay';
 const params=new URLSearchParams(location.search);
 params.set('camera',config.broadcast_corrected===true?'corrected':'raw');
 frame.src=(style==='board'?'/static/board/index.html':'/static/overlay/index.html')+'?'+params;
 document.body.replaceChildren(frame);
}
function connectOverlay(){
 const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');
 ws.onopen=async()=>{try{const r=await fetch('/api/config');if(r.ok)selectOverlay(await r.json());}catch{}};
 ws.onmessage=e=>{const data=JSON.parse(e.data);if(data.config)selectOverlay(data.config);};
 ws.onclose=()=>setTimeout(connectOverlay,1500);
}
connectOverlay();
