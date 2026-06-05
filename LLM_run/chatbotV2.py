import time
from typing import List, Dict

from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaEmbeddings, ChatOllama


# =========================
# 基本設定
# =========================

OLLAMA_BASE_URL = "http://localhost:11434"

EMBEDDING_MODEL_NAME = "nomic-embed-text"
LLM_MODEL_NAME = "gemma3:4b"

FAISS_DB_PATH = "../RAG_Embedding/faiss_db_local_JSON_v2"

NUM_PREDICT = 320
NUM_CTX = 4096

RETRIEVER_K = 2
MAX_RETRIEVED_CHARS = 7000
MAX_HISTORY_TURNS = 6

RESOURCE_KEYWORDS = (
    "福利", "補助", "津貼", "年金", "資格", "申請", "申辦", "文件",
    "電話", "聯絡", "費用", "金額", "資源", "長照", "照顧服務",
    "老人服務", "送餐", "獨居老人服務", "關懷訪視", "敬老卡",
    "區公所", "社會局",
    "可以領", "能領", "怎麼辦", "哪裡辦", "去哪辦", "找誰",
    "酷暑", "熱浪", "避暑", "避熱", "避熱場所", "避暑場所",
    "好熱", "很熱", "太熱", "悶熱", "天氣熱", "熱到受不了",
    "快熱暈", "熱暈", "沒冷氣", "哪裡涼",
)

RESOURCE_FOLLOW_UP_KEYWORDS = (
    "那", "這個", "剛剛", "前面", "它", "要去哪", "怎麼申請",
    "怎麼辦", "多少錢", "需要什麼", "要帶什麼", "電話", "資格",
)

SERVICE_NAME_ALIASES = {
    "敬老卡申辦": ("敬老卡", "敬老悠遊卡", "老人悠遊卡"),
    "中低收入老人生活津貼": ("中低收入老人生活津貼", "老人生活津貼"),
    "中低收入老人特別照顧津貼": (
        "中低收入老人特別照顧津貼",
        "老人特別照顧津貼",
        "特別照顧津貼",
    ),
    "老年年金給付": ("老年年金", "國民年金老年年金", "老年年金給付"),
    "臺北市獨居老人服務": (
        "臺北市獨居老人服務",
        "獨居老人服務",
        "獨居長者服務",
    ),
}


# =========================
# 建立 Embedding Model
# =========================

embedding_model = OllamaEmbeddings(
    model=EMBEDDING_MODEL_NAME,
    base_url=OLLAMA_BASE_URL,
)


# =========================
# 載入 FAISS
# =========================

print("正在載入 FAISS DB...")

t0 = time.perf_counter()

vectorstore = FAISS.load_local(
    FAISS_DB_PATH,
    embeddings=embedding_model,
    allow_dangerous_deserialization=True
)

t1 = time.perf_counter()

print(f"FAISS DB 載入完成，耗時 {t1 - t0:.2f} 秒")


# =========================
# 建立 Retriever
# =========================

retriever = vectorstore.as_retriever(
    search_type="similarity",
    search_kwargs={
        "k": RETRIEVER_K,
    }
)


# =========================
# 建立 LLM
# =========================

llm = ChatOllama(
    model=LLM_MODEL_NAME,
    base_url=OLLAMA_BASE_URL,
    temperature=0.35,
    num_predict=NUM_PREDICT,
    num_ctx=NUM_CTX,
    keep_alive=1800,
)


# =========================
# Prompt
# =========================

