"""Regression guard: YT Music Data API sends the real bearer token.

NOTE: A prior session reported the Authorization header was hardcoded to the
literal ``******`` placeholder. That was a false alarm caused by secret
REDACTION in tool output — the real source is ``f"Bearer {self._access_token}"``
and the runtime header is correct. This test locks that correct behaviour in
place so a genuine regression (e.g. dropping the token) would be caught.
"""
from tuneshift.platforms.ytmusic import YTMusicClient


def test_auth_headers_send_real_bearer_token(monkeypatch, tmp_path):
    client = YTMusicClient(token_path=tmp_path / "ytmusic.json")
    client._access_token = "ya29.real-access-token"
    monkeypatch.setattr(client, "_maybe_refresh_token", lambda: None)

    headers = client._auth_headers()

    assert headers["Authorization"] == "Bearer ya29.real-access-token"
    assert "******" not in headers["Authorization"]
