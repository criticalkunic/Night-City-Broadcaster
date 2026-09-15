# Night City Broadcaster desktop

**Platform support:** I use Linux and can only test the app on Linux. A Windows build is provided and should work in theory, but I can’t verify it on Windows. Reports from Windows users are welcome.

Linux: double-click the AppImage in `releases/` (mark it executable in file properties if needed). Windows: double-click `Night City Broadcaster-1.0.3-Windows.exe`. The portable app launches directly. Keep the executable wherever you like; it extracts its runtime into a temporary folder when launched. Settings and downloaded art remain in `%APPDATA%\Night City Broadcaster`, including when you replace or move the executable. Close the app before replacing its executable.

The app includes Python and recognition dependencies, but no card catalog or artwork. First launch fetches the complete current website catalog, saves it locally, then downloads and validates every required card image and alternate reference before allowing access to the app or OBS stream. Failed or interrupted downloads keep the app locked and can be retried; completed files are reused. Future launches skip this step when artwork is complete. The legend card back is downloaded from the public Beyond TCG gallery during setup and cached in user data; no card back is bundled. It starts a private localhost service on port 8766 and stops that service when the app closes. If port 8766 is already occupied, the desktop app automatically chooses a free port without interrupting the existing service. Copy the current OBS link from Stream settings. The default OBS URL is http://127.0.0.1:8766/broadcast/live; use the link shown in Stream settings if the app selects another port.

Settings, captures and artwork downloads live in Electron's user-data directory: `~/.config/Night City Broadcaster` on Linux and `%APPDATA%/Night City Broadcaster` on Windows. First launch uses clean camera defaults. Your existing browser installation is untouched. Choose and configure your webcam in Camera setup. Player names are stored in the desktop app's persistent browser cookies.

Existing desktop installs continue using their original `Night City Broadcast` data folder, so settings, artwork, and saved player names carry over. Fresh installs use `Night City Broadcaster`.

## Build on the target operating system

Install Node.js 22 and Python 3.12+, then from the project directory:

```
python -m pip install -r requirements.txt pyinstaller
python desktop/build_backend.py
cd desktop
npm ci
npm run dist
```

Only downloadable applications appear in `releases/`, ready to attach to a GitHub release. Extracted builds, blockmaps and builder logs stay in `desktop/build/packages/`. Build Windows portable executables on Windows and Linux packages on Linux; the bundled Python backend is OS-specific. The included manual GitHub Actions workflow builds both. Windows camera discovery uses DirectShow. Windows builds are provided without native Windows verification. Windows executables are currently unsigned.

For wider Linux compatibility use the Ubuntu 22.04 build in the workflow. A package built on a newer distribution may require that distribution's newer glibc. AppImage launch requires FUSE support; use `--appimage-extract` and launch `squashfs-root/AppRun` on systems without it.

A Windows x64 portable executable is included in releases. It bundles official CPython 3.12.10 and Windows wheels. Its backend was smoke-tested under Wine on Linux; this does not verify that the app or camera capture works on Windows. To reproduce that cross-build, run `python desktop/build_windows_backend.py`, then in desktop run `npm run dist -- --win --config windows-builder.json` after generating the shared distribution assets with build_backend.py.

Packaging checks the backend against current source files and stops if it is stale. Re-run the backend build after changing application code, then run `npm run dist`.
