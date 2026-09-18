const https = require('node:https');
const RELEASES = 'https://github.com/criticalkunic/Night-City-Broadcaster/releases/';
const API = 'https://api.github.com/repos/criticalkunic/Night-City-Broadcaster/releases/latest';

function versionParts(value) {
  const match = /^v?(\d+)\.(\d+)\.(\d+)(?:[.+](\d+))?$/.exec(value || '');
  return match ? match.slice(1).map(part => Number(part || 0)) : null;
}
function availableUpdate(current, release) {
  if (!release || release.draft || release.prerelease) return null;
  const installed = versionParts(current), latest = versionParts(release.tag_name);
  if (!installed || !latest) return null;
  let newer = false;
  for (let i=0; i<4; i++) {
    if (latest[i] === installed[i]) continue;
    newer = latest[i] > installed[i]; break;
  }
  if (!newer || typeof release.html_url !== 'string' || !release.html_url.startsWith(RELEASES+'tag/')) return null;
  return {version: release.tag_name.replace(/^v/, ''), url: release.html_url};
}
function checkForUpdate(current, get = https.get) {
  return new Promise(resolve => {
    let request, timer, done = false;
    const finish = result => {
      if (done) return;
      done = true; clearTimeout(timer); resolve(result);
    };
    timer = setTimeout(() => {finish(null); request?.destroy();}, 5000);
    try {
      request = get(API, {headers:{'Accept':'application/vnd.github+json','User-Agent':'Night-City-Broadcaster/'+current}}, response => {
        if (response.statusCode !== 200) {response.resume();finish(null);return;}
        let body = '';
        response.setEncoding('utf8');
        response.on('data', chunk => {
          body += chunk;
          if (body.length > 262144) {finish(null);request?.destroy();}
        });
        response.on('error', () => finish(null));
        response.on('end', () => {
          try {finish(availableUpdate(current,JSON.parse(body)));} catch {finish(null);}
        });
      });
      request.on('error', () => finish(null));
    } catch {finish(null);}
  });
}
exports.availableUpdate = availableUpdate;
exports.checkForUpdate = checkForUpdate;
