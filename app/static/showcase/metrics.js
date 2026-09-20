'use strict';
window.renderDeckMetric=function(root,metrics,panel){
 const m=metrics||{total:0,legends:0,colors:{},types:[],tags:[],curve:[]};
 const titles={types:'Card breakdown',tags:`Top ${m.tag_limit||5} tags`,curve:'Cost curve'};
 root.replaceChildren();root.className='deck-metric';
 const make=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
 const color=name=>({Red:'#ef5969',Blue:'#58a6ff',Green:'#48cf97',Yellow:'#f1d44d',Purple:'#b68cf5',Black:'#99a1b0',White:'#eee9da',Colorless:'#9eabb6',Neutral:'#9eabb6',Unknown:'#747e89'}[name]||'#d49cf3');
 root.append(make('h3',titles[panel]||'Deck metrics'),make('p',`${m.total} main-deck cards · ${m.legends} legends excluded`,'metric-scope'));
 const filters=Object.values(m.filters||{}).filter(Boolean);if(filters.length)root.append(make('p','Filtered: '+filters.join(' · '),'metric-scope'));
 if(m.missing)root.append(make('p',`${m.missing} copies missing from catalog; excluded.`,'metric-warning'));
 if(!m.total){root.append(make('p',filters.length?'No cards match these filters.':'Add main-deck cards to see this metric.'));return;}
 const rows=m[panel==='types'?'types':panel==='tags'?'tags':'curve']||[];
 if(panel==='types'){
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 200 200');svg.setAttribute('role','img');svg.setAttribute('aria-label','Card types: '+rows.map(r=>`${r.label} ${r.count}`).join(', '));svg.classList.add('metric-donut');
  const palette=['#22d3ee','#ffd23f','#b68cf5','#48cf97','#ef5969','#99a1b0'];let offset=0;
  rows.forEach((r,i)=>{const circle=document.createElementNS(svg.namespaceURI,'circle');circle.setAttribute('cx','100');circle.setAttribute('cy','100');circle.setAttribute('r','72');circle.setAttribute('fill','none');circle.setAttribute('stroke',palette[i%palette.length]);circle.setAttribute('stroke-width','32');circle.setAttribute('pathLength','100');circle.setAttribute('stroke-dasharray',`${r.count/m.total*100} 100`);circle.setAttribute('stroke-dashoffset',String(-offset));circle.setAttribute('transform','rotate(-90 100 100)');offset+=r.count/m.total*100;svg.append(circle);});
  const text=document.createElementNS(svg.namespaceURI,'text');text.setAttribute('x','100');text.setAttribute('y','109');text.setAttribute('text-anchor','middle');text.setAttribute('fill','currentColor');text.setAttribute('font-size','30');text.textContent=m.total;svg.append(text);root.append(svg);
  const keys=make('div',undefined,'metric-type-key');rows.forEach((r,i)=>{const key=make('span',`${r.label} ${Math.round(r.count/m.total*100)}%`);key.style.borderColor=palette[i%palette.length];keys.append(key);});root.append(keys);
 }
 if(panel==='curve')root.append(make('p',m.average_cost===null?'No known costs':`Average cost: ${m.average_cost}`,'metric-average'));
 const list=make('div',undefined,'metric-bars');const max=Math.max(1,...rows.map(r=>r.count));
 for(const row of rows){const item=make('div',undefined,'metric-row');item.append(make('div',`${panel==='curve'&&row.label!=='Unknown'?'Cost ':''}${row.label}`,'metric-label'));const track=make('div',undefined,'metric-track');const bar=make('div',undefined,'metric-stack');bar.style.width=(row.count/max*100)+'%';for(const [name,count] of Object.entries(row.colors)){const segment=make('span');segment.style.width=(count/row.count*100)+'%';segment.style.background=color(name);segment.title=`${name}: ${count}`;bar.append(segment);}track.append(bar);item.append(track,make('b',String(row.count)));item.setAttribute('aria-label',`${row.label}: ${row.count}; `+Object.entries(row.colors).map(([name,n])=>`${name} ${n}`).join(', '));list.append(item);}root.append(list);
 if(!rows.length)root.append(make('p',panel==='tags'?'No classification tags recorded in this catalog.':'No data recorded.'));
 const legend=make('div',undefined,'metric-color-key');for(const [name,count] of Object.entries(m.colors)){const chip=make('span',`${name} · ${count}`);const swatch=make('i');swatch.style.background=color(name);chip.prepend(swatch);legend.append(chip);}root.append(make('h4','Color split'),legend);
 root.append(make('p',panel==='tags'?'Copies with each tag. A card can have several tags; totals may overlap.':panel==='curve'?`Printed cost, weighted by copies. ${m.unknown_cost} copies have unknown costs.`:'Type shares above; each bar is split by card color.','metric-footnote'));
};
