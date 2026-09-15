const fs = require('node:fs');
const path = require('node:path');

function userDataDirectory(appData) {
  const current = path.join(appData, 'Night City Broadcaster');
  const legacy = path.join(appData, 'Night City Broadcast');
  // Keep existing profiles in place: settings, artwork, cookies and instance lock.
  return !fs.existsSync(current) && fs.existsSync(legacy) ? legacy : current;
}
exports.userDataDirectory = userDataDirectory;
