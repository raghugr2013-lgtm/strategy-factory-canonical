"""
Compatibility package.

Allows old imports like:

    from engines.xxx import ...

to resolve to:

    legacy.engines.xxx
"""

from pathlib import Path

__path__ = [
    str(Path(__file__).resolve().parent.parent / "legacy" / "engines")
]
