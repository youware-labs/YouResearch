# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for YouResearch Backend

Builds a standalone executable that runs the FastAPI server.
Usage: pyinstaller youresearch-backend.spec
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata, collect_all

# Get the backend directory
backend_dir = Path(SPECPATH)

# Collect package metadata that pydantic_ai and other packages need
datas = []
datas += copy_metadata('genai_prices')
datas += copy_metadata('pydantic_ai')
datas += copy_metadata('pydantic_ai_slim')
datas += copy_metadata('pydantic')
datas += copy_metadata('pydantic_core')
datas += copy_metadata('anthropic')
datas += copy_metadata('httpx')
datas += copy_metadata('httpcore')
datas += copy_metadata('fastapi')
datas += copy_metadata('starlette')
datas += copy_metadata('uvicorn')

# Include our source packages
datas += [
    ('agent', 'agent'),
    ('services', 'services'),
]

# Include Tectonic binary
binaries = [
    ('bin/tectonic', 'bin'),
]

a = Analysis(
    ['main.py'],
    pathex=[str(backend_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        # FastAPI and dependencies
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'fastapi',
        'starlette',
        'pydantic',
        'pydantic_core',
        'pydantic_ai',
        'sse_starlette',
        
        # HTTP and async
        'httpx',
        'httpcore',
        'anyio',
        'sniffio',
        'h11',
        'certifi',
        
        # Anthropic
        'anthropic',
        
        # Research tools
        'arxiv',
        'fitz',  # PyMuPDF
        
        # Docker
        'docker',
        
        # Git
        'git',
        'gitdb',
        
        # Utils
        'dotenv',
        'multipart',
        
        # Agent modules
        'agent.pydantic_agent',
        'agent.streaming',
        'agent.compression',
        'agent.hitl',
        'agent.steering',
        'agent.planning',
        'agent.vibe_state',
        'agent.providers',
        'agent.providers.openrouter',
        'agent.providers.dashscope',
        'agent.subagents',
        'agent.subagents.base',
        'agent.subagents.research',
        'agent.subagents.compiler',
        'agent.subagents.planner',
        'agent.tools',
        'agent.tools.pdf_reader',
        
        # Services
        'services.docker',
        'services.project',
        'services.memory',
        'services.semantic_scholar',
        'services.tectonic_latex',
        'services.local_latex',
        'services.unified_latex',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_rth_disable_logfire.py'],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        # Exclude logfire - causes source inspection issues with PyInstaller
        'logfire',
        'logfire.integrations',
        'logfire.integrations.pydantic',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='youresearch-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console for logging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
