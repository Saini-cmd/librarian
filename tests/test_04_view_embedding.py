from bootstrap import ensure_repo_root

ensure_repo_root()

from vector_store.qdrant_client import QdrantManager

client = QdrantManager().get_client()

points, _ = client.scroll(
    collection_name="code_chunks",
    limit=5,
    with_vectors=True,
    with_payload=True
)

for p in points:
    print("=" * 80)
    print(f"ID: {p.id}")
    print(f"File: {p.payload.get('file_path')}")
    print(f"Lines: {p.payload.get('start_line')} - {p.payload.get('end_line')}")
    print(f"Language: {p.payload.get('language')}")
    
    print("\nContent Preview:")
    print(p.payload.get("content")[:300])   # first 300 chars
    
    print("\nVector (first 8 dims):")
    print([round(v, 4) for v in p.vector[:8]])
    
    print("=" * 80)
    print()
    print()
