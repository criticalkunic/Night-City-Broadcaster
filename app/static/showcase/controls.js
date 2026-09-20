'use strict';
window.mountShowcaseControls=function(root,{remote=false}={}){
 let deck=null,busy=false,online=false,revision=0;
 const sections=['Legends','Core units','Gear & support','Full deck'];
 root.className='showcase-workspace'+(remote?' showcase-remote':'');
 root.innerHTML=`<div><section><div class="showcase-heading"><h2>Deck showcase</h2><span data-role="connection">Connecting…</span></div><p class="showcase-help">Keep your top-down camera on the table. Select a card to hold its artwork on stream, then advance at your own pace.</p><p data-role="status" role="status" class="showcase-note"></p><div class="actions"><button data-action="previous">← Previous</button><button data-action="next">Next →</button><button data-action="follow">Follow camera</button><label class="detect-toggle"><input data-role="detect" type="checkbox"> Show latest detected card</label></div><p data-role="current"></p><h3>Show on broadcast</h3><div data-role="metrics" class="metric-buttons" aria-label="Show on broadcast"></div><div data-role="chart-controls" class="chart-controls"></div><div data-role="metric-preview" class="metric-local" hidden></div><div data-role="sections" class="actions"></div><div data-role="rows" class="showcase-rows"></div></section>${remote?'':`<section><h2>Prepare your deck</h2><label>Deck title<input data-role="title" maxlength="100"></label><button data-action="title">Save title</button><label>Find a card<input data-role="search" type="search" placeholder="Search your catalog…"></label><div data-role="results" class="actions"></div><details><summary>Import a deck list</summary><p class="showcase-help">Paste exports from cyberpunktcg.com or cyberpunk-tcg-sim.online, including their section headers and card numbers. Or use one card per line: <code>3 Panam Palmer: Strength Through Family</code>. Use a full name with subtitle if names repeat. Import replaces the current deck after every line is validated.</p><textarea data-role="import" placeholder="3 Card name&#10;2 Another card"></textarea><button data-action="import">Replace deck from list</button><p data-role="import-status" role="status" class="showcase-note" tabindex="-1"></p></details><p class="showcase-help">Use the section menus to group your walkthrough. ↑ / ↓ changes the presentation order. Removing a row only removes it from this deck.</p></section>`}</div>${remote?'':`<div><section><h2>On your video</h2><div class="preview"><iframe src="/broadcast/live" title="Deck showcase preview"></iframe></div><p class="showcase-help">Record in OBS using the same broadcast URL. Set the Browser Source to your OBS output resolution.</p><div class="actions"><button data-action="camera">Start camera</button><a href="/setup">Camera setup</a><a href="/overlay">Stream settings</a></div><p><input data-role="url" readonly aria-label="OBS broadcast URL"></p><button data-action="copy">Copy OBS stream link</button></section></div>`}`;
 if(!remote){const frame=root.querySelector('.preview iframe'),panel=frame.parentElement;panel.style.position='relative';panel.style.overflow='hidden';Object.assign(frame.style,{width:'1920px',height:'1080px',transformOrigin:'top left',position:'absolute',left:0,top:0,border:0});const resize=()=>frame.style.transform=`scale(${panel.clientWidth/1920})`;new ResizeObserver(resize).observe(panel);resize();}
 const el=name=>root.querySelector(`[data-role="${name}"]`);
 function message(text){el('status').textContent=text;}
 async function send(path,body){
  if(!online)throw Error('Disconnected. Wait for your PC to reconnect.');
  if(busy)throw Error('Please wait for the current change.');
  busy=true;disable();
  try{const r=await fetch('/api'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Check the values and try again.');if(Array.isArray(data.entries))render(data);return data;}
  finally{busy=false;disable();}
 }
 function run(fn){return async()=>{try{await fn();message('Saved.');}catch(e){message(e.message);}};}
 function disable(){root.querySelectorAll('button').forEach(b=>b.disabled=!online||busy);if(deck){root.querySelector('[data-action="previous"]').disabled=!online||busy||(deck.effective_selected??deck.selected)===0;root.querySelector('[data-action="next"]').disabled=!online||busy||(deck.effective_selected??deck.selected)>=deck.entries.length-1;root.querySelector('[data-action="follow"]').disabled=!online||busy||!deck.detect_latest;}}
 const edit=()=>({title:deck.title,entries:deck.entries.map(({card,...e})=>e),selected:deck.selected,pinned:deck.pinned,panel:deck.panel,chart_options:deck.chart_options,detect_latest:deck.detect_latest,display:deck.display,strokes:deck.strokes});

 function confirmReplacement(text){
  return new Promise(resolve=>{
   const dialog=document.createElement('dialog');dialog.className='replace-deck-dialog';
   const title=document.createElement('h2');title.textContent='Replace current deck?';
   const copy=document.createElement('p');copy.textContent=text;
   const actions=document.createElement('div');actions.className='actions';
   const cancel=document.createElement('button');cancel.textContent='Keep current deck';
   const replace=document.createElement('button');replace.textContent='Replace deck';
   const finish=value=>{dialog.close();dialog.remove();resolve(value);};
   cancel.onclick=()=>finish(false);replace.onclick=()=>finish(true);
   dialog.oncancel=e=>{e.preventDefault();finish(false);};
   actions.append(cancel,replace);dialog.append(title,copy,actions);root.append(dialog);dialog.showModal();cancel.focus();
  });
 }
 const chartFields=[['color','Color'],['card_type','Card type'],['sort','Sort by'],['tag_limit','Tags to show']];
 for(const [key,label] of chartFields){const wrap=document.createElement('label');wrap.textContent=label;const select=document.createElement('select');select.dataset.chart=key;wrap.append(select);el('chart-controls').append(wrap);select.onchange=run(()=>send('/showcase/charts',{...deck.chart_options,[key]:key==='tag_limit'?Number(select.value):select.value}));}
 const resetCharts=document.createElement('button');resetCharts.textContent='Reset chart filters';resetCharts.onclick=run(()=>send('/showcase/charts',{}));el('chart-controls').append(resetCharts);
 function chartControls(){
  el('chart-controls').hidden=deck.panel==='card';
  const choices={color:[['','All colors'],...(deck.metrics.available_colors||[]).map(v=>[v,v])],card_type:[['','All card types'],...(deck.metrics.available_types||[]).map(v=>[v,v])],sort:[['default','Default'],['count_desc','Most copies first'],['count_asc','Fewest copies first'],['name','Name / cost order']],tag_limit:[[5,'Top 5'],[10,'Top 10'],[20,'Top 20']]};
  for(const [key] of chartFields){const select=el('chart-controls').querySelector(`[data-chart="${key}"]`);const signature=JSON.stringify(choices[key]);if(select.dataset.choices!==signature){select.replaceChildren(...choices[key].map(([v,label])=>new Option(label,String(v))));select.dataset.choices=signature;}select.value=String(deck.chart_options[key]);select.parentElement.hidden=key==='tag_limit'&&deck.panel!=='tags';}
 }
 function animate(node){if(!matchMedia('(prefers-reduced-motion: reduce)').matches)node.animate([{opacity:0,transform:'translateY(10px)'},{opacity:1,transform:'translateY(0)'}],{duration:260,easing:'ease-out'});}
 el('detect').onchange=run(()=>send('/showcase/present',{action:'detection',enabled:el('detect').checked}));
 let reasonId=null;
 function openReason(entry){reasonId=entry.card_id;el('reason-title').textContent='Why '+(entry.card?.name||entry.card_id)+'?';el('reason-text').value=entry.note||'';el('reason-dialog').showModal();}
 if(!remote){
  const list=document.createElement('section');list.className='showcase-deck-area';list.innerHTML='<h2>Your deck</h2><p class="showcase-help">Click a card to show it. With detection enabled, a newly detected card takes over. Use Follow camera to release your selection now.</p>';
  list.append(el('sections'),el('rows'));root.append(list);
  const prepare=root.firstElementChild.querySelectorAll('section')[1];prepare.classList.add('showcase-prepare');root.append(prepare);
  const library=document.createElement('div');library.className='deck-library';library.innerHTML='<h3>Saved decks</h3><div class="actions"><button data-role="save-deck">Save timestamped copy</button><select data-role="saved-decks" aria-label="Saved decks"></select><button data-role="recall-deck">Recall deck</button></div><p class="showcase-help">Each save creates a new copy with its date and time, including quantities, reasoning, and display settings.</p>';prepare.prepend(library);
  async function refreshLibrary(){const r=await fetch('/api/showcase/library');if(!r.ok)throw Error('Could not load saved decks.');const list=await r.json();el('saved-decks').replaceChildren(new Option('Choose a saved deck…',''));for(const item of list)el('saved-decks').add(new Option(`${item.title} · ${new Date(item.saved_at).toLocaleString()} · ${item.cards} cards`,item.id));}
  el('save-deck').onclick=run(async()=>{const next=edit();next.title=el('title').value;await send('/showcase/deck',next);await send('/showcase/library/save',{});await refreshLibrary();});
  el('recall-deck').onclick=run(async()=>{const id=el('saved-decks').value;if(!id)throw Error('Choose a saved deck.');if(deck.entries.length&&!await confirmReplacement('Recall this saved deck? Save a timestamped copy first if you want to keep current changes.'))return;await send('/showcase/library/recall',{id});});
  refreshLibrary().catch(e=>message(e.message));
  const dialog=document.createElement('dialog');dialog.dataset.role='reason-dialog';dialog.innerHTML='<h2 data-role="reason-title">Card reasoning</h2><p>Explain why this card is in your deck. This appears on broadcast when Card reasoning is enabled; leave it blank to hide the panel.</p><textarea data-role="reason-text" maxlength="300"></textarea><div class="actions"><button data-role="reason-save">Save reasoning</button><button data-role="reason-close">Close</button></div>';root.append(dialog);
  el('reason-close').onclick=()=>dialog.close();el('reason-save').onclick=run(async()=>{const next=edit(),entry=next.entries.find(e=>e.card_id===reasonId);if(!entry)throw Error('This card was removed from the deck.');entry.note=el('reason-text').value;await send('/showcase/deck',next);dialog.close();});
 }

 const updateDisplay=mountShowcaseDisplay(root,{send,run,remote});
 function render(value){
  deck=value;updateDisplay(deck);chartControls();
  const metricPreview=el('metric-preview');metricPreview.hidden=deck.panel==='card';
  const metricKey=JSON.stringify([deck.panel,deck.metrics]);if(!metricPreview.hidden&&metricPreview.dataset.key!==metricKey){renderDeckMetric(metricPreview,deck.metrics,deck.panel);metricPreview.dataset.key=metricKey;animate(metricPreview);}
  el('metrics').querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.panel===deck.panel)));
  const shown=deck.effective_selected??deck.selected;const entry=deck.entries[shown];
  el('detect').checked=deck.detect_latest;
  el('current').textContent=entry?`${deck.title} · ${deck.total} cards · Presenting ${entry.card?.name||'Unavailable card'}`:'Add cards or import a deck to begin.';
  root.querySelector('[data-action="follow"]').textContent=!deck.detect_latest?'Follow camera':deck.manual_override?'Release selection · follow camera':'Following camera';
  if(!remote&&document.activeElement!==el('title'))el('title').value=deck.title;
  if(!remote)root.querySelectorAll('[data-display]').forEach(input=>{if(input.type==='checkbox')input.checked=deck.display[input.dataset.display];else input.value=deck.display[input.dataset.display];});
  // Vision snapshots arrive often; preserve focus and in-progress edits.
  const signature=JSON.stringify([deck.entries,shown]);
  if(root.dataset.signature!==signature){
   root.dataset.signature=signature;el('rows').replaceChildren();el('sections').replaceChildren();
   sections.forEach(section=>{const i=deck.entries.findIndex(e=>e.section===section);if(i<0)return;const b=document.createElement('button');b.textContent=section;b.onclick=run(()=>send('/showcase/present',{action:'select',index:i}));el('sections').append(b);});
   deck.entries.forEach((entry,index)=>{
    const row=document.createElement('div');row.className='showcase-row'+(index===shown?' active':'');
    const select=document.createElement('button');select.textContent=`${entry.quantity}× ${entry.card?.display_name||[entry.card?.name,entry.card?.subtitle].filter(Boolean).join(': ')||entry.card_id}`;select.onclick=run(()=>send('/showcase/present',{action:'select',index}));if(!remote&&entry.card?.image){const image=document.createElement('img');image.src=entry.card.image;image.alt='';image.loading='lazy';select.prepend(image);}row.append(select);
    if(!remote){
     const reason=document.createElement('button');reason.textContent='Reasoning';reason.onclick=()=>openReason(entry);row.append(reason);
     const quantity=document.createElement('input');quantity.type='number';quantity.min=1;quantity.max=99;quantity.value=entry.quantity;quantity.setAttribute('aria-label','Quantity of '+(entry.card?.name||entry.card_id));quantity.onchange=run(()=>{const next=edit();next.entries[index].quantity=Number(quantity.value);return send('/showcase/deck',next);});row.append(quantity);
     const section=document.createElement('select');section.setAttribute('aria-label','Section');sections.forEach(name=>section.add(new Option(name,name)));section.value=entry.section;section.onchange=run(()=>{const next=edit();next.entries[index].section=section.value;return send('/showcase/deck',next);});row.append(section);
     for(const [label,delta] of [['↑',-1],['↓',1],['Remove',0]]){const b=document.createElement('button');b.textContent=label;b.setAttribute('aria-label',label==='Remove'?'Remove '+select.textContent:(delta<0?'Move up ':'Move down ')+select.textContent);b.onclick=run(()=>{const next=edit();const currentId=next.entries[next.selected]?.card_id;if(delta){const dest=index+delta;if(dest<0||dest>=next.entries.length)return;[next.entries[index],next.entries[dest]]=[next.entries[dest],next.entries[index]];}else next.entries.splice(index,1);next.selected=Math.max(0,next.entries.findIndex(e=>e.card_id===currentId));return send('/showcase/deck',next);});row.append(b);}
    }
    el('rows').append(row);
   });
  }disable();
 }
 root.querySelectorAll('[data-action]').forEach(b=>b.onclick=run(async()=>{
  const action=b.dataset.action;
  if(['next','previous','follow'].includes(action))return send('/showcase/present',{action});
  if(action==='import'){
   const status=el('import-status'),text=el('import').value.trim();
   const report=(text,error=false)=>{status.textContent=text;status.classList.toggle('import-error',error);status.scrollIntoView({block:'nearest'});};
   if(!text){report('Paste a deck list first.',true);return;}
   if(deck.entries.length&&!await confirmReplacement('Replace the current deck with your pasted list? Saved copies stay available.')){report('Canceled. Your current deck is unchanged.');return;}
   report('Checking your deck list…');
   try{const result=await send('/showcase/import',{title:el('title').value,text});report(`Imported ${result.total} cards across ${result.entries.length} unique cards. Your deck is ready above.`);}catch(error){report(error.message,true);throw error;}
   return;
  }
  if(action==='title'){const next=edit();next.title=el('title').value;return send('/showcase/deck',next);}
  if(action==='camera')return send('/vision/start',{});
  if(action==='copy'){try{await navigator.clipboard.writeText(el('url').value);}catch{el('url').select();throw Error('Copy the selected URL.');}}
 }));
 if(!remote){el('url').value=location.origin+'/broadcast/live';let timer;el('search').oninput=()=>{const ticket=++revision;clearTimeout(timer);timer=setTimeout(async()=>{try{const q=el('search').value.trim();el('results').replaceChildren();if(!q)return;const r=await fetch('/api/cards/search?q='+encodeURIComponent(q));if(!r.ok)throw Error('Search unavailable');const data=await r.json();if(ticket!==revision)return;for(const card of data.results){const b=document.createElement('button');b.textContent=card.display_name||[card.name,card.subtitle].filter(Boolean).join(': ');b.onclick=run(async()=>{const next=edit();const existing=next.entries.find(e=>e.card_id===card.id);if(existing)existing.quantity++;else next.entries.push({card_id:card.id,quantity:1,section:card.card_type==='Legend'?'Legends':card.card_type==='Unit'?'Core units':'Gear & support',note:''});await send('/showcase/deck',next);});el('results').append(b);}}catch(e){message(e.message);}},200);};}
 const metricIcons={card:'<rect x="6" y="3" width="12" height="18" rx="2"/><path d="M9 15h6M9 18h4"/>',types:'<path d="M12 2v10h10A10 10 0 0 0 12 2Z"/><path d="M8 3a10 10 0 1 0 13 13H8Z"/>',tags:'<path d="M3 3h8l10 10-8 8L3 11Z"/><circle cx="7" cy="7" r="1"/>',curve:'<path d="M3 21V3m0 18h19M7 21V13h3v8m3 0V5h3v16m3 0v-11h3v11"/>'};
 for(const [panel,label] of [['card','Card'],['types','Card types'],['tags','Top tags'],['curve','Cost curve']]){const b=document.createElement('button');b.dataset.panel=panel;b.setAttribute('aria-label','Show '+label+' on broadcast');b.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true">'+metricIcons[panel]+'</svg>';const text=document.createElement('span');text.textContent=label;b.append(text);b.onclick=run(async()=>{await send('/showcase/present',{action:'panel',panel});animate(b);});el('metrics').append(b);}
 function connect(){const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');ws.onopen=()=>{online=true;el('connection').textContent='Connected';disable();};ws.onmessage=e=>{const data=JSON.parse(e.data);if(data.showcase)render(data.showcase);if(remote&&data.activity_mode){root.hidden=data.activity_mode!=='showcase';document.getElementById('controls').hidden=!root.hidden;document.querySelector('header h1').textContent=root.hidden?'Match controls':'Deck showcase';}};ws.onclose=()=>{online=false;el('connection').textContent='Reconnecting…';disable();setTimeout(connect,1500);};ws.onerror=()=>ws.close();}
 connect();return {render};
};
