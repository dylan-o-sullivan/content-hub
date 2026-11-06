from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from DarktraceManager import DarktraceManager

COUNT = 100


def _breach(pbid: int, time: int) -> dict:
    return {
        "pbid": pbid,
        "time": time,
        "score": 0.5,
        "priority": 3,
        "model": {"then": {"name": f"Model {pbid}", "description": "d"}},
    }


def _response(rows: list[dict]) -> MagicMock:
    response = MagicMock()
    response.content = b"[]" if not rows else b"[{}]"
    response.json.return_value = rows
    return response


@pytest.fixture
def siemplify() -> MagicMock:
    return MagicMock()


@pytest.fixture
def manager() -> DarktraceManager:
    return DarktraceManager("https://dt.example", "token", "private", True)


def _fetch(manager, siemplify, existing_ids=None, limit=10, **kwargs):
    return manager.get_alerts(
        existing_ids=existing_ids if existing_ids is not None else [],
        limit=limit,
        start_timestamp=1000,
        score=0,
        siemplify=siemplify,
        **kwargs,
    )


def test_include_acknowledged_not_sent_by_default(manager, siemplify) -> None:
    manager.session.get = MagicMock(return_value=_response([_breach(1, 1000)]))

    _fetch(manager, siemplify)

    assert "includeacknowledged" not in manager.session.get.call_args.kwargs["params"]


def test_include_acknowledged_sent_when_enabled(manager, siemplify) -> None:
    manager.session.get = MagicMock(return_value=_response([_breach(1, 1000)]))

    _fetch(manager, siemplify, include_acknowledged=True)

    assert manager.session.get.call_args.kwargs["params"]["includeacknowledged"] == "true"
