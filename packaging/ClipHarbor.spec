# Build in the small .build-env, never collect the user's full Conda environment.
from pathlib import Path
import os
import sys
from PyInstaller.utils.hooks import collect_all, copy_metadata
import pefile

root = Path(SPECPATH).parent
sys.path.insert(0, SPECPATH)
from tk_bundle import loaded_tk_runtime
tk_runtime = loaded_tk_runtime()
# Include adjacent non-system dependencies too (Conda's Tcl uses zlib1.dll).
pending = list(tk_runtime['libraries'].values())
while pending:
    library = Path(pending.pop())
    with pefile.PE(str(library)) as binary:
        for dependency in getattr(binary, 'DIRECTORY_ENTRY_IMPORT', []):
            name = dependency.dll.decode('ascii')
            local = library.parent / name
            if name.lower() not in {key.lower() for key in tk_runtime['libraries']} and local.is_file():
                tk_runtime['libraries'][name] = str(local)
                pending.append(str(local))
print('Matched Tcl/Tk runtime:', tk_runtime['tcl_version'], tk_runtime['tk_version'])
datas = [(str(root / 'static'), 'static'), (str(root / 'templates'), 'templates'),
         (str(root / 'packaging' / 'vendor' / 'node.exe'), 'tools'),
         (str(root / 'packaging' / 'vendor' / 'licenses' / 'Node-LICENSE.txt'), 'tools/licenses'),
         (str(root / 'packaging' / 'vendor' / 'licenses' / 'Python-LICENSE.txt'), 'tools/licenses'),
         (str(root / 'packaging' / 'licenses'), 'tools/licenses'),
         (str(root / 'packaging' / 'THIRD-PARTY-NOTICES.md'), '.'),
         (str(root / 'packaging' / 'FAMILY-README.txt'), '.')]
# This is the publisher's Desktop app registration, never an end user's tokens.
google_client_file = Path(os.environ.get('CLIPHARBOR_GOOGLE_CLIENT_FILE', root / 'google-oauth-client.json')).expanduser()
if google_client_file.is_file():
    import json
    registration = json.loads(google_client_file.read_text(encoding='utf-8'))
    if not isinstance(registration.get('installed'), dict) or not registration['installed'].get('client_id'):
        raise RuntimeError('Google registration must be an OAuth Desktop app client JSON')
    if any(key in record for record in (registration, registration['installed']) for key in ('access_token', 'refresh_token', 'token')):
        raise RuntimeError('Never bundle user tokens in a Google client registration')
    normalized_google_client = root / 'build' / 'publisher-google-client.json'
    normalized_google_client.parent.mkdir(parents=True, exist_ok=True)
    normalized_google_client.write_text(json.dumps({'installed': {
        key: registration['installed'][key] for key in ('client_id', 'client_secret')
        if key in registration['installed']
    }}), encoding='utf-8')
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
             # Optional thumbnail-tagging library is not used by ClipHarbor.
             # Keep GPL-linked Mutagen out of this independent application bundle.
             excludes=['numpy', 'scipy', 'pytest', 'IPython', 'matplotlib', 'mutagen'], noarchive=False)
if google_client_file.is_file():
    # Normalize the runtime name even when the downloaded registration has a
    # provider-generated file name such as client_secret_1234.json.
    a.datas.append(('google-oauth-client.json', str(normalized_google_client), 'DATA'))
assert not any(entry[0] == 'mutagen' or entry[0].startswith('mutagen.') for entry in a.pure)
assert not any(Path(entry[0]).name.lower() in {'ffmpeg.exe', 'ffprobe.exe'} for entry in a.datas + a.binaries)
# The dependency scanner can resolve DLLs from another Conda environment on PATH.
# Override it with the exact libraries that successfully initialized above.
tk_names = {name.lower() for name in tk_runtime['libraries']}
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() not in tk_names]
a.binaries += [(name, source, 'BINARY') for name, source in tk_runtime['libraries'].items()]
for destination, key in [('_tcl_data', 'tcl_data'), ('_tk_data', 'tk_data')]:
    a.datas = [entry for entry in a.datas if Path(entry[0]).parts[0] != destination]
    source_root = Path(tk_runtime[key])
    a.datas += [(str(Path(destination) / item.relative_to(source_root)), str(item), 'DATA')
                for item in source_root.rglob('*') if item.is_file()]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ClipHarbor',
          debug=False, strip=False, upx=False, console=False,
          icon=str(root / 'static' / 'carl-logo.png'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ClipHarbor')
