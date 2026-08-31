"""asg-common-corpus를 데이터 소스로 쓰는 DataFetcher 대체 구현.

원 논문의 사내 인프라(오프라인 arXiv Elasticsearch + Google Scholar 크롤러 팜)를
공통 코퍼스(../asg-common-corpus)의 parquet + view + FullTextResolver로 대체한다.

계약 (paper_recaller.py가 기대하는 것):
    search_on_arxiv(key_words: str) -> list[dict]      # 쉼표 구분 키워드
    search_on_google(key_words, page, time_s, time_e) -> list[dict]

same-corpus 원칙(코퍼스 integration-guide §1)에 따라:
- 온라인 검색은 수행하지 않는다. search_on_google()은 항상 빈 리스트.
- 검색은 view(컷오프+GT제외)를 JOIN한 papers.parquet 위 ILIKE 스캔으로 수행
  (원 코드 search_on_arxiv_single_word의 제목/초록 부분 문자열 매칭과 동일 시맨틱).
- 전문(md_text)은 여기서 채우지 않는다. 필터 통과분에 대해서만
  fill_md_text()로 지연 확보한다 (asg-corpus conda env에 subprocess 위임).

환경변수 (.env / .env.example 참조):
    COMMON_CORPUS_DIR, COMMON_CORPUS_VERSION, COMMON_CORPUS_VIEW,
    COMMON_CORPUS_PYTHON, COMMON_CORPUS_FULLTEXT_LIMIT
"""

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from src.configs.config import BASE_DIR
from src.configs.logger import get_logger

try:  # .env가 있으면 로드 (없어도 동작)
    from dotenv import load_dotenv

    load_dotenv(Path(BASE_DIR) / ".env")
except ImportError:
    pass

logger = get_logger("src.modules.preprocessor.CommonCorpusFetcher")


