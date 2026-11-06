from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from DarktraceManager import DarktraceManager

COUNT = 100


def _breach(pbid: int, time: int, priority: int = 3, creation_time: int | None = None) -> dict:
    breach = {
        "pbid": pbid,
        "time": time,
        "score": 0.5,
        "model": {
            "now": {"name": f"Model {pbid}", "description": "d", "priority": priority},
        },
    }
    if creation_time is not None:
        breach["creationTime"] = creation_time
    return breach


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


def _pages(manager, *pages: list[dict]) -> MagicMock:
    manager.session.get = MagicMock(side_effect=[_response(page) for page in pages])
    return manager.session.get


def _full_page(first_pbid: int, first_time: int) -> list[dict]:
    return [_breach(first_pbid + i, first_time + i) for i in range(COUNT)]


def test_single_short_page_makes_one_request(manager, siemplify) -> None:
    get = _pages(manager, [_breach(1, 1000), _breach(2, 1001)])

    alerts = _fetch(manager, siemplify)

    assert [alert.id for alert in alerts] == [1, 2]
    assert get.call_count == 1
    siemplify.LOGGER.warn.assert_not_called()


def test_full_page_with_enough_new_breaches_stops_and_warns(manager, siemplify) -> None:
    get = _pages(manager, _full_page(1, 1000))

    alerts = _fetch(manager, siemplify, limit=10)

    assert len(alerts) == COUNT
    assert get.call_count == 1
    siemplify.LOGGER.warn.assert_called_once()


def test_pages_past_already_processed_breaches(manager, siemplify) -> None:
    # The first full page only holds breaches that were ingested before; the old code
    # stopped here and never saw the new ones on the next page.
    first = _full_page(1, 1000)
    second = [first[-1], _breach(500, 2000), _breach(501, 2001)]
    get = _pages(manager, first, second)

    alerts = _fetch(manager, siemplify, existing_ids=[b["pbid"] for b in first])

    assert [alert.id for alert in alerts] == [500, 501]
    assert get.call_count == 2
    assert get.call_args_list[1].kwargs["params"]["starttime"] == first[-1]["time"]


def test_stops_after_last_short_page(manager, siemplify) -> None:
    first = _full_page(1, 1000)
    get = _pages(manager, first, [first[-1]])

    alerts = _fetch(manager, siemplify, existing_ids=[b["pbid"] for b in first])

    assert alerts == []
    assert get.call_count == 2


def test_stops_when_page_does_not_advance(manager, siemplify) -> None:
    first = _full_page(1, 1000)
    get = _pages(manager, first, first)

    alerts = _fetch(manager, siemplify, existing_ids=[b["pbid"] for b in first])

    assert alerts == []
    assert get.call_count == 2
    assert any("did not advance" in str(c) for c in siemplify.LOGGER.warn.call_args_list)


def test_page_count_is_bounded(manager, siemplify, monkeypatch) -> None:
    monkeypatch.setattr("DarktraceManager.MAX_MODEL_BREACH_PAGES", 3)
    pages = [_full_page(1 + i * COUNT, 1000 + i * COUNT) for i in range(5)]
    ids = [b["pbid"] for page in pages for b in page]
    get = _pages(manager, *pages)

    _fetch(manager, siemplify, existing_ids=ids)

    assert get.call_count == 3
    assert any("maximum of 3" in str(c) for c in siemplify.LOGGER.warn.call_args_list)


def test_priority_filter_does_not_stop_paging(manager, siemplify) -> None:
    low = [_breach(1 + i, 1000 + i, priority=1) for i in range(COUNT)]
    get = _pages(manager, low, [_breach(900, 5000)])

    alerts = _fetch(manager, siemplify, min_priority=3)

    assert [alert.id for alert in alerts] == [900]
    assert get.call_count == 2


def test_default_request_params_are_unchanged(manager, siemplify) -> None:
    manager.session.get = MagicMock(return_value=_response([_breach(1, 1000, creation_time=9)]))

    _fetch(manager, siemplify)

    assert manager.session.get.call_args.kwargs["params"] == {
        "starttime": 1000,
        "minimal": "false",
        "minscore": 0.0,
        "historicmodelonly": "false",
        "order": "ASC",
        "count": COUNT,
    }


def test_creation_time_not_sent_when_disabled(manager, siemplify) -> None:
    manager.session.get = MagicMock(return_value=_response([_breach(1, 1000)]))

    _fetch(manager, siemplify, use_creation_time=False)

    assert "creationtime" not in manager.session.get.call_args.kwargs["params"]


def test_creation_time_sent_when_enabled(manager, siemplify) -> None:
    manager.session.get = MagicMock(return_value=_response([_breach(1, 1000, creation_time=5000)]))

    alerts = _fetch(manager, siemplify, use_creation_time=True)

    assert manager.session.get.call_args.kwargs["params"]["creationtime"] == "true"
    # The displayed alert time stays the activity time.
    assert (alerts[0].time, alerts[0].creation_time) == (1000, 5000)


def test_creation_time_missing_falls_back_to_time_and_warns_once(manager, siemplify) -> None:
    manager.session.get = MagicMock(
        return_value=_response([_breach(1, 1000), _breach(2, 1001, creation_time=5000), _breach(3, 1002)])
    )

    alerts = _fetch(manager, siemplify, use_creation_time=True)

    assert [alert.creation_time for alert in alerts] == [1000, 5000, 1002]
    warnings = [c for c in siemplify.LOGGER.warn.call_args_list if "no creationTime" in str(c)]
    assert len(warnings) == 1


def test_creation_time_paging_advances_by_max_creation_time(manager, siemplify) -> None:
    # Activity times are far behind the creation times and not sorted like them.
    first = [_breach(1 + i, 10 + i, creation_time=5000 + (COUNT - i)) for i in range(COUNT)]
    second = [first[0], _breach(500, 20, creation_time=7000)]
    get = _pages(manager, first, second)

    alerts = _fetch(manager, siemplify, existing_ids=[b["pbid"] for b in first], use_creation_time=True)

    assert [alert.id for alert in alerts] == [500]
    assert get.call_count == 2
    assert get.call_args_list[1].kwargs["params"]["starttime"] == 5000 + COUNT
    assert get.call_args_list[1].kwargs["params"]["creationtime"] == "true"


def test_creation_time_paging_terminates_when_page_does_not_advance(manager, siemplify) -> None:
    first = [_breach(1 + i, 10 + i, creation_time=5000) for i in range(COUNT)]
    get = _pages(manager, first, first)

    alerts = _fetch(manager, siemplify, existing_ids=[b["pbid"] for b in first], use_creation_time=True)

    assert alerts == []
    assert get.call_count == 2


def test_creation_time_tie_at_page_boundary_does_not_skip_rows(manager, siemplify) -> None:
    # The last row of page 1 shares its millisecond with a row that only page 2 returns.
    first = [_breach(1 + i, 10, creation_time=5000 + i) for i in range(COUNT)]
    tied = _breach(900, 10, creation_time=5000 + COUNT - 1)
    get = _pages(manager, first, [first[-1], tied])

    alerts = _fetch(manager, siemplify, existing_ids=[b["pbid"] for b in first], use_creation_time=True)

    assert [alert.id for alert in alerts] == [900]
    assert get.call_args_list[1].kwargs["params"]["starttime"] == first[-1]["creationTime"]
    assert get.call_count == 2
