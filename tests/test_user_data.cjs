const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
const {userDataDirectory}=require('../desktop/user-data.cjs');
const root=fs.mkdtempSync(path.join(os.tmpdir(),'ncb-profile-'));
try {
 const old=path.join(root,'Night City Broadcast'),current=path.join(root,'Night City Broadcaster');
 assert.equal(userDataDirectory(root),current);
 fs.mkdirSync(old);fs.writeFileSync(path.join(old,'settings'),'preserved');
 assert.equal(userDataDirectory(root),old);
 assert.equal(fs.readFileSync(path.join(old,'settings'),'utf8'),'preserved');
 fs.mkdirSync(current);assert.equal(userDataDirectory(root),current);
 console.log('Profile selection preserves existing data and uses the new name for fresh installs.');
} finally {fs.rmSync(root,{recursive:true,force:true});}
