"""Run using the build environment's Python, on each target OS."""
from pathlib import Path
import subprocess
import sys
import shutil
root = Path(__file__).resolve().parent.parent
seed = root/'desktop/build/default-config'
seed.mkdir(parents=True, exist_ok=True)
(seed/'overlay.json').write_text('{}')
assets = root/'desktop/build/distribution-assets'
if assets.exists():
    shutil.rmtree(assets)
shutil.copytree(root/'app/static', assets/'static', ignore=shutil.ignore_patterns('*.webp', '*.png', '*.jpg', '*.jpeg'))

subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
    '--name', 'ncb-server', '--onedir', '--paths', str(root),
    '--distpath', str(root/'desktop/backend'), '--workpath', str(root/'desktop/build'),
    '--specpath', str(root/'desktop/build'),
    '--collect-submodules', 'app', '--collect-submodules', 'scripts',
    '--collect-all', 'certifi', '--collect-all', 'uvicorn', '--collect-all', 'cv2',
    '--add-data', f'{assets / "static"}:app/static',
    '--add-data', f'{seed}:config',
    str(root/'desktop/server.py')], check=True)

from build_manifest import stamp
stamp(root, root/'desktop/backend/ncb-server')
