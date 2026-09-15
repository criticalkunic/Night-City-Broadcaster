const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const {verify}=require('../desktop/check-backend.cjs');
const root=fs.mkdtempSync(path.join(os.tmpdir(),'ncb-freshness-'));
try {
  for(const dir of ['app','scripts','desktop','backend'])fs.mkdirSync(path.join(root,dir));
  const files={'app/main.py':'print("current")','desktop/server.py':'server'};
  const manifest={};
  for(const [name,data] of Object.entries(files)){fs.writeFileSync(path.join(root,name),data);manifest[name]=crypto.createHash('sha256').update(data).digest('hex');}
  const backend=path.join(root,'backend');
  assert.throws(()=>verify(root,backend),/stale/);
  fs.writeFileSync(path.join(backend,'source-manifest.json'),JSON.stringify(manifest));
  verify(root,backend);
  fs.writeFileSync(path.join(root,'app/main.py'),'changed');
  assert.throws(()=>verify(root,backend),/stale/);
  fs.writeFileSync(path.join(root,'app/main.py'),files['app/main.py']);
  fs.writeFileSync(path.join(root,'app/new.py'),'new');
  assert.throws(()=>verify(root,backend),/stale/);
  fs.unlinkSync(path.join(root,'app/new.py'));
  fs.unlinkSync(path.join(root,'app/main.py'));
  assert.throws(()=>verify(root,backend),/stale/);
  console.log('Packaging guard rejects missing, modified, added and deleted source inputs.');
} finally {fs.rmSync(root,{recursive:true,force:true});}
