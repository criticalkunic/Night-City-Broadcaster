# Changelog

User-facing changes are recorded here for each release. Development changes belong under **Unreleased** until they ship.

## Unreleased

## 1.0.3 — 2026-09-15

### Added

- Desktop startup checks for a newer stable GitHub release and offers to open its download page. Offline checks do not block startup, and updates remain manual.

### Changed

- Renamed the app to **Night City Broadcaster** across the interface, desktop windows, download filenames, and documentation.
- Existing desktop installs retain their saved settings, downloaded artwork, and player-name cookies by continuing to use their original data folder. New installs use a folder named Night City Broadcaster.
- Added this changelog and a release-note step to the contribution and packaging guides.

## 1.0.2 — 2026-09-15

### Added

- **Debug → Check for new cards** imports new card identities, downloads their artwork and alternate references, and refreshes recognition without restarting.
- Packaging checks reject stale backend files before creating desktop downloads.

### Changed

- The OBS stream URL is now `/broadcast/live`. Previous `/overlay/live` links redirect to it.
- Updated the README with real stream and board-setup screenshots, portable Windows instructions, and platform testing information.
- Added R. Talsorian Games to the trademark acknowledgments.

Version 1.0.1 was a local build; these changes first shipped publicly in 1.0.2.

## 1.0.0 — 2026-09-15

### Added

- Initial public release with Linux AppImage and portable Windows executable.
- Webcam card recognition, latest-play artwork, legend tracking, and manual gig controls.
- Minimal and Full board layouts using one OBS browser source.
- First-launch catalog and artwork downloads, including the legend card back.
