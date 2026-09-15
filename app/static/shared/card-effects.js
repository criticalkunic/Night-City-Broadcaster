"use strict";
const legendViews=new WeakMap();
function reducedCardMotion(){return typeof matchMedia==='function'&&matchMedia('(prefers-reduced-motion: reduce)').matches;}
function glitchCard(img){
 if(reducedCardMotion())return;
 img.classList.remove('cyber-glitch');
 // A fresh image or onload event starts the effect once per displayed play.
 void img.offsetWidth;img.classList.add('cyber-glitch');
}
function renderLegendCards(container,legends,board=false){
 let views=legendViews.get(container);
 if(!views){views=Array.from({length:3},(_,i)=>{
  const tile=document.createElement('div'),img=new Image(),label=document.createElement(board?'span':'small');
  tile.append(img,label);return {tile,img,label,key:null,face:null,revision:0};
 });legendViews.set(container,views);container.replaceChildren(...views.map(v=>v.tile));}
 views.forEach((v,i)=>{
  const legend=legends[i],revealed=!!legend?.revealed;
  const src=revealed&&legend.image?legend.image:'/static/assets/card-back.webp';
  const key=JSON.stringify([revealed,src,revealed?legend?.name:'',!!legend?.upside_down]);
  if(key===v.key)return;
  const flip=v.key!==null&&v.face!==revealed,revision=++v.revision;
  v.key=key;v.face=revealed;
  v.tile.className=(board?'legend':'legend-tile')+(revealed?(board?' revealed':' flipped'):'');
  v.label.textContent=revealed?'FLIPPED':'FACE DOWN';
  v.img.className=legend?.upside_down?'upside-down':'';
  v.img.alt=revealed?(legend.name||'Revealed legend'):'Face-down legend '+(i+1);
  for(const animation of v.img.getAnimations?.()||[])animation.cancel();
  // Hide identity immediately when turned face down, including mid-animation.
  if(!revealed)v.img.src=src;
  if(flip&&!reducedCardMotion()&&v.img.animate){
   const out=v.img.animate([{transform:'perspective(800px) rotateY(0deg)'},{transform:'perspective(800px) rotateY(90deg)'}],{duration:200,fill:'forwards',easing:'ease-in'});
   out.onfinish=()=>{
    if(v.revision!==revision)return;
    v.img.src=src;out.cancel();
    v.img.animate([{transform:'perspective(800px) rotateY(-90deg)'},{transform:'perspective(800px) rotateY(0deg)'}],{duration:240,easing:'ease-out'});
   };
  }else v.img.src=src;
 });
}

function applyOverlayTheme(config){
 const root=document.documentElement;if(!root)return;
 const theme=['cyberpunk','arasaka','edgerunners'].includes(config.overlay_theme)?config.overlay_theme:'cyberpunk';
 if(root.dataset.theme!==theme)root.dataset.theme=theme;
}
