"""tests/ scope conftest — reset the Motor client between tests.

``engines/db.py`` caches ``_client``/``_db`` at module level for
production efficiency. Under pytest-asyncio's default per-test event
loop, the cached client gets bound to a loop that closes between
tests — every subsequent ``get_db()`` raises
``RuntimeError: Event loop is closed``.

Resetting the cached singletons before each test gives every test a
fresh Motor client bound to the live loop. Cost: ~one extra TCP
connection per test (test suite is small).
"""
from __future__ import annotations

import pytest

from engines import db as _db_module


@pytest.fixture(autouse=True)
def _reset_motor_client_between_tests():
    _db_module._client = None
    _db_module._db = None
    yield
    _db_module._client = None
    _db_module._db = None
