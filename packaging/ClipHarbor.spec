# Build in the small .build-env, never collect the user's full Conda environment.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata

root = Path(SPECPATH).parent
datas = [(str(root / 'static'), 'static'), (str(root / 'templates'), 'templates'),
         (str(root / 'packaging' / 'vendor'), 'tools'),
         (str(root / 'packaging' / 'THIRD-PARTY-NOTICES.md'), '.'),
         (str(root / 'packaging' / 'FAMILY-README.txt'), '.')]
binaries, hiddenimports = [], ['tkinter', 'tkinter.filedialog', 'waitress']
for package in ['yt_dlp', 'yt_dlp_ejs']:
    data, binary, hidden = collect_all(package)
    datas += data
    binaries += binary
    hiddenimports += hidden
for package in ['yt-dlp', 'yt-dlp-ejs', 'Flask', 'waitress', 'certifi']:
    datas += copy_metadata(package, recursive=True)

a = Analysis([str(root / 'desktop.py')], pathex=[str(root)], binaries=binaries,
             datas=datas, hiddenimports=hiddenimports,
             excludes=['numpy', 'scipy', 'pytest', 'IPython', 'matplotlib'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ClipHarbor',
          debug=False, strip=False, upx=False, console=False,
          icon=str(root / 'static' / 'carl-logo.png'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ClipHarbor')
