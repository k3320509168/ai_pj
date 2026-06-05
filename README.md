# AI Humanity Term Project

本專案目前的主流程是一個面向銀髮族與獨居長者的終端聊天機器人。系統會先判斷使用者是在日常聊天，還是在詢問福利、照顧資源或生活支持資訊：

- 一般聊天時，模型以陪伴者語氣延續對話，不主動推銷福利服務。
- 進入 RAG 時，模型會優先根據資訊卡資料專業回答資格、申請方式、文件、金額、電話或服務內容。

目前主程式為 `LLM_run/chatbotV2.py`，RAG 主資料來源為 `RAG_Embedding/uploaded_docs_JSON/informationCard.json`。

## Current Architecture

```text
User terminal input
        |
        v
LLM_run/chatbotV2.py
        |
        +--> Chat routing
        |      |
        |      +--> no RAG
        |      |      -> short conversation history
        |      |      -> chat prompt
        |      |      -> Ollama ChatOllama gemma3:4b
        |      |
        |      +--> use RAG
        |             -> resource keyword / follow-up / service alias routing
        |             -> FAISS retrieval
        |             -> RAG prompt
        |             -> Ollama ChatOllama gemma3:4b
        |
        v
Terminal response + timing/debug output
```

```text
RAG_Embedding/uploaded_docs_JSON/informationCard.json
        |
        v
RAG_Embedding/embeddingJSON.py
        |
        +--> build short retrieval text for embeddings
        +--> keep full card text as answer metadata
        |
        v
RAG_Embedding/faiss_db_local_JSON_v2
        |
        v
LLM_run/chatbotV2.py
```

## Directory Layout

```text
term_project/
|-- README.md
|-- requirements.txt
|-- run_chatbot.py
|-- LLM_run/
|   |-- chatbotV2.py
|   `-- README.md
|-- RAG_Embedding/
|   |-- embeddingJSON.py
|   |-- uploaded_docs_JSON/
|   |   `-- informationCard.json
|   |-- uploaded_docs/
|   `-- faiss_db_local_JSON_v2/
`-- whisper_run/
    |-- asr.py
    |-- README.md
    `-- test.wav
```

### Main Modules

| Path | Role |
|---|---|
| `LLM_run/chatbotV2.py` | Current terminal chatbot and RAG runtime |
| `run_chatbot.py` | Project-root launcher for the terminal chatbot |
| `RAG_Embedding/uploaded_docs_JSON/informationCard.json` | Structured social-service information cards |
| `RAG_Embedding/embeddingJSON.py` | Builds the JSON-card FAISS index used by `chatbotV2.py` |
| `RAG_Embedding/faiss_db_local_JSON_v2/` | Current FAISS index for JSON-card RAG |
| `requirements.txt` | Project-level Python dependencies |

### Supporting Paths

| Path | Role |
|---|---|
| `LLM_run/README.md` | Chatbot conversation records and local notes |
| `RAG_Embedding/uploaded_docs/` | Raw PDF reference materials used while curating information cards |
| `whisper_run/asr.py` | ASR experiment using `MediaTek-Research/Breeze-ASR-26` |

## Runtime Components

### Models

`chatbotV2.py` currently expects an Ollama server at:

```text
http://localhost:11434
```

It uses:

| Purpose | Model |
|---|---|
| Chat LLM | `gemma3:4b` |
| Embedding | `nomic-embed-text` |

### Vector Store

The current JSON-card FAISS index path is:

```text
RAG_Embedding/faiss_db_local_JSON_v2
```

`chatbotV2.py` loads it from:

```python
FAISS_DB_PATH = "../RAG_Embedding/faiss_db_local_JSON_v2"
```

## Data Design

### Information Cards

`informationCard.json` stores one structured card per service. The current cards include topics such as:

- 中低收入老人生活津貼
- 老年年金給付
- 中低收入老人特別照顧津貼
- 敬老卡申辦
- 臺北市獨居老人服務

Each card contains structured fields such as:

- `service_name`
- `category`
- `target_users`
- `service_summary`
- `eligibility`
- `benefits`
- `required_documents`
- `application_method`
- `contact_info`
- `important_notes`
- `answer_guidance`
- `text`

### Retrieval Text vs Answer Content

The current JSON embedding flow separates retrieval and answer data:

1. `embeddingJSON.py` builds a short positive retrieval text from fields such as service name, summary, target users, eligibility and application method.
2. The retrieval text is embedded into FAISS.
3. The full card `text` is kept in metadata as `answer_content`.
4. When a card is retrieved, `chatbotV2.py` sends the full answer content to the LLM.

This separation reduces retrieval confusion caused by very long cards and negative cross-service labels such as `not_suitable_for`.

## Chatbot Flow

### 1. Chat Mode

If the current turn does not look like a resource question, `chatbotV2.py` uses chat mode:

- No FAISS retrieval.
- Recent user and assistant turns are passed as message history.
- The prompt emphasizes natural conversation, companionship and short replies.

### 2. RAG Mode

RAG mode is triggered by:

- Resource keywords such as `福利`, `補助`, `申請`, `資格`, `敬老卡`, `長照`, `送餐`.
- Heat and cooling-related keywords currently stored in `RESOURCE_KEYWORDS`, such as `好熱`, `避熱`, `沒冷氣`.
- One-turn resource context carryover after a keyword hit.
- Resource follow-up wording after a RAG turn, such as `那`, `這個`, `怎麼申請`, `多少錢`.

In RAG mode:

1. A retrieval query is built from the current user input and recent RAG-related user context.
2. Service aliases are checked first.
3. If a service is explicitly named, the system filters retrieval to that service card.
4. Otherwise the FAISS similarity retriever returns the top cards.
5. The RAG prompt asks the LLM to answer professionally and focus on the requested information.

### 3. Service Alias Routing

`chatbotV2.py` has explicit service aliases to reduce mixed-card retrieval. For example:

```text
敬老卡 / 敬老悠遊卡 / 老人悠遊卡
    -> 敬老卡申辦
