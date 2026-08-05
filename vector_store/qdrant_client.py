import os
from pathlib import Path

from qdrant_client import QdrantClient


class QdrantManager:
    _clients: dict[str, QdrantClient] = {}

    def __init__(self, url: str | None = None, api_key: str | None = None):
        url = url or os.getenv("QDRANT_URL")
        api_key = api_key or os.getenv("QDRANT_API_KEY")

        if url and api_key:
            key = f"cloud:{url}"
            if key not in self._clients:
                self._clients[key] = QdrantClient(url=url, api_key=api_key)
        else:
            db_path = Path(__file__).resolve().parent.parent / "qdrant_db"
            key = str(db_path.resolve())
            if key not in self._clients:
                self._clients[key] = QdrantClient(path=key)

        self.client = self._clients[key]

    def get_client(self):
        return self.client