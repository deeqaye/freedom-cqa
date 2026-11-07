import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import ingest

REC = {"conversation_id": "t-001", "channel": "agent chat", "language": "EN", "audio_url": None,
       "transcript": [{"timestamp": "00:01", "speaker": "client", "text": "hi"},
                      {"timestamp": "00:05", "speaker": "operator", "text": "Hello, my name is Ann"}]}


@pytest.mark.parametrize("url", [
    "http://ec88.a5.environment.api.powerplatform.com/x",        # not https
    "https://evil.example.com/x",                                 # foreign host
    "https://environment.api.powerplatform.com.evil.com/x",       # suffix trick
    "https://169.254.169.254/latest/meta-data",                   # metadata IP
])
def test_url_rejected(url):
    with pytest.raises(ingest.IngestError):
        ingest.check_url(url)


def test_url_allowed():
    ingest.check_url("https://ec88f21f1accecf38e20095a9fe175.a5.environment.api.powerplatform.com/powerautomate/x?group_id=DEV")


def test_safe_group_blocks_traversal():
    assert "/" not in ingest.safe_group("../../etc/passwd")
    with pytest.raises(ingest.IngestError):
        ingest.safe_group("..")


def test_group_from_link_when_response_has_none():
    assert ingest.group_of({"records": [REC]}, "https://h/x?a=1&group_id=PROD-7") == "PROD-7"


def test_upload_variants_and_errors():
    with TestClient(app) as c:
        for body, group in [({"isSuccess": True, "data": {"dataset_group_id": "T1", "records": [REC]}}, "T1"),
                            ([REC], "UPLOAD")]:
            r = c.post("/api/conversations/upload", files={"file": ("d.json", json.dumps(body).encode())})
            assert r.status_code == 200, r.text
            assert r.json()["group_id"] == group and r.json()["count"] == 1
        bad = c.post("/api/conversations/upload", files={"file": ("d.json", b'{"data":{"records":[{"x":1}]}}')})
        assert bad.status_code == 400 and "conversation_id" in bad.json()["detail"]
        assert c.post("/api/conversations/upload", files={"file": ("d.json", b"not json")}).status_code == 400
        assert c.post("/api/ingest/url", json={"url": "https://evil.example.com/x"}).status_code == 400