class CommonCorpusFetcher:
    SINGLE_WORD_LIMIT = 1000  # DataFetcher.SINGLE_WORD_LIMIT과 동일

    def __init__(self, enable_cache: bool = True):
        self.corpus_dir = Path(
            os.getenv(
                "COMMON_CORPUS_DIR", "/data2/chanjoong/survey-agent/asg-common-corpus"
            )
        )
        version = os.getenv("COMMON_CORPUS_VERSION", "v0.1-poc")
        self.view_name = os.getenv("COMMON_CORPUS_VIEW", "surveyeval-2512")
        self.corpus_python = os.getenv(
            "COMMON_CORPUS_PYTHON",
            "/data2/chanjoong/miniforge3/envs/asg-corpus/bin/python",
        )

        self.papers_parquet = (
            self.corpus_dir / "data" / "corpus" / version / "papers.parquet"
        )
        self.view_parquet = (
            self.corpus_dir / "data" / "views" / self.view_name / "paper_ids.parquet"
        )
        self.view_manifest = (
            self.corpus_dir / "data" / "views" / self.view_name / "view_manifest.json"
        )
        if not self.papers_parquet.exists():
            raise FileNotFoundError(f"corpus parquet not found: {self.papers_parquet}")
        if not self.view_parquet.exists():
            raise FileNotFoundError(f"view parquet not found: {self.view_parquet}")

        # 실행 기록용 provenance (integration-guide §7: view 이름 + manifest sha)
        self.provenance = {
            "view": self.view_name,
            "view_manifest_sha256": hashlib.sha256(
                self.view_manifest.read_bytes()
            ).hexdigest()
            if self.view_manifest.exists()
            else None,
        }
        logger.info(f"CommonCorpusFetcher provenance: {self.provenance}")

        self.enable_cache = enable_cache  # 코퍼스가 로컬이라 파일 캐시는 불필요
        self._kw_cache: dict[str, list[dict]] = {}  # 반복 리콜 대비 프로세스 내 캐시

        import duckdb  # 지연 임포트 — 어댑터를 쓸 때만 요구

        self._con = duckdb.connect()

    # ---------------------------------------------------------------- search
    def search_on_arxiv(self, key_words: str) -> list[dict]:
        """쉼표로 구분된 키워드 각각을 검색해 _id 기준으로 병합한다.

        원 코드(data_fetcher.py:307)와 동일하게 합집합을 반환한다
        (docstring의 overlap>=2 필터는 원 코드에서도 무력화 상태).
        """
        id2paper: dict[str, dict] = {}
        for key_word in key_words.split(","):
            key_word = key_word.strip()
            if not key_word:
                continue
            papers = self.search_on_arxiv_single_word(key_word)
            id2paper.update({paper["_id"]: paper for paper in papers})

        merged = list(id2paper.values())
        logger.debug(f"common_corpus: {len(merged)} unique papers for '{key_words}'")
        return merged

    def search_on_arxiv_single_word(self, key_word: str) -> list[dict]:
        """제목/초록에 key_word가 부분 문자열로 등장하는 논문을 view 범위 안에서 반환."""
        if key_word in self._kw_cache:
            return self._kw_cache[key_word]

        pattern = (
            "%"
            + key_word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            + "%"
        )
        rows = self._con.execute(
            r"""
            SELECT p.paper_id, p.arxiv_id, p.title, p.abstract,
                   p.year, p.citation_count
            FROM read_parquet(?) p
            JOIN read_parquet(?) v USING (paper_id)
            WHERE p.title ILIKE ? ESCAPE '\' OR p.abstract ILIKE ? ESCAPE '\'
            ORDER BY p.citation_count DESC NULLS LAST, p.paper_id
            LIMIT ?
            """,
            [
                str(self.papers_parquet),
                str(self.view_parquet),
                pattern,
                pattern,
                self.SINGLE_WORD_LIMIT,
            ],
        ).fetchall()

        papers = [
            {
                "_id": paper_id,
                "detail_id": f"arXiv:{arxiv_id}",
                "arxiv_id": arxiv_id,
                "title": title,
                "abstract": abstract,
                "detail_url": f"http://arxiv.org/abs/{arxiv_id}",
                "year": year,
                "citation_count": citation_count,
                "from": "arxiv",
            }
            for paper_id, arxiv_id, title, abstract, year, citation_count in rows
        ]
        logger.debug(f"common_corpus: {len(papers)} papers for keyword '{key_word}'")
        self._kw_cache[key_word] = papers
        return papers

    def search_on_google(
        self, key_words: str, page: str, time_s: str = "", time_e: str = ""
    ) -> list[dict]:
        """same-corpus 원칙에 따라 온라인 검색은 비활성 — 항상 빈 리스트."""
        logger.debug("common_corpus: search_on_google disabled (same-corpus setting)")
        return []

    # -------------------------------------------------------------- fulltext
    def fill_md_text(self, papers: list[dict]) -> list[dict]:
        """필터를 통과한 논문에 한해 전문을 확보해 md_text를 채운다.

        arXiv e-print fetch(3초/편 딜레이)는 asg-corpus env의 FullTextResolver에
        subprocess로 위임하고, 결과는 코퍼스의 fulltext_cache에 영구 캐시된다.
        실패한 논문은 md_text 없이 남는다 (DataCleaner.load_json_dir에서 탈락).
        """
        targets = [
            p for p in papers if "md_text" not in p and p.get("arxiv_id")
        ]
        limit = int(os.getenv("COMMON_CORPUS_FULLTEXT_LIMIT", "0"))
        if limit > 0:
            targets = targets[:limit]
        if not targets:
            return papers

        logger.info(
            f"fetching fulltext for {len(targets)} papers "
            f"(~{len(targets) * 4}s worst case, cached ones are instant)"
        )
        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        ) as fw:
            fw.write("\n".join(p["arxiv_id"] for p in targets))
            ids_file = fw.name

        helper = Path(BASE_DIR) / "scripts" / "fetch_fulltext_batch.py"
        proc = subprocess.run(
            [
                self.corpus_python,
                str(helper),
                "--corpus-dir",
                str(self.corpus_dir),
                "--ids-file",
                ids_file,
            ],
            capture_output=True,
            text=True,
        )
        os.unlink(ids_file)
        if proc.returncode != 0:
            logger.error(f"fulltext helper failed:\n{proc.stderr[-2000:]}")
            return papers

        results = {}
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                results[rec["arxiv_id"]] = rec
            except json.JSONDecodeError:
                continue

        ok, failed = 0, 0
        for paper in targets:
            rec = results.get(paper["arxiv_id"])
            if rec and rec.get("status") == "ok":
                text_path = Path(rec["text_path"])
                if text_path.exists():
                    paper["md_text"] = text_path.read_text(encoding="utf-8")
                    ok += 1
                    continue
            failed += 1
            logger.warning(
                f"fulltext unavailable for {paper['arxiv_id']} "
                f"({(rec or {}).get('error', 'no result')})"
            )
        logger.info(f"fulltext filled: {ok} ok, {failed} failed")
        return papers


# python -m src.modules.preprocessor.common_corpus_fetcher
if __name__ == "__main__":
    fetcher = CommonCorpusFetcher()
    found = fetcher.search_on_arxiv("retrieval-augmented generation, hallucination")
    print(f"{len(found)} papers, top-3:")
    for paper in found[:3]:
        print(f"  [{paper['citation_count']}] {paper['title']}")
    fetcher.fill_md_text(found[:2])
    for paper in found[:2]:
        print(f"  md_text: {len(paper.get('md_text', ''))} chars — {paper['title']}")
