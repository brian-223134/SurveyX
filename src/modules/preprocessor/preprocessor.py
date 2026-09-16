import sys
from pathlib import Path

FILE_PATH = Path(__file__).absolute()
BASE_DIR = FILE_PATH.parent.parent
sys.path.insert(0, str(BASE_DIR))

import json

from src.configs.config import COARSE_GRAINED_TOPK
from src.configs.constants import OUTPUT_DIR
from src.configs.logger import get_logger
from src.models.LLM import ChatAgent
from src.models.monitor.time_monitor import TimeMonitor
from src.models.monitor.token_monitor import TokenMonitor
from src.modules.preprocessor.data_cleaner import DataCleaner
from src.modules.preprocessor.paper_filter import PaperFilter
from src.modules.preprocessor.paper_recaller import PaperRecaller
from src.modules.preprocessor.utils import (
    ArgsNamespace,
    create_tmp_config,
    parse_arguments_for_preprocessor,
    save_papers,
)

logger = get_logger("preprocessing.preprocessor")


def _save_fetcher_provenance(fetcher, task_id: str) -> None:
    """fetcher.provenance(dict) 를 outputs/<task_id>/metrics/fetcher_provenance.json 에 쓴다. 없으면 무시."""
    prov = getattr(fetcher, "provenance", None)
    if not isinstance(prov, dict):
        return
    try:
        path = Path(OUTPUT_DIR) / str(task_id) / "metrics" / "fetcher_provenance.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(prov, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        pol = prov.get("retrieval_policy") or {}
        if pol:
            logger.info(
                f"retrieval policy: topic_id={pol.get('topic_id')} cutoff<{pol.get('retrieval_cutoff_at')} "
                f"allowed {pol.get('allowed')}/{pol.get('total')} → {path}"
            )
        else:
            logger.info(f"retrieval policy: none (KISTI_TOPIC_ID unset) → {path}")
    except Exception as e:  # 기록 실패가 실행을 막아서는 안 된다
        logger.warning(f"fetcher provenance not saved: {e!r}")


def _apply_policy_gate(fetcher, papers: list, task_id: str) -> list:
    """허용 집합 밖 `_id` 를 제거한다(fetcher.is_allowed). 걸린 편수는 provenance 파일에 덧붙인다."""
    is_allowed = getattr(fetcher, "is_allowed", None)
    if not callable(is_allowed):
        return papers
    kept, blocked = [], []
    for p in papers:
        (kept if is_allowed(p.get("_id", "")) else blocked).append(p.get("_id"))
    if blocked:
        logger.warning(
            f"[policy] {len(blocked)} papers outside the allowed set dropped before cleaning: {blocked[:5]}"
        )
        papers = [p for p in papers if is_allowed(p.get("_id", ""))]
    path = Path(OUTPUT_DIR) / str(task_id) / "metrics" / "fetcher_provenance.json"
    try:
        if path.exists():
            prov = json.loads(path.read_text(encoding="utf-8"))
            prov["policy_gate"] = {"stage": "after filter, before fulltext", "checked": len(kept) + len(blocked),
                                   "blocked": len(blocked), "blocked_ids": blocked[:50]}
            path.write_text(json.dumps(prov, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    except Exception as e:
        logger.warning(f"policy gate not recorded: {e!r}")
    return papers


def single_preprocessing(args: ArgsNamespace) -> str:
    chat = ChatAgent()
    tmp_config = create_tmp_config(args.title, args.key_words)

    topic = tmp_config["topic"]
    task_id = tmp_config["task_id"]

    chat.token_monitor = TokenMonitor(task_id, "recall paper")

    time_monitor = TimeMonitor(task_id=task_id)
    time_monitor.start("retrieve paper")

    # 1. 논문 리콜
    recaller = PaperRecaller(
        topic=topic, enable_cache=args.enable_cache, chat_agent=chat
    )
    # 데이터 소스 provenance(view·manifest sha·topic 정책)를 편당 기록으로 남긴다 — scripts/collect_run.py 가
    # run.json['retrieval_policy'] 로 싣는다(2026-09-14 규약). 원본 DataFetcher 에는 provenance 가 없어 건너뛴다.
    _save_fetcher_provenance(recaller.data_fetcher, task_id)
    recalled_papers = recaller.recall_papers_iterative(
        tmp_config["key_words"], args.page, args.time_s, args.time_e
    )
    logger.info(
        f"================= totally {len(recalled_papers)} papers have been recalled =================="
    )
    time_monitor.end("retrieve paper")

    # 2. 논문 필터링
    time_monitor.start("filter paper")
    chat.token_monitor = TokenMonitor(task_id, "filter paper")
    pf = PaperFilter(papers=recalled_papers, chat_agent=chat)
    filtered_papers = pf.run(topic=topic, coarse_grained_topk=COARSE_GRAINED_TOPK)
    logger.info(
        f"================= totally {len(filtered_papers)} papers have been saved after filtered =================="
    )

    # 2.4. topic 정책 게이트 — 허용 집합 밖 id 는 이 지점에서 막는다. 이후 단계(정제·AttributeTree·RAG·표)는
    # 모두 outputs/<task_id>/jsons 만 읽으므로 여기가 유일한 깔때기다. 정책이 없거나 fetcher 에 is_allowed 가
    # 없으면(원본·common_corpus) 아무것도 걸러지지 않는다. 검색이 허용 집합 안에서 돌았다면 0편이 걸린다.
    filtered_papers = _apply_policy_gate(recaller.data_fetcher, filtered_papers, task_id)

    # 2.5. 전문 지연 확보 — 필터 통과분에만 md_text를 채운다 (common corpus 어댑터 전용).
    # 원본 DataFetcher 경로에서는 fill_md_text가 없으므로 아무것도 하지 않는다.
    fill_md_text = getattr(recaller.data_fetcher, "fill_md_text", None)
    if callable(fill_md_text):
        time_monitor.start("fetch fulltext")
        filtered_papers = fill_md_text(filtered_papers)
        time_monitor.end("fetch fulltext")

    save_papers(filtered_papers, Path(f"{OUTPUT_DIR}/{str(task_id)}/jsons"))
    time_monitor.end("filter paper")

    # 3. 논문 정제
    chat.token_monitor = TokenMonitor(task_id, "clean paper")
    dc = DataCleaner()
    dc.run(task_id=task_id, chat_agent=chat)

    return task_id


if __name__ == "__main__":
    args = parse_arguments_for_preprocessor()
    single_preprocessing(args=args, chat_agent=ChatAgent())
