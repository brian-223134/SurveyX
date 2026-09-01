"""이미 생성된 태스크의 references.bib를 arXiv 메타데이터로 재구축한다.

    python scripts/rebuild_references.py --task_id 2026-08-31-1231_edge_

배경: 어댑터가 reference(BibTeX) 필드를 채우기 전에 생성된 태스크는
complete_bib() 폴백으로 제목만 있는 @article 항목이 남는다. 이 스크립트는
outputs/<task_id>/papers/의 bib_name·detail_id를 읽어, 공통 코퍼스(연도)와
로컬 arXiv 스냅샷(저자)을 조인해 완성형 항목으로 교체한다.

- 본문의 \\cite 키와 일치하도록 기존 bib_name을 그대로 키로 사용한다.
- 기존 references.bib는 references.bib.bak으로 백업한다.
- LLM 호출 없음. 이후 재컴파일은 LatexGenerator.compile_single_survey() 사용.
"""

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.configs.constants import OUTPUT_DIR  # noqa: E402
from src.modules.preprocessor.common_corpus_fetcher import make_bibtex  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task_id", required=True)
    args = parser.parse_args()

    import duckdb

    task_dir = Path(OUTPUT_DIR) / args.task_id
    papers_dir = task_dir / "papers"
    bib_path = task_dir / "latex" / "references.bib"

    corpus_dir = Path(
        os.getenv("COMMON_CORPUS_DIR", "/data2/chanjoong/survey-agent/asg-common-corpus")
    )
    version = os.getenv("COMMON_CORPUS_VERSION", "v0.1-poc")
    papers_parquet = corpus_dir / "data" / "corpus" / version / "papers.parquet"
    snapshot_db = os.getenv("ARXIV_SNAPSHOT_DUCKDB", "")

    # 1. 태스크의 최종 인용 풀 로드
    papers = []
    for f in sorted(papers_dir.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        detail_id = str(d.get("detail_id", ""))
        arxiv_id = detail_id.removeprefix("arXiv:") if detail_id.startswith("arXiv:") else None
        papers.append({"bib_name": d["bib_name"], "title": d["title"], "arxiv_id": arxiv_id})
    ids = [p["arxiv_id"] for p in papers if p["arxiv_id"]]
    print(f"{len(papers)} papers loaded, {len(ids)} with arXiv id")

    # 2. 연도(코퍼스) + 저자(스냅샷) 조회
    con = duckdb.connect()
    years = dict(
        con.execute(
            f"SELECT arxiv_id, year FROM read_parquet(?) WHERE arxiv_id = ANY(?)",
            [str(papers_parquet), ids],
        ).fetchall()
    )
    authors = {}
    if snapshot_db and Path(snapshot_db).exists():
        con.execute(f"ATTACH '{snapshot_db}' AS snap (READ_ONLY)")
        authors = dict(
            con.execute(
                "SELECT base_id, authors FROM snap.papers WHERE base_id = ANY(?)", [ids]
            ).fetchall()
        )
    print(f"matched: year {len(years)}, authors {len(authors)}")

    # 3. 기존 bib_name을 키로 완성형 항목 생성
    entries = [
        make_bibtex(
            arxiv_id=p["arxiv_id"] or "",
            title=p["title"],
            authors_json=authors.get(p["arxiv_id"]),
            year=years.get(p["arxiv_id"]),
            bib_key=p["bib_name"],
        )
        for p in papers
    ]

    backup = bib_path.with_suffix(".bib.bak")
    if not backup.exists():
        backup.write_bytes(bib_path.read_bytes())
        print(f"backup: {backup}")
    bib_path.write_text("\n".join(entries) + "\n", encoding="utf-8")
    enriched = sum(1 for e in entries if "author={" in e)
    print(f"wrote {len(entries)} entries ({enriched} with authors) to {bib_path}")


if __name__ == "__main__":
    main()
