from __future__ import annotations

import json
from unittest.mock import patch

from bootstrap import ensure_repo_root

ensure_repo_root()

from rag.external.llm.gemini_client import GeminiClient, GeminiConfig


def main() -> None:
    captured: dict[str, object] = {}

    class MockResponse:
        status_code = 200
        text = "{}"

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict[str, object]:
            return {
                "modelVersion": "gemini-test-model",
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "test-ok"},
                            ]
                        }
                    }
                ],
            }

    def fake_post(url: str, headers=None, params=None, json=None, timeout=None, stream=False):
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        captured["json"] = json
        captured["timeout"] = timeout
        captured["stream"] = stream
        return MockResponse()

    config = GeminiConfig(api_key="test-key", store=False, retries=1)
    client = GeminiClient(config=config, api_key="test-key", model="gemini-test-model", base_url="https://example.com/v1beta")

    with patch("rag.external.llm.gemini_client.requests.post", side_effect=fake_post):
        response = client.generate([
            {"role": "system", "content": "Return a short confirmation."},
            {"role": "user", "content": "confirm the api call"},
        ])

    assert captured["url"] == "https://example.com/v1beta/models/gemini-test-model:generateContent"
    assert captured["params"] == {"key": "test-key"}
    assert isinstance(captured["json"], dict)
    assert captured["json"]["store"] is False
    assert response.text == "test-ok"
    assert response.model == "gemini-test-model"
    print(json.dumps({"status": "ok", "store": captured["json"]["store"], "response": response.text}))


if __name__ == "__main__":
    main()