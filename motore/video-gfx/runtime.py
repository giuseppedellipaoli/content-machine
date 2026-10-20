"""Portable execution for the native renderer. Never installs tools or browsers."""
import json
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
shared_path = ROOT.parent / 'runtime.py'
if shared_path.is_file():
    spec = importlib.util.spec_from_file_location('content_machine_shared_runtime', shared_path)
    shared = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shared)
    shared.ensure_env()
CACHE = Path(os.environ.get('CONTENT_MACHINE_CACHE', str(ROOT.parent.parent / 'work' / 'cache'))).expanduser().resolve()
(CACHE / 'tmp').mkdir(parents=True, exist_ok=True)
for key in ('TEMP', 'TMP', 'TMPDIR'):
    os.environ[key] = str(CACHE / 'tmp')
tempfile.tempdir = str(CACHE / 'tmp')

def executable(env, name):
    chosen = os.environ.get(env)
    if chosen:
        path = shutil.which(chosen) or (chosen if Path(chosen).is_file() else None)
        if not path:
            raise RuntimeError(f'{env} points to a missing executable.')
        return path
    return shutil.which(name) or name

FFMPEG = executable('FFMPEG_PATH', 'ffmpeg')
FFPROBE = executable('FFPROBE_PATH', 'ffprobe')

def browser_path():
    explicit = os.environ.get('REMOTION_BROWSER_EXECUTABLE') or os.environ.get('CHROME_PATH') or os.environ.get('MOTORE_CHROME')
    candidates = [explicit] if explicit else [
        shutil.which('google-chrome'), shutil.which('chromium'), shutil.which('chromium-browser'),
        str(Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe'),
        str(Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe'),
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise RuntimeError('System Chrome/Chromium/Edge missing. Set REMOTION_BROWSER_EXECUTABLE or CHROME_PATH. No browser downloaded.')

def remotion(args, *, browser=True, **kwargs):
    package = ROOT / 'node_modules' / '@remotion' / 'cli' / 'package.json'
    if not package.is_file():
        raise RuntimeError('Remotion dependencies missing. Run the documented setup explicitly first.')
    meta = json.loads(package.read_text(encoding='utf-8'))
    entry = meta['bin']['remotion'] if isinstance(meta['bin'], dict) else meta['bin']
    args = list(args)
    if args and args[0] == 'render' and not any(a == '--concurrency' or a.startswith('--concurrency=') for a in args):
        try:
            concurrency = int(os.environ.get('MOTORE_CONCURRENCY', os.environ.get('REMOTION_CONCURRENCY', '2')))
        except ValueError as error:
            raise RuntimeError('MOTORE_CONCURRENCY must be an integer from 1 to 16.') from error
        if not 1 <= concurrency <= 16:
            raise RuntimeError('MOTORE_CONCURRENCY must be an integer from 1 to 16.')
        args.append(f'--concurrency={concurrency}')
    command = [executable('NODE_PATH', 'node'), str(package.parent / entry), *args]
    if browser:
        command += ['--browser-executable=' + browser_path(), '--chrome-mode=chrome-for-testing']
    kwargs.setdefault('cwd', str(ROOT))
    if sys.platform == 'win32':
        kwargs.setdefault('creationflags', subprocess.CREATE_NO_WINDOW)
    return subprocess.run(command, **kwargs)
