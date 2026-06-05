import os
import runpy
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
CHATBOT_DIR = PROJECT_ROOT / "LLM_run"
CHATBOT_ENTRY = CHATBOT_DIR / "chatbotV2.py"
FAISS_INDEX = PROJECT_ROOT / "RAG_Embedding" / "faiss_db_local_JSON_v2" / "index.faiss"
FAISS_METADATA = PROJECT_ROOT / "RAG_Embedding" / "faiss_db_local_JSON_v2" / "index.pkl"


def require_path(path: Path, label: str) -> None:
    if path.exists():
        return

    raise SystemExit(f"找不到 {label}：{path}")


def main() -> None:
    require_path(CHATBOT_ENTRY, "chatbot 主程式")
    require_path(FAISS_INDEX, "FAISS index")
    require_path(FAISS_METADATA, "FAISS metadata")

    os.chdir(CHATBOT_DIR)
    sys.path.insert(0, str(CHATBOT_DIR))

    runpy.run_path(str(CHATBOT_ENTRY), run_name="__main__")


if __name__ == "__main__":
    main()

