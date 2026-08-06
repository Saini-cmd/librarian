import os
from pathlib import Path

from qdrant_client import QdrantClient


class QdrantManager:
    _clients: dict[str, QdrantClient] = {}

    def __init__(self, url: str | None = None, api_key: str | None = None):
        mode = os.getenv("QDRANT_MODE", "server").strip().lower()

        if mode == "cloud":
            url = url or os.getenv("QDRANT_URL")
            api_key = api_key or os.getenv("QDRANT_API_KEY")
            key = f"cloud:{url}"
            if key not in self._clients:
                self._clients[key] = QdrantClient(url=url, api_key=api_key)
        elif mode == "embedded":
            db_path = Path(__file__).resolve().parent.parent / "qdrant_db"
            key = str(db_path.resolve())
            if key not in self._clients:
                self._clients[key] = QdrantClient(path=key)
        else:
            url = url or os.getenv("QDRANT_LOCAL_URL", "http://localhost:6333")
            key = f"server:{url}"
            if key not in self._clients:
                self._clients[key] = QdrantClient(url=url)

        self.client = self._clients[key]

    def get_client(self):
        return self.client
