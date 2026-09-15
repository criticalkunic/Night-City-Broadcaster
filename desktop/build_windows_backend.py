"""Assemble official embedded CPython + Windows wheels; works on Linux too."""
from pathlib import Path
import urllib.request, zipfile, io, subprocess, sys, shutil
root=Path(__file__).resolve().parent.parent
out=root/'desktop/backend-windows/ncb-server'
out.mkdir(parents=True,exist_ok=True)
url='https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'
with urllib.request.urlopen(url,timeout=60) as response:
    zipfile.ZipFile(io.BytesIO(response.read())).extractall(out)
(out/'python312._pth').write_text('python312.zip\n.\nLib/site-packages\nimport site\n')
subprocess.run([sys.executable,'-m','pip','install','--upgrade','--target',str(out/'Lib/site-packages'),
 '--platform','win_amd64','--python-version','3.12','--implementation','cp','--only-binary=:all:',
 'fastapi','uvicorn','websockets','pydantic','opencv-python','numpy','pygrabber','comtypes'],check=True)
shutil.copytree(root/'app',out/'app',dirs_exist_ok=True,ignore=shutil.ignore_patterns('cards','static','__pycache__'))
shutil.copytree(root/'scripts',out/'scripts',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
if (out/'app/static').exists():
    shutil.rmtree(out/'app/static')
shutil.copytree(root/'desktop/build/distribution-assets/static',out/'app/static')
(out/'config').mkdir(exist_ok=True)
shutil.copy2(root/'desktop/server.py',out/'server.py')
print('Windows backend ready:',out)

from build_manifest import stamp
stamp(root, out)
