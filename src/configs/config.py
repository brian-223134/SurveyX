import json
from pathlib import Path
import os

FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent.parent.parent

# .env 로드 — 설정은 .env(.env.example 참조)에서 읽고, 없으면 아래 기본값 사용
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# huggingface 미러
# os.environ["HF_ENDPOINT"] = "https://hf-mirror.com" # 특정 Hugging Face 미러를 쓰려면 이 줄의 주석을 해제하세요
# os.environ["HF_HOME"] = os.path.expanduser("~/hf_cache/")

REMOTE_URL = os.getenv(
    "SURVEYX_REMOTE_URL", "https://api.openai.com/v1/chat/completions"
)
TOKEN = os.getenv("OPENROUTER_API_KEY", "your token here")
DEFAULT_CHATAGENT_MODEL = os.getenv("SURVEYX_DEFAULT_MODEL", "gpt-4o-mini")
ADVANCED_CHATAGENT_MODEL = os.getenv("SURVEYX_ADVANCED_MODEL", "gpt-4o")

# OpenRouter provider 라우팅 고정 (예: "akashml/fp8"). 비우면 provider 블록 미전송.
# 같은 모델이라도 provider마다 quantization이 달라, 고정하지 않으면 서베이 한 편
# 안에서 호출마다 다른 정밀도가 섞인다. allow_fallbacks=false로 이탈도 막는다.
OPENROUTER_PROVIDER_ONLY = os.getenv("OPENROUTER_PROVIDER_ONLY", "")
OPENROUTER_ALLOW_FALLBACKS = (
    os.getenv("OPENROUTER_ALLOW_FALLBACKS", "false").lower() == "true"
)

# LLM HTTP 타임아웃(초). 미설정 시 무한 대기로 파이프라인이 행에 걸릴 수 있다.
CHAT_REQUEST_TIMEOUT = int(os.getenv("SURVEYX_HTTP_TIMEOUT", "900"))

LOCAL_URL = "LOCAL_URL"
LOCAL_LLM = "LOCAL_LLM"
DEFAULT_EMBED_LOCAL_MODEL = "DEFAULT_EMBED_LOCAL_MODEL"

## 임베딩 모델 설정 (파이프라인은 로컬 HF 임베딩을 사용 — 원격은 선택 사항)
DEFAULT_EMBED_ONLINE_MODEL = "BAAI/bge-base-en-v1.5"
EMBED_REMOTE_URL = (
    os.getenv("EMBED_REMOTE_URL") or "https://api.siliconflow.cn/v1/embeddings"
)
EMBED_TOKEN = os.getenv("EMBED_TOKEN") or "your embed token here"
SPLITTER_WINDOW_SIZE = 6
SPLITTER_CHUNK_SIZE = 2048

## 전처리 설정
CRAWLER_BASE_URL = ""
CRAWLER_GOOGLE_SCHOLAR_SEND_TASK_URL = ""
DEFAULT_DATA_FETCHER_ENABLE_CACHE = True
CUT_WORD_LENGTH = 10
MD_TEXT_LENGTH = 20000
ARXIV_PROJECTION = (
    "_id, title, authors, detail_url, abstract, md_text, reference, detail_id, image"
)

## 반복 횟수 및 논문 풀 크기 제한
DEFAULT_ITERATION_LIMIT = 3
DEFAULT_PAPER_POOL_LIMIT = 1024

## llamaindex OpenAI 설정
DEFAULT_LLAMAINDEX_OPENAI_MODEL = "gpt-4o"
# DEFAULT_OPENAI_MODEL = "gpt-3.5-turbo"
CHAT_AGENT_WORKERS = 4

## survey 생성 설정
COARSE_GRAINED_TOPK = 200
MIN_FILTERED_LIMIT = 150
NUM_PROCESS_LIMIT = 10

## 그림(figure) 검색 설정
FIG_RETRIEVE_URL = ""
ENHANCED_FIG_RETRIEVE_URL = ""
FIG_CHUNK_SIZE = 8192
MATCH_TOPK = 3
FIG_RETRIEVE_Authorization = ""
FIG_RETRIEVE_TOKEN = ""
