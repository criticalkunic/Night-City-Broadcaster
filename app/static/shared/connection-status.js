// Same app-connection indicator on every control page.
(()=>{
 const label=document.getElementById('connection');
 async function check(){
  const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),4000);
  try{const response=await fetch('/api/health',{signal:controller.signal,cache:'no-store'});if(!response.ok)throw Error();label.textContent='● Connected';label.dataset.connected='true';}
  catch{label.textContent='Reconnecting…';label.dataset.connected='false';}
  finally{clearTimeout(timeout);setTimeout(check,5000);}
 }
 check();
})();