system_prompt = """
你是一位溫暖、自然、有耐心的聊天陪伴者。
主要對話對象為銀髮族、獨居長者。你的第一目標是陪對方好好說話：先理解他現在想聊天、想被聽見，還是正在詢問照顧與福利資源。
知識庫裡有老人福利、照顧資源與生活支持服務資料；只有當使用者主動詢問資源、明顯需要協助，或服務能直接回答他的問題時，才簡短提到相關資料。

你的回答方式：
1. 對方打招呼、閒聊、分享心情或生活小事時，先自然回應內容，不要急著給建議或推薦服務。
2. 可以像熟悉的聊天對象一樣回應情緒，例如表示理解、接話、輕輕關心，但不要過度熱情、制式安慰或連續盤問。
3. 請用台灣繁體中文簡短回答，語氣口語、友善、關懷，適合 LINE 閱讀。
4. 可以偶爾關心他今天過得如何、吃飯了沒、身體怎麼樣，讓對話自然；若已關心過或話題不適合，就不要重複問。
5. 使用者只是想聊天時，優先延續話題；使用者問具體問題時，再給具體回答。
6. 如果資料不足，可以用一般常識給出安全、合理、保守的初步建議。
7. 若真的需要更多資訊，最多只問一個最重要的問題。
8. 回答要簡短，通常 1 到 3 小段，350 字內。

重要限制：
1. 請記住對方的名子，如果對方有提到名字，之後回答要用名字稱呼，若沒有提及請直接對話不需稱呼。
2. 資料中的資格、金額、電話、申請方式不可自行編造。
3. 不要保證使用者一定符合資格，實際仍需由承辦單位確認。
4. 若使用者有立即危險，例如胸悶、意識不清、跌倒、失聯、嚴重身體不適，請優先提醒聯絡 119 或 110。
5. 如果使用者所在地和資料服務地區不一致，請提醒實際服務需以當地社會局、區公所或承辦單位為準。
6. 不要把每段對話都導向申請服務、資格說明、電話或承辦單位。
7. 不要用推銷口吻，例如「我推薦您」「您可以考慮申請」「這項服務很適合您」，除非使用者正在問資源或確實需要下一步協助。
8. 每一輪都要先回應使用者剛剛新增的內容，不要只重複上一輪的安慰、關心或建議；除非使用者要求重述。
"""

rag_prompt_template = """
以下是從知識庫檢索到的資料：

{retrieved_chunks}

使用者目前問題：
{question}

本輪已進入知識庫回答模式，請優先根據「檢索資料」專業回答。
回答時先判斷使用者這一輪真正要知道什麼，直接回答問題，不要先寫長篇陪聊或泛泛安慰。
請只使用與問題直接相關的檢索資訊，避免把資料中的其他服務、資格、金額、電話或流程一併展開。
若問題在問地點、電話、資格、申請方式、文件、金額或服務內容，請優先回答該項資訊；必要時再補一個重要限制或下一步。
若檢索資料提供了明確資訊，請給出清楚答案；若資料不足或條件不足，請明確說目前無法確認，再最多問一個關鍵問題。
保留友善語氣，但語氣要清楚、穩重、精簡，像熟悉長者需求的服務人員，不要像推銷員。
"""

chat_prompt_template = """
使用者目前想聊天或分享近況：
{question}

請直接接住使用者這一輪的新內容，像自然聊天一樣回應。
不要主動介紹福利、申請方式或服務資料。
不要重複上一輪已經說過的安慰句、關心句或建議。
"""


# =========================
# 短期聊天記憶
# =========================

conversation_history: List[Dict[str, object]] = []


def build_history_text() -> str:
    if not conversation_history:
        return "目前沒有先前對話紀錄。"

    recent_history = conversation_history[-MAX_HISTORY_TURNS:]

    lines = []
    for i, turn in enumerate(recent_history, start=1):
        lines.append(f"第 {i} 輪")
        lines.append(f"使用者：{turn['user']}")
        lines.append(f"AI：{turn['assistant']}")
        lines.append("")

    return "\n".join(lines).strip()


def build_history_messages() -> List[tuple]:
    messages = []

    for turn in conversation_history[-MAX_HISTORY_TURNS:]:
        messages.append(("user", turn["user"]))
        messages.append(("assistant", turn["assistant"]))

    return messages


