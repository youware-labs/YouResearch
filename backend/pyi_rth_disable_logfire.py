"""
Runtime hook to disable pydantic-logfire integration.
This prevents source code inspection errors in PyInstaller builds.
"""
import os
os.environ['LOGFIRE_SEND_TO_LOGFIRE'] = 'false'
os.environ['PYDANTIC_DISABLE_PLUGINS'] = '1'
