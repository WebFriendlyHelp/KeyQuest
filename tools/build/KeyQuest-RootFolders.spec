# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for KeyQuest with games/ and Sentences/ in root folder

import os
import sys

from PyInstaller.utils.hooks import collect_submodules

# Find cytolk DLLs for screen reader support
cytolk_binaries = []
try:
    import cytolk
    cytolk_dir = os.path.dirname(cytolk.__file__)
    for file in os.listdir(cytolk_dir):
        if file.endswith(('.dll', '.pyd')):
            cytolk_binaries.append((os.path.join(cytolk_dir, file), '.'))
    print(f"Found {len(cytolk_binaries)} cytolk binaries to bundle")
except Exception as e:
    print(f"Warning: Could not find cytolk binaries: {e}")

# Data files - DO NOT bundle games/ and Sentences/ (will be copied manually to root)
# This allows them to be easily accessible and modifiable by users
datas = []
REPO_ROOT = os.path.abspath(os.getcwd())

a = Analysis(
    [os.path.join(REPO_ROOT, 'keyquest.pyw')],
    pathex=[REPO_ROOT],
    binaries=cytolk_binaries,
    datas=datas,
    hiddenimports=[
        'cytolk',
        'pyttsx3',
        'pyttsx3.drivers',
        'pyttsx3.drivers.sapi5',
        *collect_submodules('modules'),
        *collect_submodules('ui'),
        *collect_submodules('games'),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pkg_resources',
        'setuptools',
        'jaraco',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KeyQuest',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='KeyQuest',
)

# Post-build: Copy folders to root (alongside .exe)
import shutil
import fnmatch
dist_dir = os.path.join(DISTPATH, 'KeyQuest')
print("\n=== Copying folders to distribution root ===")

COMMON_IGNORE_PATTERNS = (
    '__pycache__',
    '*.pyc',
    '*.pyo',
    '*.pyd',
    '.DS_Store',
    'Thumbs.db',
    '.pytest_cache',
    '.mypy_cache',
    '.ruff_cache',
)

def make_ignore(extra_patterns=()):
    patterns = COMMON_IGNORE_PATTERNS + tuple(extra_patterns)

    def _ignore(_dir, names):
        ignored = set()
        for name in names:
            for pattern in patterns:
                if fnmatch.fnmatch(name, pattern):
                    ignored.add(name)
                    break
        return ignored

    return _ignore

# Copy program folders
for folder in ['modules', 'games', 'Sentences', 'ui']:
    src = os.path.join(REPO_ROOT, folder)
    dst = os.path.join(dist_dir, folder)
    if os.path.exists(dst):
        shutil.rmtree(dst)

    shutil.copytree(src, dst, ignore=make_ignore())
    print(f"Copied {folder}/ to {dst}")

# Copy user docs into distribution docs folder.
docs_dst = os.path.join(dist_dir, 'docs')
if os.path.exists(docs_dst):
    shutil.rmtree(docs_dst)
os.makedirs(docs_dst, exist_ok=True)

readme_src = os.path.join(REPO_ROOT, 'README.md')
if os.path.exists(readme_src):
    shutil.copy(readme_src, os.path.join(docs_dst, 'README.md'))
    print("Copied README.md to distribution docs")

readme_html_src = os.path.join(REPO_ROOT, 'README.html')
if os.path.exists(readme_html_src):
    shutil.copy(readme_html_src, os.path.join(docs_dst, 'README.html'))
    print("Copied README.html to distribution docs")

whats_new_src = os.path.join(REPO_ROOT, 'docs', 'user', 'WHATS_NEW.md')
if os.path.exists(whats_new_src):
    shutil.copy(whats_new_src, os.path.join(docs_dst, 'WHATS_NEW.md'))
    print("Copied WHATS_NEW.md to distribution docs")

# Copy readmes to root for easy access
if os.path.exists(readme_src):
    shutil.copy(readme_src, os.path.join(dist_dir, 'README.md'))
    print("Copied README.md to distribution root")
if os.path.exists(readme_html_src):
    shutil.copy(readme_html_src, os.path.join(dist_dir, 'README.html'))
    print("Copied README.html to distribution root")

print("=== Folders copied successfully! ===\n")
