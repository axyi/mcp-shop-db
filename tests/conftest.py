import json

import pytest


@pytest.fixture
def call():
    """Invoke a tool function and decode its JSON envelope."""

    def _call(fn, *args, **kwargs) -> dict:
        return json.loads(fn(*args, **kwargs))

    return _call
