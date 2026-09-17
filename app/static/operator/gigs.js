'use strict';
function initGigControls({request,notice}) {
 const el=id=>document.getElementById(id), dialog=el('gig-picker');
 let dice={},key='',selected=null,busy=false;
 const trays=[el('own-gig-tray'),el('captured-gig-tray')];
 function button(type,label,active){
  const b=document.createElement('button');b.type='button';b.className='gig-die'+(active?' active':'');
  b.innerHTML=dieShapeSVG(type);const text=document.createElement('span');text.textContent=label;b.append(text);return b;
 }
 function close(){dialog.close();document.getElementById('gig-'+selected?.id)?.focus();}
 function markValue(){
  const die=dice[selected?.id],value=die?.location==='p1_gig'?die.last_roll:null;
  for(const b of el('gig-values').children)b.setAttribute('aria-pressed',String(b.dataset.value===String(value)));
 }
 async function choose(value){
  if(busy)return;busy=true;el('gig-picker-error').textContent='';
  const buttons=[...el('gig-values').children,el('gig-picker-close')];buttons.forEach(b=>b.disabled=true);
  try{await request(selected.id,value);close();notice(value===null?'Gig removed.':'Gig value updated.');}
  catch(error){el('gig-picker-error').textContent=error.message;}
  finally{busy=false;buttons.forEach(b=>b.disabled=false);}
 }
 function open(owner,type){
  selected={id:'p'+owner+'-'+type};dialog.classList.toggle('captured',owner===2);
  el('gig-picker-title').textContent=(owner===2?'Captured ':'My ')+type.toUpperCase()+' gig';
  el('gig-picker-error').textContent='';el('gig-values').replaceChildren();
  for(let value=1;value<=DIE_SIDES[type];value++){
   const b=button(type,value,true);b.dataset.value=String(value);b.setAttribute('aria-label','Set '+type.toUpperCase()+' to '+value);
   b.onclick=()=>choose(value);el('gig-values').append(b);
  }
  const remove=button(type,type.toUpperCase(),false);remove.classList.add('remove-gig');remove.dataset.value='null';
  remove.setAttribute('aria-label','Remove '+(owner===2?'captured ':'')+type.toUpperCase()+' gig');
  const cross=document.createElement('span');cross.className='remove-cross';cross.setAttribute('aria-hidden','true');remove.append(cross);
  remove.onclick=()=>choose(null);el('gig-values').append(remove);markValue();dialog.showModal();
 }
 el('gig-picker-close').onclick=()=>{if(!busy)close();};
 dialog.addEventListener('cancel',event=>{event.preventDefault();if(!busy)close();});
 return {
  setTheme(theme){for(const node of [el('gig-controls'),dialog])node.dataset.theme=theme||'cyberpunk';},
  render(next){
   dice=next||{};const nextKey=JSON.stringify(dice);if(nextKey===key)return;key=nextKey;
   for(const owner of [1,2]){
    const tray=trays[owner-1];tray.replaceChildren();
    for(const type of DIE_ORDER){
     const id='p'+owner+'-'+type,die=dice[id],active=die?.location==='p1_gig';
     const b=button(type,active&&die.last_roll!=null?die.last_roll:type.toUpperCase(),active);
     b.id='gig-'+id;b.setAttribute('aria-label',(owner===2?'Captured ':'My ')+type.toUpperCase()+(active?' · value '+die.last_roll:' · not controlled'));
     b.setAttribute('aria-haspopup','dialog');b.onclick=()=>open(owner,type);tray.append(b);
    }
   }
   if(dialog.open)markValue();
  }
 };
}
