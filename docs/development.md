# Development

The web app uses FastAPI, OpenCV, and browser JavaScript. Electron launches a bundled Python service for the standalone app. There is no frontend bundler.

## Local setup

Use Python 3.12 or newer. From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./start.sh
```

Open `http://localhost:8766/operator`. Artwork is downloaded during first-launch setup. To work with an isolated data directory, set `NCB_DATA_DIR` before launching.

## Project layout

| Path | Contents |
| --- | --- |
| `app/api/` | HTTP endpoints and camera controls |
| `app/game/` | Card database, match state, artwork downloads |
| `app/vision/` | Camera capture, detection, and recognition |
| `app/static/` | Match controls, camera setup, stream layouts, and Debug |
| `scripts/` | Catalog import and maintenance commands |
| `desktop/` | Electron entry point and packaging scripts |
| `tests/` | Python and JavaScript tests |

`config/`, `app/cards/`, and `captures/` are local data directories and are excluded from Git. Desktop builds and dependencies are excluded too.

## Tests

These checks run without a camera, card library, or network access:

```bash
.venv/bin/python -m pytest -q \
  tests/test_first_run.py tests/test_card_back.py \
  tests/test_import_cards.py tests/test_art_download.py

for test in tests/*.cjs; do node "$test" || exit 1; done
```

Node.js 22 is used for the JavaScript checks. Other Python tests cover detection, recognition, API integration, and video capture. Some require local card data or camera fixtures; those fixtures are not distributed because they contain card artwork. Run the relevant tests when those inputs are available rather than treating a missing local fixture as a release failure.

## Refreshing the card catalog

Stop the service before updating the catalog. From the repository root:

```bash
.venv/bin/python -m scripts.import_cards --source cyberpunktcg
.venv/bin/python -m scripts.import_cards --validate
```

Use the same `NCB_DATA_DIR` value as your service if you configured one. The importer follows the current remote catalog and pagination; it does not assume a fixed number of cards. Existing images are reused. Restart the app after importing. Debug’s **Download missing card art** repairs images and alternate references for the existing local catalog.

## Desktop builds

See [Desktop packaging](../desktop/README.md). Build outputs are:

- Linux: an AppImage.
- Windows: a portable `.exe`, with saved data in AppData.

No card catalog or artwork should be included in either package.

## Preparing a GitHub release

1. Create the GitHub repository and push the source. Review `git status` before committing; `.gitignore` excludes personal data, artwork, dependencies, and build outputs.
2. Run **Build desktop applications** from the Actions tab. It builds on Ubuntu and Windows and uploads application artifacts. It does not publish a release automatically.
3. Test the downloaded applications, including first launch with an empty data directory and a real camera on each supported system.
4. Create a GitHub release with a version tag matching `desktop/package.json` and attach the `.AppImage` and `-Windows.exe` files. GitHub supplies the source ZIP automatically.

Do not commit the binaries: they exceed GitHub’s normal Git file-size limit. `releases/` is a local staging folder for downloadable applications; unpacked applications and builder logs remain under `desktop/build/packages/`.

To prepare a clean source ZIP without a GitHub repository:

```bash
python3 scripts/source_archive.py /tmp/night-city-broadcast-source.zip
```

This requires Git and uses the repository’s ignore rules. It includes source and documentation, not application binaries. Add the standalone files separately as GitHub release assets.

Project code is licensed under GPL-3.0-only. Publish the corresponding source for each binary release, including build scripts and any changes used to produce it. Retain bundled third-party license notices. Artwork is not covered by the project’s code license.
