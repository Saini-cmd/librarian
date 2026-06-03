from __future__ import annotations

import json
from unittest.mock import patch

from bootstrap import ensure_repo_root

ensure_repo_root()

from rag.external.llm.deepseek_client import DeepSeekClient, DeepSeekConfig


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
                "model": "deepseek-test-model",
                "choices": [
                    {
                        "message": {
                            "content": "test-ok"
                        }
                    }
                ],
            }

    def fake_post(url: str, headers=None, json=None, timeout=None, stream=False):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        captured["stream"] = stream
        return MockResponse()

    config = DeepSeekConfig(api_key="test-key", retries=1)
    client = DeepSeekClient(config=config, api_key="test-key", model="deepseek-test-model", base_url="https://example.com")

    with patch("rag.external.llm.deepseek_client.requests.post", side_effect=fake_post):
        response = client.generate([
            {"role": "system", "content": "Return a short confirmation."},
            {"role": "user", "content": "confirm the api call"},
        ])

    assert captured["url"] == "https://example.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert isinstance(captured["json"], dict)
    assert captured["json"]["model"] == "deepseek-test-model"
    assert response.text == "test-ok"
    assert response.model == "deepseek-test-model"
    print(json.dumps({"status": "ok", "response": response.text}))


if __name__ == "__main__":
    main()