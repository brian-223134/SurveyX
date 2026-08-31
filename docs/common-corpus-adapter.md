# Common Corpus 어댑터 설계

SurveyX의 문헌 수집 계층(`DataFetcher`)을 [asg-common-corpus](../../asg-common-corpus)로
대체하는 어댑터의 설계 문서. 코퍼스 구축 배경과 지연 파싱 설계 근거는
[REPRODUCTION.md](../REPRODUCTION.md), 재현 전체 범위는 [README.md](../README.md) 참조.

## 1. 목표와 제약

- **same-corpus 비교**: AutoSurvey · SurveyForge · LLMxMapReduce-V2와 동일한
  paper universe(view)에서 서베이를 생성해 공정 비교를 성립시킨다.
- **상위 모듈 무수정**: `PaperRecaller`/`PaperFilter`가 기대하는
  `search_on_arxiv(key_words)` / `search_on_google(...)` 계약만 지킨다.
- **코퍼스 불변 규칙 준수** (integration-guide §1): 온라인 검색 비활성,
  실행 기록에 view 이름 + manifest sha256 남기기.

## 2. 구성 요소

| 파일 | 역할 |
|---|---|
| `src/modules/preprocessor/common_corpus_fetcher.py` | `CommonCorpusFetcher` — 검색(DuckDB) + 전문 지연 확보 |
| `src/modules/preprocessor/data_fetcher.py` `get_data_fetcher()` | `SURVEYX_DATA_SOURCE=common_corpus`일 때 어댑터 선택하는 팩토리 |
| `scripts/fetch_fulltext_batch.py` | asg-corpus conda env에서 `FullTextResolver`를 배치 실행하는 헬퍼 |
| `src/modules/preprocessor/data_cleaner.py` | C0 가드 2건 — 아래 §5 |
| `src/modules/preprocessor/preprocessor.py` | 필터 통과 후 `fill_md_text()` 훅 (2.5단계) |

## 3. 검색 (`search_on_arxiv`)

원 코드의 시맨틱(제목/초록 부분 문자열 매칭, 키워드당 상한 1,000편)을
DuckDB ILIKE 스캔으로 그대로 재현한다. 인덱스 사전 구축 없이 키워드당 ~1초.

```sql
SELECT p.paper_id, p.arxiv_id, p.title, p.abstract, p.year, p.citation_count
FROM read_parquet('.../papers.parquet') p
JOIN read_parquet('.../views/<view>/paper_ids.parquet') v USING (paper_id)
WHERE p.title ILIKE '%kw%' OR p.abstract ILIKE '%kw%'
ORDER BY p.citation_count DESC NULLS LAST, p.paper_id
LIMIT 1000
```

설계 판단:

- **view JOIN이 컷오프·GT 제외를 강제** — `surveyeval-2512`
  (cutoff 2025-12-31, GT 서베이 20편 제외)를 기본값으로 사용.
- **1,000편 초과 시 citation_count 내림차순으로 절단**. 원 인프라(ES)의 절단
  기준은 알 수 없으므로, 무작위 대신 인용수를 사전 순위(prior)로 택했다.
  관련성 판정은 어차피 하류의 coarse(임베딩 Top-200)/fine(LLM) 필터가 수행한다.
- **쉼표 구분 키워드는 합집합 병합** — 원 코드의 무력화된 overlap≥2 필터를
  복원하지 않고 현행 동작(≥1)을 유지 (README §8의 미결 사항, 복원 시 별도 결정).
- `search_on_google()`은 항상 빈 리스트 (same-corpus 원칙. `from` 필드 규약 유지).

반환 dict 매핑:

| SurveyX 필드 | 값 | 비고 |
|---|---|---|
| `_id` | `paper_id` (OpenAlex W-id) | 캐시 파일명·중복 제거 키 |
| `detail_id` | `arXiv:{arxiv_id}` | eval/data/ref 형식 준수 |
| `arxiv_id` | base id (예: `2312.10997`) | 전문 확보·보강 조인 키 |
| `title`, `abstract` | 그대로 | 커버리지 100% |
| `detail_url` | `http://arxiv.org/abs/{arxiv_id}` | |
| `from` | `"arxiv"` | 상위 코드 분기 유지 |
| `year`, `citation_count` | 그대로 | 부가 메타데이터 |

## 4. 전문 지연 확보 (`fill_md_text`)

