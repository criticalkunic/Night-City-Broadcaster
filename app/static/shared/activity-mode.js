'use strict';
(()=>{
 const main=document.querySelector('main');if(!main)return;
 const operator=location.pathname==='/operator';
 let play,showcase;
 if(operator){
  play=document.createElement('div');play.id='play-workspace';while(main.firstChild)play.append(main.firstChild);main.append(play);
  showcase=document.createElement('div');showcase.hidden=true;main.append(showcase);mountShowcaseControls(showcase);
  // Phone controls remain available in either activity.
  const phone=document.getElementById('phone-open');
  if(phone){const toolbar=document.createElement('div');toolbar.className='actions';toolbar.style.marginBottom='18px';toolbar.append(phone);main.prepend(toolbar);}
 }
 const choice=document.createElement('div');choice.className='activity-choice';choice.setAttribute('role','group');choice.setAttribute('aria-label','Broadcast activity');
 choice.innerHTML='<button data-mode="play" aria-pressed="false" aria-label="Playing over webcam" title="Playing over webcam"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="2" y="5" width="14" height="14" rx="3"/><path d="m16 9 6-3v12l-6-3Z"/></svg><span>Webcam play</span></button><button data-mode="showcase" aria-pressed="false" aria-label="Showcasing a deck" title="Showcasing a deck"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="3" width="12" height="17" rx="2"/><path d="M5 6H3v15h12M11 7h6M11 11h6M11 15h3"/></svg><span>Deck showcase</span></button><span class="mode-status" role="status"></span>';
 document.getElementById('topbar').append(choice);
 let busy=false;
 function render(config){const mode=config.activity_mode==='showcase'?'showcase':'play';document.body.dataset.activity=mode;window.dispatchEvent(new CustomEvent('activity-mode-change',{detail:mode}));choice.querySelectorAll('button').forEach(b=>{b.setAttribute('aria-pressed',String(b.dataset.mode===mode));b.disabled=busy;});if(operator){play.hidden=mode==='showcase';showcase.hidden=mode!=='showcase';document.querySelector('.brand-role').textContent=mode==='showcase'?'Deck showcase':'Player console';}document.querySelectorAll('a[href="/operator"]').forEach(a=>a.textContent=mode==='showcase'?'Deck showcase':'Player console');}
 choice.querySelectorAll('button').forEach(b=>b.onclick=async()=>{busy=true;choice.querySelectorAll('button').forEach(b=>b.disabled=true);try{const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({config:{activity_mode:b.dataset.mode}})});if(!r.ok)throw Error('Could not switch activity.');render(await r.json());choice.querySelector('.mode-status').textContent='Broadcast updated. Your other activity is saved.';}catch(e){choice.querySelector('.mode-status').textContent=e.message;}finally{busy=false;choice.querySelectorAll('button').forEach(b=>b.disabled=false);}});
 function connect(){const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');ws.onopen=()=>fetch('/api/config').then(r=>r.json()).then(render).catch(()=>{});ws.onmessage=e=>{const d=JSON.parse(e.data);if(d.config)render(d.config);};ws.onclose=()=>setTimeout(connect,1500);}
 connect();
})();
