const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

function sourceFiles(root, folder) {
  return fs.readdirSync(path.join(root, folder), {withFileTypes:true}).flatMap(entry => {
    if (['cards', '__pycache__'].includes(entry.name)) return [];
    const name = folder + '/' + entry.name;
    if (entry.isDirectory()) return sourceFiles(root, name);
    return /\.(py|js|cjs|html|css)$/.test(name) ? [name] : [];
  });
}

function verify(root, backend) {
  const fail = () => { throw new Error('Backend is missing or stale. Rebuild it with desktop/build_backend.py (or build_windows_backend.py for the Windows cross-build) before packaging.'); };
  const manifestPath = path.join(backend, 'source-manifest.json');
  if (!fs.existsSync(manifestPath)) fail();
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const files = [...sourceFiles(root, 'app'), ...sourceFiles(root, 'scripts'), 'desktop/server.py'];
  if (files.length !== Object.keys(manifest).length) fail();
  for (const name of files) {
    const digest = crypto.createHash('sha256').update(fs.readFileSync(path.join(root, name))).digest('hex');
    if (manifest[name] !== digest) fail();
  }
}
exports.verify = verify;
exports.default = async context => {
  const desktop = context.packager.projectDir;
  const resource = context.packager.config.extraResources.find(item => item.to === 'backend');
  verify(path.dirname(desktop), path.resolve(desktop, resource.from));
};