전문 파싱이 병목이므로 **필터 통과분(150~200편)에만** 전문을 채운다
(REPRODUCTION.md §3 — 1,000편 전부 대비 5~7배 절감).

```
recall (title/abstract만) → coarse/fine filter → fill_md_text() → DataCleaner
```

- 실행 흐름: `preprocessor.py` 2.5단계에서 `fill_md_text(filtered_papers)` 호출
  → arXiv id 목록을 임시 파일로 넘겨 `scripts/fetch_fulltext_batch.py`를
  **asg-corpus conda env python으로 subprocess 실행** → JSONL 결과의
  `text_path`(코퍼스 `fulltext_cache`)를 읽어 `md_text`에 주입.
- subprocess로 분리한 이유: `common_corpus` 패키지 의존성(duckdb/pydantic v2 등)을
  SurveyX env에 끌어오지 않기 위함. SurveyX env에는 `duckdb`(검색용)만 추가.
- fetch는 arXiv e-print 기준 3초/편 순차(코퍼스 정책) + LaTeX→text 파싱.
  200편 신규 기준 최악 ~15분, 캐시 히트는 즉시. `COMMON_CORPUS_FULLTEXT_LIMIT`로
  스모크 시 상한 설정 가능.
- 실패(429, 소스 없음 등)한 논문은 `md_text` 없이 남고,
  `DataCleaner.load_json_dir`의 기존 md_text 게이트에서 자연 탈락한다.
  재시도는 헬퍼의 `--retry-failed`로 failure.json을 지운 뒤 수행.
- 코퍼스가 주는 것은 진짜 Markdown이 아니라 **섹션 헤딩만 `##`로 변환된
  plain text**다. AttributeTree 입력으로는 충분하며, `MD_TEXT_LENGTH=20000`
  토큰 절단은 기존 로직 그대로 적용된다.

## 5. 기존 코드 수정 (C0 가드)

REPRODUCTION.md §3.1에서 식별한 지연 파싱 차단 지점 2곳:

1. `DataCleaner.quick_check()` — `md_text` 필수 조건 제거. title/abstract를
   md_text로도 복원할 수 없는 레코드만 버린다. (전문이 있는 기존 오프라인
   흐름의 동작은 불변)
2. `DataCleaner.complete_abstract()` — `md_text` 부재 시 skip 가드.
   코퍼스 초록은 50자 이상이 보장되지만 500자 미만이 흔해 가드 없이는
   KeyError가 실제로 발생하는 경로였다.

## 6. 재현성 (provenance)

어댑터는 초기화 시 `view_manifest.json`의 sha256을 계산해
`self.provenance`로 노출하고 로그에 남긴다. 실행 기록/실험 노트에는
`view=surveyeval-2512, view_manifest_sha256=...`을 함께 기록할 것
(코퍼스 integration-guide §7 체크리스트).

## 7. 한계와 후속 작업

- **authors 없음** — 코퍼스 parquet에 authors 컬럼이 없다. 필요 시
  `ARXIV_SNAPSHOT_DUCKDB`(survey-search의 로컬 arXiv 스냅샷, base_id 조인,
  커버리지 ~65%)로 보강. 현재 파이프라인은 authors 없이 동작한다.
- **reference(BibTeX) 없음** — 코퍼스 파서가 bibliography를 제거한다.
  `complete_bib()`가 제목 기반 `@article{...}`을 자동 생성하므로 파이프라인은
  돌지만, 인용 품질 평가 신뢰도를 위해 arXiv 메타데이터 기반 BibTeX 생성을
  후속 작업으로 남긴다.
- **image 없음** — 멀티모달(그림 검색·삽입)은 이번 재현 범위에서 제외.
- **출처 분포 차이** — 원 논문은 arXiv 86% + Google Scholar 14%, 어댑터는
  arXiv 100%. Table 3 수치와 비교할 때 편차 요인으로 기록해 둘 것.

## 8. 스모크 테스트

```bash
# 검색 + 전문 확보 (asg-corpus env로 실행 — duckdb 포함)
/data2/chanjoong/miniforge3/envs/asg-corpus/bin/python \
    -m src.modules.preprocessor.common_corpus_fetcher
```

2026-08-31 실측: 키워드당 1,000편 검색 ~1초, 전문 2편(캐시 1 + 신규 1) 4초.
