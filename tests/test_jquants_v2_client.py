from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

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


def test_get_collects_paginated_data() -> None:
    first = Mock()
    first.raise_for_status.return_value = None
    first.json.return_value = {
        "data": [{"Code": "11110"}],
        "pagination_key": "next-page",
    }
    second = Mock()
    second.raise_for_status.return_value = None
    second.json.return_value = {"data": [{"Code": "22220"}]}

    client = JQuantsV2Client(api_key="secret", min_interval=0)
    with patch("src.data.jquants_v2_client.requests.get", side_effect=[first, second]) as get:
        rows = client._get("/equities/master")

    assert rows == [{"Code": "11110"}, {"Code": "22220"}]
    assert get.call_count == 2
    assert get.call_args_list[0].kwargs["headers"] == {"x-api-key": "secret"}
    assert get.call_args_list[1].kwargs["params"]["pagination_key"] == "next-page"
