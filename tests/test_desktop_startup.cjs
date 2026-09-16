const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),{EventEmitter}=require('node:events');
const calls=[];let env;
const app={getPath:()=>'/tmp',setPath(){},requestSingleInstanceLock:()=>true,on(){},whenReady:()=>Promise.resolve(),isPackaged:false,quit(){calls.push('quit');}};
class Window{constructor(){calls.push('window');this.webContents={setWindowOpenHandler(){},on(){}};}async loadFile(){calls.push('splash');}async loadURL(){calls.push('service-page');}}
const modules={electron:{app,BrowserWindow:Window,dialog:{showErrorBox(...args){throw Error(args.join(':'));}},shell:{}},'node:child_process':{spawn(file,args,options){calls.push('backend');env=options.env;return Object.assign(new EventEmitter(),{stdout:{resume(){}},stderr:new EventEmitter()});}},'node:path':require('node:path'),'node:fs':{mkdirSync(){},existsSync(){return false;}},'node:crypto':{randomBytes:()=>({toString:()=> 'test-token'})},'./port.cjs':{choosePort:async()=>8766},'./user-data.cjs':{userDataDirectory:()=>'/tmp'},'./update-check.cjs':{},'node:http':{get(url,callback){const request={on(){},setTimeout(){}};queueMicrotask(()=>{const response=new EventEmitter();callback(response);response.emit('data','test-token');response.emit('end');});return request;}}};
vm.runInNewContext(fs.readFileSync('desktop/main.cjs','utf8'),{require:name=>modules[name],__dirname:'/desktop',process:{env:{},platform:'win32',on(){}},console:{log(){}},setTimeout,URL});
setImmediate(()=>{
 assert.deepEqual(calls,['window','splash','backend','service-page']);
 assert.equal(env.PYTHONUTF8,'1');assert.equal(env.PYTHONIOENCODING,'utf-8');
 for(const file of ['desktop/package.json','desktop/windows-builder.json']){
  const config=JSON.parse(fs.readFileSync(file));const build=config.build||config;
  assert(build.files.includes('startup.html'));
  assert.equal(fs.readFileSync('desktop/'+build.portable.splashImage).subarray(0,2).toString(),'BM');
 }
 console.log('Startup window precedes backend; UTF-8 environment and portable extraction splash configured.');
});
