"""Export source using .gitignore, without touching the project's Git index."""
import argparse
from pathlib import Path
import subprocess
import tempfile
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    output = args.output.resolve()
    with tempfile.TemporaryDirectory(prefix='ncb-source-') as temporary:
        subprocess.run(['git', 'init', '--bare', '--quiet', temporary], check=True)
        names = subprocess.check_output([
            'git', '--git-dir='+temporary, '--work-tree='+str(root),
            'ls-files', '--others', '--exclude-standard', '-z',
        ], cwd=root).decode().split('\0')
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(filter(None, names)):
                path = root/name
                if path.resolve() == output or path.is_symlink():
                    continue
                archive.write(path, 'night-city-broadcast/'+name)
    print(output)


if __name__ == '__main__':
    main()
