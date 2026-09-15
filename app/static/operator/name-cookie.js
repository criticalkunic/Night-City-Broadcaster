"use strict";
function rememberedPlayerName(){
 try{const value=document.cookie.split(';').map(p=>p.trim()).find(p=>p.startsWith('cyberpunk_player_name='));return value?decodeURIComponent(value.slice('cyberpunk_player_name='.length)).trim().slice(0,50):'';}catch{return '';}
}
let lastRememberedPlayerName=null;
function rememberPlayerName(name){
 const value=String(name||'').trim().slice(0,50);
 if(lastRememberedPlayerName===value)return;
 lastRememberedPlayerName=value;
 document.cookie='cyberpunk_player_name='+encodeURIComponent(value)+'; Max-Age=31536000; Path=/; SameSite=Lax'+(location.protocol==='https:'?'; Secure':'');
}
let playerNameInitialized=false;
function syncRememberedPlayerName(state){
 const name=state.match.player1_name;
 if(!playerNameInitialized){
  playerNameInitialized=true;
  const saved=rememberedPlayerName();
  if(saved&&(!name||name==='Player 1')){
   api('/match/names',{player1_name:saved,player2_name:state.match.player2_name}).catch(error=>notice('Could not restore saved name: '+error.message));
   return;
  }
 }
 if(name&&name!=='Player 1')rememberPlayerName(name);
}
