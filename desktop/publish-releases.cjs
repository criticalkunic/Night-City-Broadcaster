const fs = require('node:fs/promises');
const path = require('node:path');

// Keep build directories, diagnostics and updater blockmaps out of downloads.
exports.default = async function publishReleases({ artifactPaths }) {
  const releases = path.resolve(__dirname, '../releases');
  await fs.mkdir(releases, { recursive: true });
  for (const artifact of artifactPaths) {
    if (!/\.(AppImage|exe|deb)$/.test(artifact)) continue;
    await fs.copyFile(artifact, path.join(releases, path.basename(artifact)));
  }
  return [];
};