def save_to_history(user_input: str, assistant_answer: str, used_rag: bool) -> None:
    conversation_history.append({
        "user": user_input,
        "assistant": assistant_answer,
        "used_rag": used_rag,
    })

    while len(conversation_history) > MAX_HISTORY_TURNS:
        conversation_history.pop(0)


def clear_history() -> None:
    conversation_history.clear()


# =========================
# RAG 工具
# =========================

def has_resource_keyword(text: str) -> bool:
    return any(keyword in text for keyword in RESOURCE_KEYWORDS)


def should_use_rag(user_input: str) -> bool:
    if has_resource_keyword(user_input):
        return True

    if not conversation_history:
        return False

    last_turn = conversation_history[-1]
    last_user_input = str(last_turn["user"])

    # Keep the resource context for one more turn after a keyword hit.
    # This lets replies like "那附近有嗎" or "我在大安" still use RAG
    # even when the user does not repeat the original keyword.
    if has_resource_keyword(last_user_input):
        return True

    is_resource_follow_up = any(
        keyword in user_input for keyword in RESOURCE_FOLLOW_UP_KEYWORDS
    )

    return bool(last_turn.get("used_rag")) and is_resource_follow_up


def build_retrieval_query(user_input: str) -> str:
    """
    用使用者最近的說法 + 當前問題做檢索。
    不放入 AI 舊回答，避免模型自己的句型把檢索和回覆帶回原路。
    """
    recent_user_inputs = [
        turn["user"] for turn in conversation_history[-2:] if turn.get("used_rag")
    ]
    user_context = "\n".join(recent_user_inputs) or "目前沒有相關前文。"
    return f"""
最近相關使用者訊息：
{user_context}

使用者目前問題：
{user_input}
""".strip()


def find_target_service_name(text: str) -> str:
    for service_name, aliases in SERVICE_NAME_ALIASES.items():
        if any(alias in text for alias in aliases):
            return service_name

    return ""


def retrieve_docs(retrieval_query: str):
    target_service_name = find_target_service_name(retrieval_query)

    if target_service_name:
        exact_docs = vectorstore.similarity_search(
            retrieval_query,
            k=1,
            filter={"service_name": target_service_name},
        )

        if exact_docs:
            return exact_docs

    return retriever.invoke(retrieval_query)


def format_retrieved_docs(docs) -> str:
    if not docs:
        return "目前沒有檢索到明確對應的資料。"

    chunks = []

    for i, doc in enumerate(docs, start=1):
        metadata = doc.metadata

        service_name = metadata.get("service_name", "unknown")
        category = metadata.get("category", "unknown")
        answer_guidance = metadata.get("answer_guidance", "")
        source_summary = metadata.get("source_summary", "")

        answer_content = metadata.get("answer_content", doc.page_content)

        chunk = f"""
========== 資料 {i} ==========
[服務名稱]
{service_name}

[服務類別]
{category}

[回答指引]
{answer_guidance}

[資料來源摘要]
{source_summary}

[資料內容]
{answer_content}
""".strip()

        chunks.append(chunk)

    return "\n\n".join(chunks)[:MAX_RETRIEVED_CHARS]


# =========================
# Warm up
# =========================

def warm_up() -> None:
    print("\n正在 warm up LLM...")

    for i in range(2):
        start = time.perf_counter()
        _ = llm.invoke([
            ("user", "請用繁體中文簡短回答：你好")
        ])
        end = time.perf_counter()
        print(f"LLM warm up 第 {i + 1} 次耗時: {end - start:.2f} 秒")

    print("\n正在 warm up embedding model...")

    for i in range(2):
        start = time.perf_counter()
        _ = embedding_model.embed_query("測試")
        end = time.perf_counter()
        print(f"Embedding warm up 第 {i + 1} 次耗時: {end - start:.2f} 秒")


# =========================
# 主聊天函式
# =========================

