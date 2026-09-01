"""공통 코퍼스 전체(947K편)에 대한 paper_id → 출판 venue lookup을 1회 생성한다.

    python scripts/build_venue_lookup.py            # datasets/venue_lookup.parquet 생성

OpenAlex 미러의 works_locations(6.1억 행)를 코퍼스 papers.parquet와 조인해,
논문마다 가장 신뢰도 높은 출판처 하나를 고른다:

- publishedVersion 우선
- 리포지터리성 소스(arXiv, Zenodo, DOAJ, SSRN 등)는 제외
- 동률이면 이름순으로 결정적(deterministic) 선택

산출물은 gitignore되는 datasets/에 두며(수 MB), 소스가 갱신되면 재실행으로
재생성한다. CommonCorpusFetcher와 rebuild_references.py가 이 파일을 읽어
BibTeX의 journal 필드를 채운다 (없으면 "arXiv preprint" 폴백).

소요: 전체 스캔 1회, 약 1~2분.
"""

import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# 리포지터리/색인 서비스 — 출판 venue가 아니므로 제외
REPO_SOURCES = [
    "%arxiv%", "%zenodo%", "%doaj%", "%ssrn%", "%researchgate%",
    "%citeseer%", "%biorxiv%", "%medrxiv%", "%preprint%", "%repository%",
    "%semantic scholar%", "%core (%",
]


def main():
    import duckdb

    corpus_dir = Path(
        os.getenv("COMMON_CORPUS_DIR", "/data2/chanjoong/survey-agent/asg-common-corpus")
    )
    version = os.getenv("COMMON_CORPUS_VERSION", "v0.1-poc")
    papers = corpus_dir / "data" / "corpus" / version / "papers.parquet"
    locations = (
        corpus_dir / "data" / "upstream" / "cd87dd0" / "openalex"
        / "works_locations" / "works_locations.parquet"
    )
    out_path = Path(
        os.getenv("COMMON_CORPUS_VENUE_LOOKUP", str(REPO_ROOT / "datasets" / "venue_lookup.parquet"))
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    not_repo = " AND ".join(f"l.source_display_name NOT ILIKE '{p}'" for p in REPO_SOURCES)
    con = duckdb.connect()
    t = time.time()
    con.execute(
        f"""
        COPY (
            SELECT p.paper_id,
                   l.source_display_name AS venue,
                   l.version
            FROM read_parquet('{papers}') p
            JOIN read_parquet('{locations}') l
              ON l.work_id = 'https://openalex.org/' || p.paper_id
            WHERE l.source_display_name IS NOT NULL AND {not_repo}
            QUALIFY row_number() OVER (
                PARTITION BY p.paper_id
                ORDER BY (l.version = 'publishedVersion') DESC NULLS LAST,
                         l.source_display_name
            ) = 1
        ) TO '{out_path}' (FORMAT PARQUET)
        """
    )
    n, published = con.execute(
        f"SELECT count(*), count(*) FILTER (version = 'publishedVersion') FROM read_parquet('{out_path}')"
    ).fetchone()
    print(f"wrote {out_path}: {n:,} papers with venue "
          f"({published:,} publishedVersion) in {time.time() - t:.0f}s")


if __name__ == "__main__":
    main()
