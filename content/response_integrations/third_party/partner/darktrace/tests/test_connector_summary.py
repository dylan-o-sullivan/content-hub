from __future__ import annotations

import pathlib
import sys
from unittest.mock import MagicMock, patch

# Import the integration as a package, as the connector uses relative imports.
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

from darktrace.connectors import DarktraceModelBreachesConnector as connector  # noqa: E402

PARAMS = {
    "API Root": "https://dt.example",
    "API Token": "token",
    "API Private Token": "private",
    "Verify SSL": "true",
    "PythonProcessTimeout": "180",
    "Max Model Breaches To Fetch": "10",
    "Use whitelist as a blacklist": "true",
    "DeviceProductField": "Product Name",
}


def _alert(pbid: int) -> MagicMock:
    alert = MagicMock()
    alert.id = pbid
    alert.name = f"Model {pbid}"
    alert.time = 1000 + pbid
    return alert


def _run(whitelist_passes, overflowed, extra_params=None, save_timestamp=None):
    siemplify = MagicMock()
    siemplify.parameters = {**PARAMS, **(extra_params or {})}
    alerts = [_alert(1), _alert(2)]
    manager = MagicMock()
    manager.get_alerts.return_value = alerts

    with (
        patch.object(connector, "SiemplifyConnectorExecution", return_value=siemplify),
        patch.object(connector, "DarktraceManager", return_value=manager),
        patch.object(connector, "read_ids", return_value=[]),
        patch.object(connector, "write_ids") as write_ids,
        patch.object(connector, "save_timestamp", save_timestamp or MagicMock()),
        patch.object(connector, "calculate_last_success_time", return_value=1),
        patch.object(connector, "GetEnvironmentCommonFactory"),
        patch.object(connector, "pass_whitelist_filter", side_effect=whitelist_passes),
        patch.object(connector, "is_overflowed", side_effect=overflowed),
    ):
        connector.main(False)

    return siemplify, manager, write_ids


def test_skipped_alerts_are_logged_and_still_deduplicated() -> None:
    siemplify, _, write_ids = _run(whitelist_passes=[False, True], overflowed=[True])

    logged = " ".join(str(c) for c in siemplify.LOGGER.info.call_args_list)
    assert "Alert 1 - Model 1 skipped: filtered out by the whitelist" in logged
    assert "found as overflow alert" in logged
    assert "fetched 2 new, created 0, skipped 2 (overflow 1, behaviour visibility 0, whitelist 1)" in logged
    # Conservative choice: skipped alerts stay in the persisted ids so they are not retried forever.
    assert write_ids.call_args.args[1] == [1, 2]


def test_include_acknowledged_param_is_forwarded() -> None:
    _, manager, _ = _run([True, True], [False, False], {"Include Acknowledged": "true"})
    assert manager.get_alerts.call_args.kwargs["include_acknowledged"] is True


def test_include_acknowledged_defaults_to_false() -> None:
    _, manager, _ = _run([True, True], [False, False])
    assert manager.get_alerts.call_args.kwargs["include_acknowledged"] is False


def test_use_creation_time_defaults_to_false_and_saves_time_cursor() -> None:
    save = MagicMock()
    _, manager, _ = _run([True, True], [False, False], save_timestamp=save)
    assert manager.get_alerts.call_args.kwargs["use_creation_time"] is False
    assert save.call_args.kwargs["timestamp_key"] == "time"


def test_use_creation_time_enabled_saves_creation_time_cursor() -> None:
    save = MagicMock()
    _, manager, _ = _run([True, True], [False, False], {"Use Creation Time": "true"}, save_timestamp=save)
    assert manager.get_alerts.call_args.kwargs["use_creation_time"] is True
    assert save.call_args.kwargs["timestamp_key"] == "creation_time"
