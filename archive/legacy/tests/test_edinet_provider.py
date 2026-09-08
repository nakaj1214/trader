from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from src.data.providers.edinet_provider import EdinetDocument, EdinetProvider


def test_edinet_document_maps_submission_time_and_security_code() -> None:
    doc = EdinetDocument.from_api({
        "docID": "S100TEST",
        "edinetCode": "E00000",
        "secCode": "72030",
        "filerName": "Example",
        "submitDateTime": "2026-05-14 15:30",
        "periodEnd": "2026-03-31",
    })
    assert doc.doc_id == "S100TEST"
    assert doc.sec_code == "72030"
    assert doc.period_end == "2026-03-31"
    assert doc.submit_datetime == "2026-05-14 15:30"


def test_list_documents_requires_api_key() -> None:
    provider = EdinetProvider(api_key=None)
    provider.api_key = None
    with pytest.raises(RuntimeError):
        provider.list_documents("2026-05-14")


@patch("src.data.providers.edinet_provider.requests.get")
def test_list_documents_uses_v2_api(mock_get: Mock) -> None:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "results": [
            {
                "docID": "S100TEST",
                "secCode": "72030",
                "submitDateTime": "2026-05-14 15:30",
            }
        ]
    }
    mock_get.return_value = response
    provider = EdinetProvider(api_key="secret")
    docs = provider.list_documents("2026-05-14")
    assert len(docs) == 1
    assert docs[0].sec_code == "72030"
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["date"] == "2026-05-14"
    assert kwargs["params"]["type"] == 2
    assert kwargs["params"]["Subscription-Key"] == "secret"
