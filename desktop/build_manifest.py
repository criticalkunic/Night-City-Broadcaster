"""Record source inputs so packaging cannot silently reuse an old backend."""
import hashlib
import json
from pathlib import Path


def stamp(root, backend):
    files = []
    for folder in ('app', 'scripts'):
        files.extend(p for p in (root/folder).rglob('*')
                     if p.is_file() and p.suffix in ('.py', '.js', '.cjs', '.html', '.css')
                     and not {'cards', '__pycache__'}.intersection(p.relative_to(root).parts))
    files.append(root/'desktop/server.py')
    manifest = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(files)}
    (backend/'source-manifest.json').write_text(json.dumps(manifest, sort_keys=True))
