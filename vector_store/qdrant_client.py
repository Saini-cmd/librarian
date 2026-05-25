from pathlib import Path
from qdrant_client import QdrantClient

class QdrantManager:
    _clients: dict[str, QdrantClient] = {}

    def __init__(self, path: str | None = None):
        db_path = Path(path) if path else Path(__file__).resolve().parent.parent / "qdrant_db"
        key = str(db_path.resolve())

        if key not in self._clients:
            self._clients[key] = QdrantClient(path=key)

        self.client = self._clients[key]

    def get_client(self):
        return self.client