```

This is important because many social-service cards share wording such as `65歲`, `臺北市`, `申請`, `資格` and `補助`.

## Short-Term Memory

`chatbotV2.py` keeps a short in-memory conversation history:

```python
MAX_HISTORY_TURNS = 6
```

The history is reset when the process exits. It can also be cleared during chat with:

```text
/clear
```

## Setup

### 1. Python Environment

Install dependencies from the project root:

```powershell
pip install -r requirements.txt
```

The current workspace has been run with a Conda environment named `LLM_midProject`.

### 2. Start Ollama

Make sure the Ollama service is running:

```powershell
ollama serve
```

In another terminal, verify the required models exist:

```powershell
ollama list
```

If needed, pull the models:

```powershell
ollama pull gemma3:4b
ollama pull nomic-embed-text
```

## Build the JSON RAG Index

After editing `informationCard.json`, rebuild the current FAISS index:

```powershell
cd RAG_Embedding
python embeddingJSON.py
```

Expected output path:

```text
RAG_Embedding/faiss_db_local_JSON_v2
```

If the embedding build fails with an Ollama connection error, check that Ollama is running. If it fails with a model-not-found error, check that `nomic-embed-text` is available in Ollama.

## Run the Chatbot

From the project root:

```powershell
python run_chatbot.py
```

The root launcher checks that the chatbot entry file and current FAISS index exist, then starts `LLM_run/chatbotV2.py` from the working directory it expects.

You can still run the chatbot entry file directly:

```powershell
cd LLM_run
python chatbotV2.py
```

The chatbot warms up:

- `gemma3:4b`
- `nomic-embed-text`

Then it enters terminal chat mode.

## Terminal Commands

| Command | Purpose |
|---|---|
| `q`, `quit`, `exit` | Leave the chatbot |
| `/history` | Print current short-term memory |
| `/clear` | Clear current short-term memory |
| `/debug <question>` | Show retrieval query and retrieved cards |

Example:

```text
/debug 我65歲可以辦敬老卡嗎
```

For the current implementation, a direct `敬老卡` question should retrieve the `敬老卡申辦` card rather than 老人津貼 cards.

## Debugging RAG Quality

When an answer looks wrong, debug the retrieval result before changing the prompt:

```text
/debug <your question>
```

Check:

1. Did the turn enter RAG mode?
2. Did the correct service card appear?
3. Did an unrelated card appear before the correct card?
4. Is the query too vague or missing service context?

If retrieval is wrong, fix indexing, service alias routing, metadata filtering or card retrieval text before blaming the generation model.

## Current Limitations

- The service alias table is manual and currently covers only known service names and aliases.
- The fallback retriever is still FAISS similarity search with a small `k`.
- The chatbot uses in-memory short-term history only; there is no persistent user profile.
- Keyword-based RAG routing is intentionally simple and can be too eager or too conservative depending on phrasing.
- The JSON information cards are curated for the current service set; adding many more services may require hybrid search, reranking or finer card chunking.

## ASR Experiment

`whisper_run/asr.py` is a separate speech-recognition experiment. It reads `test.wav` and runs:

```text
MediaTek-Research/Breeze-ASR-26
```

It is not currently wired into `chatbotV2.py`.
