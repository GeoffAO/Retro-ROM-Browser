# -*- mode: python ; coding: utf-8 -*-
#
# RetroBat ROM Browser — PyInstaller spec
#
# Usage (run from the retrobat_browser folder):
#   pyinstaller retrobat_browser.spec
#
# Output: dist\RetroBat ROM Browser\RetroBat ROM Browser.exe  (folder mode)
#     or: dist\RetroBat ROM Browser.exe                       (one-file mode, slower start)
#
# Set ONEFILE = True below for a single .exe (slower startup ~5-10s on first run).
# Set ONEFILE = False for a folder you zip and distribute (faster startup).

ONEFILE = False

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        # PyQt6 modules that PyInstaller may miss
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.QtMultimedia',         # bundled inside PyQt6, no separate install needed
        'PyQt6.QtMultimediaWidgets',  # same
        'PyQt6.sip',
        # lxml
        'lxml',
        'lxml.etree',
        'lxml._elementpath',
        # Pillow codecs
        'PIL',
        'PIL.Image',
        'PIL.PngImagePlugin',
        'PIL.JpegImagePlugin',
        'PIL.WebPImagePlugin',
        'PIL.GifImagePlugin',
        # Our package
        'retrobat_browser',
        'retrobat_browser.app',
        'retrobat_browser.core',
        'retrobat_browser.core.models',
        'retrobat_browser.core.scanner',
        'retrobat_browser.core.library',
        'retrobat_browser.core.settings',
        'retrobat_browser.ui',
        'retrobat_browser.ui.main_window',
        'retrobat_browser.ui.grid_view',
        'retrobat_browser.ui.list_view',
        'retrobat_browser.ui.detail_panel',
        'retrobat_browser.ui.sidebar',
        'retrobat_browser.ui.toolbar',
        'retrobat_browser.ui.styles',
        'retrobat_browser.ui.loading',
        'retrobat_browser.ui.image_loader',
        'retrobat_browser.ui.edit_dialog',
        'retrobat_browser.ui.batch_edit_dialog',
        'retrobat_browser.ui.scrape_dialog',
        'retrobat_browser.ui.sync_dialog',
        'retrobat_browser.ui.duplicate_finder_dialog',
    ],
    hookspath=['.'],          # look for hook-*.py in this folder
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'scipy',
        'IPython', 'notebook', 'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='RetroBat ROM Browser',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,          # no console window
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,              # set to 'icon.ico' if you have one
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='RetroBat ROM Browser',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        icon=None,              # set to 'icon.ico' if you have one
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='RetroBat ROM Browser',
    )
