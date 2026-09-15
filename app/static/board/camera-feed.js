"use strict";
// Do not decode offscreen setup panels or previews in background tabs.
function feedVisibility(img){
 let onScreen=true;
 if(typeof IntersectionObserver==='function'){
  new IntersectionObserver(entries=>{onScreen=entries[0].isIntersecting;},{rootMargin:'80px'}).observe(img);
 }
 return ()=>!document.hidden&&onScreen&&img.getClientRects().length>0;
}
// Continuous multipart video avoids one HTTP round trip per frame.
function startBoardFeed(img, area) {
 if(typeof navigator!=="undefined"&&/Firefox\//.test(navigator.userAgent)){startAcknowledgedFeed(img,area);return;}
 const isVisible=feedVisibility(img);
 let active=false, retryAt=0;
 function update() {
  const visible=isVisible();
  if (!visible&&active) {img.removeAttribute("src");active=false;}
  if (visible&&!active&&Date.now()>=retryAt) {
   active=true;img.src="/api/vision/area-stream/"+area+"?t="+Date.now();
  }
  setTimeout(update,250);
 }
 img.onerror=()=>{active=false;retryAt=Date.now()+1500;};
 update();
}

// Firefox avoids long-lived multipart image decoding and its HTTP connection
// pool. Keep at most one image awaiting decode; release old blob URLs.
function startAcknowledgedFeed(img,area){
 const isVisible=feedVisibility(img);
 let socket=null,retryAt=0,currentURL=null,pendingURL=null;
 function release(){
  img.onload=null;img.onerror=null;img.removeAttribute('src');
  if(currentURL)URL.revokeObjectURL(currentURL);
  if(pendingURL)URL.revokeObjectURL(pendingURL);
  currentURL=pendingURL=null;
 }
 function disconnect(){const old=socket;socket=null;if(old)old.close();release();}
 function update(){
  const visible=isVisible();
  if(!visible&&socket)disconnect();
  if(visible&&!socket&&Date.now()>=retryAt){
   const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/api/vision/area-socket/'+area);
   socket=ws;ws.binaryType='blob';
   ws.onopen=()=>{if(socket===ws)ws.send('next');};
   ws.onmessage=event=>{
    if(socket!==ws)return;
    if(pendingURL){disconnect();retryAt=Date.now()+1500;return;}
    pendingURL=URL.createObjectURL(event.data);
    img.onload=()=>{
     if(socket!==ws)return;
     if(currentURL)URL.revokeObjectURL(currentURL);
     currentURL=pendingURL;pendingURL=null;
     if(ws.readyState===1)ws.send('next');
    };
    img.onerror=()=>{if(socket===ws){disconnect();retryAt=Date.now()+1500;}};
    img.src=pendingURL;
   };
   ws.onclose=()=>{if(socket===ws){socket=null;release();retryAt=Date.now()+1500;}};
   ws.onerror=()=>{if(socket===ws){disconnect();retryAt=Date.now()+1500;}};
  }
  setTimeout(update,250);
 }
 update();
}

// Signal only our dedicated renderer after the page has painted. Ordinary OBS
// sources have no token and do not affect virtual-camera startup.
const rendererToken=new URLSearchParams(location.search).get("renderer");
if(rendererToken)requestAnimationFrame(()=>requestAnimationFrame(()=>{
 fetch("/api/broadcast/renderer-ready?token="+encodeURIComponent(rendererToken),{method:"POST"});
}));
