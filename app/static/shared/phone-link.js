'use strict';
(()=>{
 const open=document.getElementById('phone-open'),dialog=document.getElementById('phone-dialog'),status=document.getElementById('phone-status'),select=document.getElementById('phone-address');
 function showURL(){document.getElementById('phone-qr').src='/api/phone/qr?url='+encodeURIComponent(select.value);document.getElementById('phone-url').textContent=select.value;document.getElementById('phone-url').href=select.value;}
 select.onchange=showURL;
 open.onclick=async()=>{dialog.showModal();status.textContent='Starting local phone controls…';document.getElementById('phone-details').hidden=true;try{const response=await fetch('/api/phone/start',{method:'POST'});if(!response.ok)throw Error('Could not start phone controls.');const data=await response.json();select.replaceChildren(...data.urls.map(url=>{const option=document.createElement('option');option.value=option.textContent=url;return option;}));if(!data.urls.length)throw Error('No LAN address found. Connect your PC to Wi-Fi or Ethernet, then reopen this panel.');document.getElementById('phone-details').hidden=false;select.hidden=data.urls.length<2;showURL();status.textContent='Scan with your phone camera. No pairing or app needed.';}catch(error){status.textContent=error.message;}};
 document.getElementById('phone-close').onclick=()=>dialog.close();
 document.getElementById('phone-stop').onclick=async()=>{const response=await fetch('/api/phone/stop',{method:'POST'});if(response.ok){document.getElementById('phone-details').hidden=true;status.textContent='Phone access stopped. Reopen this panel to enable it again.';}};
})();
