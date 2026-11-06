from __future__ import annotations

import pathlib
import sys

import soar_sdk

# The core modules use flat imports (``from constants import ...``) and the old
# TIPCommon expects the SDK modules at top level (``from SiemplifyAction import ...``),
# so expose both directories the same way the SOAR runtime does.
_EXTRA_PATHS: tuple[str, ...] = (
    str(pathlib.Path(__file__).parent.parent / "core"),
    str(pathlib.Path(soar_sdk.__file__).parent),
)
for _path in _EXTRA_PATHS:
    if _path not in sys.path:
        sys.path.insert(0, _path)
