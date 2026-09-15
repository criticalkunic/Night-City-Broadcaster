"use strict";
(()=>{
 const el=id=>document.getElementById(id);let busy=false;
 async function refresh(){
  if(busy)return;
  try{
   const response=await fetch('/api/broadcast/status');if(!response.ok)throw Error('Output status unavailable');
   const state=await response.json(),select=el('virtual-device'),value=select.value;
   select.replaceChildren(...state.devices.map(d=>{const o=document.createElement('option');o.value=d.path;o.textContent=d.name+' ('+d.path+')'+(d.writable?'':' — no write permission');o.disabled=!d.writable;return o;}));
   if([...select.options].some(o=>o.value===value))select.value=value;
   else {const preferred=state.devices.find(d=>d.name==='Night City Broadcaster Camera');if(preferred)select.value=preferred.path;}
   const missing=Object.entries(state.dependencies).filter(([,v])=>!v).map(([k])=>k);
   el('virtual-start').disabled=state.running||!select.value||missing.length>0;
   el('virtual-stop').disabled=!state.running;select.disabled=state.running;
   el('virtual-status').textContent=state.error|| (state.running?`Sending selected overlay to ${state.device} · target ${state.target_fps} FPS · output ${state.output_fps} FPS · webcam ${state.capture.fps} FPS`:
    missing.length?'Missing: '+missing.join(', '):!state.devices.length?'No accessible virtual cameras. See Linux setup below.':`Ready · webcam ${state.capture.fps} FPS`);
  }catch(error){el('virtual-status').textContent=error.message;}
 }
 async function action(path,body){busy=true;el('virtual-start').disabled=true;el('virtual-stop').disabled=true;
  try{const r=await fetch('/api/broadcast/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok){const e=await r.json();throw Error(e.detail||'Output failed');}busy=false;await refresh();}
  catch(e){el('virtual-status').textContent=e.message;busy=false;el('virtual-start').disabled=false;}
 }
 el('virtual-start').onclick=()=>action('start',{device:el('virtual-device').value,layout:'board'});
 el('virtual-stop').onclick=()=>action('stop',{});
 refresh();setInterval(refresh,2000);
})();
