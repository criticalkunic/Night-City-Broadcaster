'use strict';
const $=id=>document.getElementById(id);
async function start(){
 $('retry').hidden=true;$('error').textContent='';
 try{const r=await fetch('/api/first-run/start',{method:'POST'});if(!r.ok)throw Error('Could not start download.');}
 catch(e){$('error').textContent=e.message;$('retry').hidden=false;}
}
async function poll(){
 try{
  const r=await fetch('/api/first-run/status',{cache:'no-store'});if(!r.ok)throw Error('Cannot connect to the service.');
  const s=await r.json();if(s.ready){location.replace('/operator');return;}
  if(s.total)$('progress').value=Math.min(99,s.completed/s.total*100);else $('progress').removeAttribute('value');
  $('status').textContent=s.total?`${s.completed} / ${s.total} cards checked · ${s.downloaded} images downloaded. ${s.message}`:s.message;
  if(s.error)$('progress').value=0;
  $('error').textContent=s.error||'';$('retry').hidden=s.running;
 }catch(e){$('error').textContent=e.message;$('retry').hidden=false;}
 setTimeout(poll,1000);
}
$('retry').onclick=start;start().then(poll);
