"""Make the NVDA-independent add-on package importable without NVDA."""

from __future__ import annotations

import sys
from pathlib import Path


PACKAGE_PARENT = (
	Path(__file__).resolve().parents[1] / "addon" / "globalPlugins" / "eloquenceDictionaryManager"
)
TOOLS_DIRECTORY = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(PACKAGE_PARENT))
sys.path.insert(0, str(TOOLS_DIRECTORY))
