from pathlib import Path
import shutil


DB_PATH = Path(__file__).resolve().parent / "qdrant_db"


def main():
    print(f"Target DB path: {DB_PATH}")

    if DB_PATH.exists():
        shutil.rmtree(DB_PATH)
        print("Deleted existing Qdrant DB directory")
    else:
        print("Qdrant DB directory does not exist, nothing to delete")

    DB_PATH.mkdir(parents=True, exist_ok=True)
    print("Recreated empty Qdrant DB directory")
    print("DB wipe complete")


if __name__ == "__main__":
    main()
