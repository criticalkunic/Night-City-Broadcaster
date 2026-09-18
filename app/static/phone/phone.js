'use strict';
const $=id=>document.getElementById(id);
let connected=false,busy=false,current=null,searchRevision=0;
function notice(message){$('notice').textContent=message;}
async function request(path,body={}){
 if(!connected)throw Error('Disconnected. Waiting for your PC…');
 if(busy)throw Error('Please wait for the current change.');
 busy=true;
 try{const response=await fetch('/api'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw Error(data.detail||'Could not save change');render(data);return data;}
 finally{busy=false;}
}
async function action(path,body){try{await request(path,body);notice('Saved.');}catch(error){notice(error.message);}}
const gigs=initGigControls({request:(id,value)=>request('/solo/gigs/'+id,{value}),notice});
function render(data){
 if(!data.state)return;
 current=data.state;gigs.render(current.dice);
 $('latest').textContent=current.latest_cards?.['1']?.name||'No card played';
 $('undo').disabled=!data.history?.can_undo;$('redo').disabled=!data.history?.can_redo;
 $('legends').replaceChildren();
 (current.legends?.['1']||[]).forEach((legend,slot)=>{
  const row=document.createElement('div');row.className='legend-row';
  const label=document.createElement('span');label.textContent=(slot+1)+'. '+(legend.name||'Unassigned');
  const status=document.createElement('small');status.textContent=legend.revealed?'Face up':'Face down';label.append(status);
  const flip=document.createElement('button');flip.textContent=legend.revealed?'Face down':'Reveal';flip.disabled=!legend.card_id;flip.onclick=()=>action('/legends/1/'+slot,{revealed:!legend.revealed});
  row.append(label,flip);$('legends').append(row);
 });
}
$('undo').onclick=()=>action('/undo');$('redo').onclick=()=>action('/redo');
$('undo-card').onclick=()=>action('/solo/card/undo');$('clear').onclick=()=>action('/solo/card/clear');
$('new-match').onclick=()=>{if(confirm('Start a new match and clear the current board state?'))action('/solo/match/new');};
let timer;
function search(){const revision=++searchRevision;clearTimeout(timer);$('results').replaceChildren();timer=setTimeout(async()=>{
 const q=$('search').value.trim(),target=$('target').value;if(!q)return;
 try{const response=await fetch('/api/cards/search?q='+encodeURIComponent(q)+(target==='play'?'':'&type=Legend'));if(!response.ok)throw Error('Search unavailable');const data=await response.json();if(revision!==searchRevision)return;
 for(const card of data.results){const b=document.createElement('button');b.textContent=card.display_name||card.name;b.onclick=()=>action(target==='play'?'/card/latest':'/solo/legends/'+target,target==='play'?{player:1,card_id:card.id}:{card_id:card.id});$('results').append(b);}
 if(!data.results.length)$('results').textContent='No matching cards.';
 }catch(error){if(revision===searchRevision)notice(error.message);}
 },250);}
$('search').oninput=search;$('target').onchange=search;
function connect(){
 const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');
 ws.onopen=()=>{connected=true;$('controls').disabled=false;$('connection').textContent='Connected';notice('');};
 ws.onmessage=e=>render(JSON.parse(e.data));
 ws.onclose=()=>{connected=false;$('controls').disabled=true;$('connection').textContent='Reconnecting…';if($('gig-picker').open)$('gig-picker').close();setTimeout(connect,1500);};
 ws.onerror=()=>ws.close();
}
connect();
