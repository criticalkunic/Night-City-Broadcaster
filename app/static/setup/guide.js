'use strict';
window.initCameraGuide = function({selectTarget, save, cameraReady, setVisibleTargets = ()=>{}, getActivity = ()=>"play"}) {
 const el=id=>document.getElementById(id);
 const playSteps=[
  {title:'Start with your webcam', target:'p1_rect', camera:true, demo:'camera', text:'Use a game mat, keep it fully in view, then start your camera. Even lighting helps avoid glare.'},
  {title:'Straighten the board', target:'p1_corners', demo:'perspective', text:'Drag the four handles onto the corners of your game mat, clockwise from top left. This straightens an angled camera view.'},
  {title:'Your played cards go here', target:'p1_card', demo:'play', text:'Fit the box around your play area. Cards can go anywhere inside it. Keep legends outside this box. Match printed mat zones, or use the same spots each game.'},
  {title:'Make room for three legends', target:'p1_legend', demo:'legends', text:'Fit the box around your legend row. Center one card in each third, from left to right.'},
  {title:'Frame your Eddies', target:'p1_eddie', demo:'eddies', text:'Fit the box around your Eddies. This becomes their close-up in the full-board stream.'},
  {title:'Frame your gigs', target:'p1_gig', demo:'gigs', text:'Mark where your gig dice live. Using tracked dice instead? Keep this box and continue.'},
  {title:'Frame your fixer dice', target:'p1_fixer', demo:'fixer', text:'Mark your available dice. Using tracked dice or hiding this panel? You can continue.'},
  {title:'Ready for your first play', target:'p1_card', demo:'play', text:'Place a card in the play area. After finishing, check its artwork in Player console. Keep your camera and mat in place.'}
 ];
 const showcaseSteps=[playSteps[0],playSteps[1],{title:'Your showcase board',target:'p1_board',demo:'play',text:'Fit this box around the board where you will show cards. Enable Show latest detected card to let a new card update the right panel.'}];
 let steps=getActivity()==='showcase'?showcaseSteps:playSteps;
 const panel=el('camera-guide'), moved=[];
 function openWindow(){
  if(!panel.open){
   for(const [selector,slot] of [['.views','guide-camera'],['.camera-controls','guide-source'],['[aria-label="Camera orientation"]','guide-source']]){
    const node=document.querySelector(selector), marker=document.createComment('setup home');
    node.before(marker);moved.push([node,marker]);el(slot).append(node);
   }
   panel.hidden=false;panel.showModal();
  }
 }
 function closeWindow(){
  panel.close();panel.hidden=true;setVisibleTargets(null);
  for(const [node,marker] of moved.splice(0)){marker.replaceWith(node);}
  el('guide-open').focus();
 }
 panel.addEventListener('cancel',event=>{event.preventDefault();if(!busy)el('guide-close').onclick();});
 let index=-1, busy=false;
 async function remember(){const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({config:{camera_guide_seen:true}})});if(!r.ok)throw Error('Could not save your walkthrough preference.');}
 function render(){
  const active=index>=0, step=active?steps[index]:null;
  el('guide-progress').textContent=active?`Step ${index+1} of ${steps.length}`:'A little help getting started';
  el('guide-title').textContent=active?step.title:'Set up your camera with us';
  el('guide-text').textContent=active?step.text:'Your webcam, one step at a time. We’ll frame your mat and mark where everything goes.';
  panel.dataset.demo=active?step.demo:'camera';
  el('guide-source').hidden=active&&!step.camera;
  el('guide-meter').max=steps.length;
  el('guide-meter').value=active?index+1:0;
  el('guide-demo-label').textContent=active?'Example · '+step.title:'Example · keep your mat in view';
  el('guide-back').hidden=index<=0;
  el('guide-next').textContent=!active?'Start walkthrough':index===steps.length-1?'Save & finish':step.target&&!step.camera?'Save & continue':'Continue';
  for(const id of ['guide-back','guide-next','guide-close','guide-open'])el(id).disabled=busy;
 }
 function show(next){steps=getActivity()==='showcase'?showcaseSteps:playSteps;index=Math.min(next,steps.length-1);openWindow();el('guide-error').textContent='';setVisibleTargets(steps.slice(0,index+1).map(s=>s.target).filter(Boolean));if(steps[index]?.target)selectTarget(steps[index].target);render();el('guide-copy').animate([{opacity:0,transform:'translateX(16px)'},{opacity:1,transform:'translateX(0)'}],{duration:matchMedia('(prefers-reduced-motion: reduce)').matches?0:240});el('guide-title').focus();}
 el('guide-open').onclick=()=>show(-1);
 el('guide-back').onclick=()=>show(index-1);
 el('guide-close').onclick=async()=>{busy=true;render();try{await remember();closeWindow();}catch(e){el('guide-error').textContent=e.message;}finally{busy=false;render();}};
 el('guide-next').onclick=async()=>{
  busy=true;render();el('guide-error').textContent='';
  try{
   if(index>=0){
    if(steps[index].camera && !await cameraReady())throw Error('Start your camera and wait for a live picture, then continue.');
    if(steps[index].target&&!steps[index].camera)await save();
   }
   if(index===steps.length-1){await remember();closeWindow();}
   else show(index+1);
  }catch(e){el('guide-error').textContent=e.message;}
  finally{busy=false;render();}
 };
 render();
 fetch('/api/config').then(r=>{if(!r.ok)throw Error();return r.json();}).then(config=>{if(!config.camera_guide_seen||new URLSearchParams(location.search).has('guide'))show(-1);}).catch(()=>{});
};
