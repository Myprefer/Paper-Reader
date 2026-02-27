# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置
用法: pyinstaller build.spec --clean -y
"""

import os

block_cipher = None
BASE = os.path.abspath('.')

a = Analysis(
    ['desktop.py'],
    pathex=[BASE],
    binaries=[],
    datas=[
        # 前端构建产物（打包进 _MEIPASS）
        ('frontend/dist', 'frontend/dist'),
        # 应用图标
        ('assets/app.ico', 'assets'),
    ],
    hiddenimports=[
        'backend',
        'backend.app',
        'backend.config',
        'backend.db',
        'backend.routes',
        'backend.routes.tree',
        'backend.routes.papers',
        'backend.routes.notes',
        'backend.routes.images',
        'backend.services',
        'backend.services.gemini',
        'engineio.async_drivers.threading',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', '_tkinter',
        'matplotlib', 'scipy', 'numpy.distutils',
        'test', 'unittest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PaperReader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,      # 无控制台窗口
    icon='assets/app.ico',
    version='version_info.py',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PaperReader',
)
