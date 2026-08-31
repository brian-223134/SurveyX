"""arXiv 전문을 asg-common-corpus의 FullTextResolver로 배치 확보하는 헬퍼.

⚠️ SurveyX env가 아니라 **asg-corpus conda env의 python**으로 실행해야 한다
(common_corpus 패키지와 그 의존성이 그쪽에 있음). CommonCorpusFetcher가
subprocess로 호출하는 것이 정상 경로이며, 수동 실행도 가능하다:

    /data2/chanjoong/miniforge3/envs/asg-corpus/bin/python \
        scripts/fetch_fulltext_batch.py \
        --corpus-dir /data2/chanjoong/survey-agent/asg-common-corpus \
        --ids-file ids.txt [--retry-failed]

입력: --ids-file — 한 줄에 base arXiv id 하나 (예: 2312.10997)
출력: stdout에 JSONL —
    {"arxiv_id": ..., "status": "ok", "text_path": ".../text.txt"}
    {"arxiv_id": ..., "status": "error", "error": "..."}

fetch 결과는 코퍼스의 data/fulltext_cache/에 영구 캐시되므로 재실행은 즉시
반환된다. 이전에 실패한 id는 resolver가 재시도를 거부하므로(failure.json),
--retry-failed로 실패 기록을 지우고 다시 시도할 수 있다.
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", required=True, help="asg-common-corpus 루트")
    parser.add_argument("--ids-file", required=True, help="base arXiv id 목록 파일")
    parser.add_argument(
        "--retry-failed", action="store_true", help="failure.json을 지우고 재시도"
    )
    args = parser.parse_args()

    corpus_dir = Path(args.corpus_dir)
    # common_corpus가 pip install 되어 있지 않은 경우를 대비한 폴백
    sys.path.insert(0, str(corpus_dir / "src"))
    from common_corpus.fulltext.resolver import FullTextResolver

    cache_dir = corpus_dir / "data" / "fulltext_cache"
    resolver = FullTextResolver(corpus_dir=corpus_dir, cache_dir=cache_dir)

    ids = [
        line.strip()
        for line in Path(args.ids_file).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for arxiv_id in ids:
        slot = cache_dir / "arxiv" / arxiv_id.replace("/", "_")
        if args.retry_failed and (slot / "failure.json").exists():
            (slot / "failure.json").unlink()
        try:
            resolver.resolve(arxiv_id=arxiv_id)
            record = {
                "arxiv_id": arxiv_id,
                "status": "ok",
                "text_path": str(slot / "text.txt"),
            }
        except Exception as e:  # 한 편의 실패가 배치를 중단시키지 않도록
            record = {"arxiv_id": arxiv_id, "status": "error", "error": str(e)}
        print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
