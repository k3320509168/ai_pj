import os
import sys
import json
from typing import Any, Dict, List

from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaEmbeddings


# =========================
# 基本設定
# =========================

base_dir = os.path.dirname(os.path.abspath(__file__))

# 你的資訊卡檔案名稱
JSON_CARD_PATH = os.path.join("./uploaded_docs_JSON", "informationCard.json")

# FAISS 輸出位置，要跟 LLM_run/chatbotV2.py 的 FAISS_DB_PATH 對應
FAISS_DB_PATH = os.path.join(base_dir, "faiss_db_local_JSON_v2")

OLLAMA_BASE_URL = "http://localhost:11434"
EMBEDDING_MODEL_NAME = "nomic-embed-text"


# =========================
# 讀取 JSON / JSONL
# =========================

def load_information_cards(path: str) -> List[Dict[str, Any]]:
    """
    支援兩種格式：

    1. JSON array:
       [
         {"id": "...", "text": "..."},
         {"id": "...", "text": "..."}
       ]

    2. JSONL:
       {"id": "...", "text": "..."}
       {"id": "...", "text": "..."}
    """
    if not os.path.exists(path):
        print(f"找不到資訊卡檔案：{path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        print("資訊卡檔案是空的。")
        sys.exit(1)

    # 如果是 JSON array
    if content.startswith("["):
        data = json.loads(content)

        if not isinstance(data, list):
            print("JSON 格式錯誤：最外層應該是 list。")
            sys.exit(1)

        return data

    # 如果是 JSONL
    cards = []
    for line_no, line in enumerate(content.splitlines(), start=1):
        line = line.strip()

        if not line:
            continue

        try:
            item = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"第 {line_no} 行不是合法 JSON：{e}")
            sys.exit(1)

        if not isinstance(item, dict):
            print(f"第 {line_no} 行格式錯誤：每一行都應該是一個 JSON object。")
            sys.exit(1)

        cards.append(item)

    return cards


# =========================
# 轉成 LangChain Document
# =========================

def format_list_field(title: str, values: Any, max_items: int = 3) -> str:
    if not values:
        return ""

    if not isinstance(values, list):
        values = [values]

    text = "；".join(
        str(value).strip() for value in values[:max_items] if str(value).strip()
    )
    return f"{title}：{text}" if text else ""


def build_retrieval_text(card: Dict[str, Any]) -> str:
    """
    Keep retrieval text positive and service-specific.
    Do not embed negative cross-service labels such as not_suitable_for.
    """
    sections = [
        f"服務名稱：{str(card.get('service_name', '未命名服務')).strip()}",
        f"服務類別：{str(card.get('category', '未分類')).strip()}",
        f"服務摘要：{str(card.get('service_summary', '')).strip()}",
        format_list_field("適用對象", card.get("target_users", []), max_items=3),
        format_list_field("申請資格", card.get("eligibility", []), max_items=2),
        format_list_field("服務內容與補助", card.get("benefits", []), max_items=2),
        format_list_field("申請文件", card.get("required_documents", []), max_items=2),
        format_list_field("申請與洽辦方式", card.get("application_method", []), max_items=2),
    ]

    return "\n".join(section for section in sections if section.strip())


def cards_to_documents(cards: List[Dict[str, Any]]) -> List[Document]:
    """
    一張資訊卡 = 一個 Document = 一個 chunk。

    注意：
    - page_content 放真正要 embedding 的 retrieval text
    - metadata 放 service_name、category、answer_guidance 等輔助資訊
    """
    documents = []

    for idx, card in enumerate(cards, start=1):
        card_id = str(card.get("id", f"card_{idx:03d}")).strip()
        service_name = str(card.get("service_name", "未命名服務")).strip()
        category = str(card.get("category", "未分類")).strip()

        answer_content = str(card.get("text", "")).strip()
        retrieval_text = build_retrieval_text(card)

        if not answer_content or not retrieval_text:
            print(f"略過第 {idx} 筆，因為回答內容或檢索文字是空的。id={card_id}")
            continue

        metadata = {
            "id": card_id,
            "source": JSON_CARD_PATH,
            "service_name": service_name,
            "category": category,
            "target_users": card.get("target_users", []),
            "answer_guidance": card.get("answer_guidance", ""),
            "source_summary": card.get("source_summary", ""),
            "not_suitable_for": card.get("not_suitable_for", []),
            "answer_content": answer_content,
        }

        doc = Document(
            page_content=retrieval_text,
            metadata=metadata,
        )

        documents.append(doc)

    return documents


# =========================
# 主程式
# =========================

def main() -> None:
    print("正在讀取資訊卡...")
    cards = load_information_cards(JSON_CARD_PATH)
    print(f"讀取資訊卡數量：{len(cards)}")

    documents = cards_to_documents(cards)
    print(f"建立 Document 數量：{len(documents)}")

    if not documents:
        print("沒有可用的 Document，請確認 informationCard.json 裡每筆都有 text 欄位。")
        sys.exit(1)

    print("\n資訊卡列表：")
    for doc in documents:
        print(
            f"- {doc.metadata.get('id')} | "
            f"{doc.metadata.get('service_name')} | "
            f"{doc.metadata.get('category')} | "
            f"retrieval text 長度：{len(doc.page_content)}"
        )

    print("\n正在建立 embedding model...")
    embedding_model = OllamaEmbeddings(
        model=EMBEDDING_MODEL_NAME,
        base_url=OLLAMA_BASE_URL,
    )

    print("\n正在建立 FAISS 向量資料庫...")
    vectorstore = FAISS.from_documents(
        documents=documents,
        embedding=embedding_model,
    )

    print(f"\n正在儲存 FAISS DB 到：{FAISS_DB_PATH}")
    vectorstore.save_local(FAISS_DB_PATH)

    print("\n完成：FAISS vector database 已建立。")
    print("現在可以執行 LLM_run/chatbotV2.py 進行 RAG 查詢。")


if __name__ == "__main__":
    main()
