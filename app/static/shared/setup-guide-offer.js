'use strict';
(async()=>{
 try{
  const response=await fetch('/api/config');if(!response.ok)return;
  const config=await response.json();if(config.camera_guide_seen)return;
  const panel=document.createElement('section');panel.setAttribute('aria-label','Camera setup help');
  const title=document.createElement('h2');title.textContent='New here? Let’s set up your camera.';
  const text=document.createElement('p');text.textContent='Our walkthrough helps you frame your game mat, straighten the view, and mark consistent places for your cards and dice.';
  const link=document.createElement('a');link.href='/setup?guide=1';link.textContent='Start camera setup walkthrough';
  const later=document.createElement('button');later.textContent='Not now';later.style.marginLeft='16px';
  later.onclick=async()=>{later.disabled=true;try{const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({config:{camera_guide_seen:true}})});if(!r.ok)throw Error();panel.remove();}catch{later.disabled=false;text.textContent='Could not save that preference. You can still open Camera setup any time.';}};
  panel.append(title,text,link,later);document.querySelector('main').prepend(panel);
 }catch{}
})();
