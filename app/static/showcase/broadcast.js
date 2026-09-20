'use strict';
(()=>{
 const el=id=>document.getElementById(id);let image='',panelKey='',metricKey='',drawingKey='',savedStrokes=[],previewStroke=null,previewTimer;
 let currentDisplay={};
 const corrected=new URLSearchParams(location.search).get('camera')==='corrected';
 const updateBoardTransform=()=>applyShowcaseBoardTransform(el('camera'),el('board-drawings'),currentDisplay,corrected);
 new ResizeObserver(updateBoardTransform).observe(el('table'));
 setInterval(updateBoardTransform,500);
 startBoardFeed(el('camera'),new URLSearchParams(location.search).get('camera')==='corrected'?'board_corrected':'raw');
 function paintDrawing(){renderShowcaseDrawings(el('board-drawings'),previewStroke?[...savedStrokes,previewStroke]:savedStrokes);}
 function render(data){
  if(data.type==='showcase_drawing'){previewStroke=data.stroke;clearTimeout(previewTimer);paintDrawing();if(previewStroke)previewTimer=setTimeout(()=>{previewStroke=null;paintDrawing();},3000);return;}

  if(data.config)document.documentElement.dataset.theme=data.config.overlay_theme||'cyberpunk';
  const deck=data.showcase;if(!deck)return;
  const display=deck.display;
  currentDisplay=display;
  updateBoardTransform();
  el('table').style.background=display.camera?'#080b10':'transparent';
  document.querySelector('header').hidden=!display.header;document.querySelector('footer').hidden=!display.footer;
  document.querySelector('aside').hidden=!display.sidebar;
  el('camera').hidden=!display.camera;document.body.classList.toggle('minimal-showcase',display.layout==='minimal');
  el('sections').hidden=!display.sections;el('board-drawings').toggleAttribute('hidden',!display.drawings);
  document.body.classList.toggle('no-sidebar',!display.sidebar);
  document.body.style.setProperty('--header-height',display.header?'5.3vh':'0px');document.body.style.setProperty('--footer-height',display.footer?'5vh':'0px');

  const drawings=JSON.stringify(deck.strokes);if(drawings!==drawingKey){drawingKey=drawings;savedStrokes=deck.strokes;previewStroke=null;clearTimeout(previewTimer);paintDrawing();}
  el('metric-output').hidden=deck.panel==='card';el('card-panel').hidden=deck.panel!=='card';
  const key=JSON.stringify([deck.panel,deck.metrics]);if(deck.panel!=='card'&&key!==metricKey){metricKey=key;renderDeckMetric(el('metric-output'),deck.metrics,deck.panel);}
  if(panelKey!==deck.panel){panelKey=deck.panel;if(!matchMedia('(prefers-reduced-motion: reduce)').matches){const node=el(deck.panel==='card'?'card-panel':'metric-output');node.animate([{opacity:0,transform:'translateX(24px)'},{opacity:1,transform:'translateX(0)'}],{duration:320,easing:'ease-out'});}}
  const index=deck.effective_selected??deck.selected;
  const entry=deck.entries[index],card=entry?.card;
  const reasoning=(entry?.note||'').trim();
  const showReasoning=display.summary&&!!reasoning;
  el('deck-summary').hidden=!showReasoning;
  document.body.classList.toggle('no-summary',!showReasoning);
  el('deck-caption').textContent=card?.name||'';
  el('card-reasoning').textContent=reasoning;
  el('title').textContent=deck.title;el('name').textContent=card?.name||'';
  el('quantity').textContent=entry?`${entry.quantity} ${entry.quantity===1?'COPY':'COPIES'} IN DECK`:'';
  el('empty').hidden=!!card?.image;el('card').hidden=!card?.image;
  if(card?.image&&image!==card.image){image=card.image;el('card').src=image;el('card').alt=card.name;el('card').getAnimations().forEach(a=>a.cancel());el('card').animate([{opacity:0},{opacity:1}],{duration:250});}
  el('section').textContent=entry?.section.toUpperCase()||'DECK WALKTHROUGH';
  el('count').textContent=entry?`${String(index+1).padStart(2,'0')} / ${deck.entries.length} UNIQUE CARDS`:'No deck loaded';
  el('total').textContent=deck.total?`${deck.total} CARDS IN DECK`:'';
  el('progress').max=Math.max(1,deck.entries.length);el('progress').value=entry?index+1:0;
  el('sections').replaceChildren();
  ['Legends','Core units','Gear & support','Full deck'].forEach((name,i)=>{const row=document.createElement('div');row.textContent=`0${i+1}  ${name}`;row.classList.toggle('active',name===entry?.section);el('sections').append(row);});
 }
 function connect(){const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');ws.onmessage=e=>render(JSON.parse(e.data));ws.onopen=()=>fetch('/api/config').then(r=>r.json()).then(config=>render({config}));ws.onclose=()=>setTimeout(connect,1500);}
 connect();
})();
