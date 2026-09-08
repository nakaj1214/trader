from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
import requests

from src.data.jquants_v2_client import JQuantsV2Client


def test_headers_require_api_key() -> None:
    client = JQuantsV2Client(api_key=None)
    client.api_key = None
    with pytest.raises(RuntimeError):
        client._headers()


def test_headers_use_x_api_key() -> None:
    client = JQuantsV2Client(api_key="secret")
    assert client._headers() == {"x-api-key": "secret"}


def test_listed_issues_uses_master_endpoint() -> None:
    client = JQuantsV2Client(api_key="secret", min_interval=0)
    with patch.object(client, "_get", return_value=[{"Code": "72030"}]) as get:
        rows = client.listed_issues("2026-09-07")
    assert rows == [{"Code": "72030"}]
    get.assert_called_once_with("/equities/master", {"date": "2026-09-07"})


def test_financial_summary_uses_summary_endpoint() -> None:
    client = JQuantsV2Client(api_key="secret", min_interval=0)
    with patch.object(client, "_get", return_value=[]) as get:
        client.financial_summary("72030")
    get.assert_called_once_with("/fins/summary", {"code": "72030"})


def _response(status: int, payload: object, headers: dict[str, str] | None = None) -> Mock:
    response = Mock(spec=requests.Response)
    response.status_code = status
    response.headers = headers or {}
    response.json.return_value = payload
    if status >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(str(status))
    else:
        response.raise_for_status.return_value = None
    return response


def test_get_collects_paginated_data() -> None:
    first = _response(200, {"data": [{"Code": "11110"}], "pagination_key": "next-page"})
    second = _response(200, {"data": [{"Code": "22220"}]})

    client = JQuantsV2Client(api_key="secret", min_interval=0)
    with patch("src.data.jquants_v2_client.requests.get", side_effect=[first, second]) as get:
        rows = client._get("/equities/master")

    assert rows == [{"Code": "11110"}, {"Code": "22220"}]
    assert get.call_count == 2
    assert get.call_args_list[0].kwargs["headers"] == {"x-api-key": "secret"}
    assert get.call_args_list[1].kwargs["params"]["pagination_key"] == "next-page"


def test_each_paginated_request_checks_rate_limit_slot() -> None:
    first = _response(200, {"data": [], "pagination_key": "next-page"})
    second = _response(200, {"data": []})
    client = JQuantsV2Client(api_key="secret", min_interval=0)

    with (
        patch.object(client, "_wait_for_slot") as wait,
        patch("src.data.jquants_v2_client.requests.get", side_effect=[first, second]),
    ):
        client._get("/equities/master")

    assert wait.call_count == 2


def test_retryable_status_uses_retry_after_then_succeeds() -> None:
    limited = _response(429, {}, {"Retry-After": "1.5"})
    success = _response(200, {"data": [{"Code": "11110"}]})
    client = JQuantsV2Client(api_key="secret", min_interval=0, max_retries=2)

    with (
        patch("src.data.jquants_v2_client.requests.get", side_effect=[limited, success]) as get,
        patch("src.data.jquants_v2_client.time.sleep") as sleep,
    ):
        rows = client._get("/equities/master")

    assert rows == [{"Code": "11110"}]
    assert get.call_count == 2
    sleep.assert_called_once_with(1.5)


def test_retryable_status_raises_after_retry_budget() -> None:
    failure = _response(503, {})
    client = JQuantsV2Client(
        api_key="secret",
        min_interval=0,
        max_retries=1,
        retry_backoff=0,
    )

    with (
        patch("src.data.jquants_v2_client.requests.get", side_effect=[failure, failure]),
        patch("src.data.jquants_v2_client.time.sleep"),
        pytest.raises(requests.HTTPError),
    ):
        client._get("/equities/master")


def test_connection_error_is_retried() -> None:
    success = _response(200, {"data": [{"Code": "11110"}]})
    client = JQuantsV2Client(api_key="secret", min_interval=0, retry_backoff=0)

    with (
        patch(
            "src.data.jquants_v2_client.requests.get",
            side_effect=[requests.ConnectionError("offline"), success],
        ),
        patch("src.data.jquants_v2_client.time.sleep") as sleep,
    ):
        assert client._get("/equities/master") == [{"Code": "11110"}]

    sleep.assert_called_once_with(0)


@pytest.mark.parametrize("payload", [[], {"data": {}}, {"data": ["not-an-object"]}])
def test_get_rejects_malformed_success_payload(payload: object) -> None:
    client = JQuantsV2Client(api_key="secret", min_interval=0)
    with (
        patch("src.data.jquants_v2_client.requests.get", return_value=_response(200, payload)),
        pytest.raises(RuntimeError, match="Invalid J-Quants response"),
    ):
        client._get("/equities/master")


def test_get_rejects_repeated_pagination_cursor() -> None:
    page = _response(200, {"data": [], "pagination_key": "same"})
    client = JQuantsV2Client(api_key="secret", min_interval=0)
    with (
        patch("src.data.jquants_v2_client.requests.get", side_effect=[page, page]),
        pytest.raises(RuntimeError, match="repeated pagination cursor"),
    ):
        client._get("/equities/master")