def chat_with_rag(user_input: str) -> str:
    retrieve_start = time.perf_counter()

    used_rag = should_use_rag(user_input)

    if used_rag:
        retrieval_query = build_retrieval_query(user_input)
        docs = retrieve_docs(retrieval_query)
        retrieved_chunks = format_retrieved_docs(docs)
        final_prompt = rag_prompt_template.format(
            retrieved_chunks=retrieved_chunks,
            question=user_input
        )
    else:
        final_prompt = chat_prompt_template.format(question=user_input)

    retrieve_end = time.perf_counter()

    messages = [
        ("system", system_prompt),
        *build_history_messages(),
        ("user", final_prompt),
    ]

    print("\nAI：", end="", flush=True)

    llm_start = time.perf_counter()

    chunks = []
    first_token_time = None

    for chunk in llm.stream(messages):
        if chunk.content:
            if first_token_time is None:
                first_token_time = time.perf_counter()

            print(chunk.content, end="", flush=True)
            chunks.append(chunk.content)

    llm_end = time.perf_counter()

    answer = "".join(chunks)

    save_to_history(user_input, answer, used_rag)

    print("\n")
    print("-" * 50)
    print(f"檢索耗時: {retrieve_end - retrieve_start:.2f} 秒")
    if first_token_time is not None:
        print(f"首 token 時間: {first_token_time - llm_start:.2f} 秒")
    print(f"LLM 生成耗時: {llm_end - llm_start:.2f} 秒")
    print(f"回答字數: {len(answer)}")
    print(f"目前記憶輪數: {len(conversation_history)}")
    print(f"本輪使用 RAG: {'是' if used_rag else '否'}")
    print("-" * 50)

    return answer


# =========================
# Debug
# =========================

def debug_retrieval(user_input: str) -> None:
    if not should_use_rag(user_input):
        print("\n=== Retrieval Debug ===")
        print("這句話目前判定為一般聊天，本輪不會使用 RAG。")
        print("=== Debug End ===")
        return

    retrieval_query = build_retrieval_query(user_input)
    docs = retrieve_docs(retrieval_query)

    print("\n=== Retrieval Debug ===")
    print(f"原始問題：{user_input}")

    print("\n實際檢索 query：")
    print(retrieval_query)

    print(f"\n檢索文件數：{len(docs)}")

    for i, doc in enumerate(docs, start=1):
        metadata = doc.metadata

        print(f"\n--- DOC {i} ---")
        print("service_name:", metadata.get("service_name", "unknown"))
        print("category:", metadata.get("category", "unknown"))
        print("source_summary:", metadata.get("source_summary", ""))
        print("answer_guidance:", metadata.get("answer_guidance", ""))

        print("\ncontent preview:")
        print(doc.page_content[:1200])

    print("\n=== Debug End ===")


def debug_history() -> None:
    print("\n=== Conversation History ===")
    print(build_history_text())
    print("=== History End ===")


# =========================
# 終端聊天
# =========================

def main() -> None:
    print("\n======================================")
    print("RAG 終端聊天模式：極簡 LLM + RAG 版本")
    print("輸入 q / quit / exit 離開")
    print("輸入 /debug + 問題 可檢視檢索資料")
    print("輸入 /history 可檢視聊天記憶")
    print("輸入 /clear 可清除聊天記憶")
    print("======================================")

    warm_up()

    while True:
        try:
            user_input = input("\n你：").strip()

            if not user_input:
                continue

            if user_input.lower() in ["q", "quit", "exit"]:
                print("已結束聊天。")
                break

            if user_input.startswith("/debug "):
                debug_question = user_input.replace("/debug ", "", 1).strip()
                debug_retrieval(debug_question)
                continue

            if user_input == "/history":
                debug_history()
                continue

            if user_input == "/clear":
                clear_history()
                print("已清除聊天記憶。")
                continue

            chat_with_rag(user_input)

        except KeyboardInterrupt:
            print("\n已中斷聊天。")
            break

        except Exception as e:
            print("\n發生錯誤：", repr(e))


if __name__ == "__main__":
    main()
# ─── 🧠 幫 main.py 做一個專屬的對接傳送門 ───
