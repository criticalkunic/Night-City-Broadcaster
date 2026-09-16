# Changelog

User-facing changes are recorded here for each release. Development changes belong under **Unreleased** until they ship.

## Unreleased

## 1.0.10 — 2026-09-16

### Added

- Guided camera setup in a focused window, offered on first use and reopenable from Camera setup. Short instructions, animated examples and automatic area selection walk through mat framing, perspective and zones. Adjustments save before advancing.
- Minimal and full-board streams share circuit-grid details, cut-corner accents and theme-aware panel styling.

### Changed

- Short camera exposure is now the default; camera setup explains automatic exposure’s brightness and frame-rate tradeoff.
- Removed redundant walkthrough steps. Each zone appears in sequence, with earlier zones shown as dotted outlines.
- Saving perspective now sizes the corrected board from the mat corners instead of forcing 4:3. Camera previews preserve their image proportions.


## 1.0.9 — 2026-09-16

### Added

- Camera exposure controls now support Linux V4L2 cameras, including short exposure and restoring automatic exposure. Troubleshooting labels exposure readings with the correct units for each platform.

## 1.0.8 — 2026-09-16

### Added

- Optional Windows camera exposure modes: keep existing settings, automatic, or short exposure (1/64 second) to test exposure-limited capture rates. Troubleshooting reports the driver exposure values.

## 1.0.7 — 2026-09-16

### Fixed

- Windows camera negotiation now requests MJPEG after setting the frame rate and resolution, preventing DirectShow from discarding the requested compressed format during its FPS change.

### Added

- Troubleshooting video-performance measurements show capture backend, pixel format, reported FPS, and per-feed processing throughput and time.

## 1.0.6 — 2026-09-16

### Added

- **Camera setup → Rotate camera 180°** turns upside-down overhead feeds upright for preview, recognition, and both broadcast layouts.

## 1.0.5 — 2026-09-16

### Fixed

- First-launch artwork setup and catalog updates save and read UTF-8 explicitly, fixing Windows failures on card names containing characters such as ☆.

### Added

- A Windows portable extraction notice and an immediate desktop startup activity screen while the local service starts. First-launch artwork progress now distinguishes catalog fetching and recognition preparation.

## 1.0.4 — 2026-09-16

### Added

- **Stream settings → Match artwork to the detected card** shows the recognized official printing for card reveals and legends in both layouts and the player console. Regular artwork remains the default.

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
