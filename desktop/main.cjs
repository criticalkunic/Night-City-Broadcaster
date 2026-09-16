const {app,BrowserWindow,dialog,shell}=require('electron');
const {spawn}=require('node:child_process');
const path=require('node:path');
const http=require('node:http');
const {checkForUpdate}=require('./update-check.cjs');
const {userDataDirectory}=require('./user-data.cjs');
const dataDirectory=userDataDirectory(app.getPath('appData'));
require('node:fs').mkdirSync(dataDirectory,{recursive:true});
app.setPath('userData',dataDirectory);
app.setPath('sessionData',dataDirectory);
let backend,window,quitting=false;
const {choosePort}=require('./port.cjs');
let port,origin;
const token=require('node:crypto').randomBytes(24).toString('hex');
function ready(){return new Promise(resolve=>{const req=http.get(origin+'/api/desktop-ready',res=>{let data='';res.on('data',chunk=>data+=chunk);res.on('end',()=>resolve(data===token));});req.on('error',()=>resolve(false));req.setTimeout(1000,()=>{req.destroy();resolve(false);});});}
async function start(){
 window=new BrowserWindow({width:1400,height:950,minWidth:900,minHeight:640,title:'Night City Broadcaster',backgroundColor:'#101216',autoHideMenuBar:true,webPreferences:{nodeIntegration:false,contextIsolation:true,sandbox:true}});
 window.webContents.setWindowOpenHandler(({url})=>{if(url.startsWith(origin+'/'))window.loadURL(url);else if(/^https?:/.test(url))shell.openExternal(url);return {action:'deny'};});
 window.webContents.on('will-navigate',(event,url)=>{if(new URL(url).origin!==origin){event.preventDefault();if(/^https?:/.test(url))shell.openExternal(url);}});
 await window.loadFile(path.join(__dirname,'startup.html'));
 if(quitting)return;
 port=await choosePort(Number(process.env.NCB_PORT||8766));
 origin='http://127.0.0.1:'+port;
 const root=app.isPackaged?path.join(process.resourcesPath,'backend'):path.join(__dirname,'backend','ncb-server');
 const embedded=process.platform==='win32'&&require('node:fs').existsSync(path.join(root,'python.exe'));
 backend=spawn(path.join(root,embedded?'python.exe':process.platform==='win32'?'ncb-server.exe':'ncb-server'),embedded?[path.join(root,'server.py')]:[],{env:{...process.env,NCB_PORT:String(port),NCB_DATA_DIR:app.getPath('userData'),NCB_SESSION_TOKEN:token,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'},stdio:['ignore','pipe','pipe'],windowsHide:true});
 backend.stdout.resume();
 let tail='';backend.stderr.on('data',d=>{tail=(tail+d).slice(-8000);});
 backend.on('error',error=>{dialog.showErrorBox('Could not start Night City Broadcaster',error.message);app.quit();});
 backend.on('exit',()=>{if(!quitting){dialog.showErrorBox('Broadcast service stopped',tail||'The service exited unexpectedly.');app.quit();}});
 let ok=false;for(let i=0;i<120;i++){if(quitting)return;if(await ready()){ok=true;break;}await new Promise(r=>setTimeout(r,500));}
 if(!ok){dialog.showErrorBox('Could not start the service','The local service did not become ready. Please reopen the app.\n\n'+tail);app.quit();return;}
 if(quitting)return;
 await window.loadURL(origin+'/operator');
 console.log('Night City Broadcaster window loaded');
 if(app.isPackaged) void recommendUpdate();
}
async function recommendUpdate(){
 try{
  const update=await checkForUpdate(app.getVersion());
  if(!update||quitting||!window||window.isDestroyed())return;
  const {response}=await dialog.showMessageBox(window,{type:'info',title:'Update available',message:`Night City Broadcaster ${update.version} is available`,detail:`You’re running ${app.getVersion()}. Download the latest build from GitHub, then close this app before opening the new version. Your saved data will be kept.`,buttons:['Open download page','Later'],defaultId:0,cancelId:1});
  if(response===0&&!quitting)await shell.openExternal(update.url);
 }catch(error){console.warn('Update check unavailable:',error.message);}
}
if(!app.requestSingleInstanceLock()){app.quit();}else{
 app.on('second-instance',()=>{if(window){if(window.isMinimized())window.restore();window.focus();}});
 app.whenReady().then(start).catch(error=>{dialog.showErrorBox('Could not start',error.message);app.quit();});
 app.on('window-all-closed',()=>app.quit());
 app.on('before-quit',()=>{quitting=true;if(backend){backend.kill();backend=null;}});
}

process.on('SIGTERM',()=>app.quit());process.on('SIGINT',()=>app.quit());
