# 코퍼스 구축 설계 (Corpus Design)

SurveyX 재현에서 유일하게 비어 있는 구성 요소인 **문헌 수집 계층(`DataFetcher`)**을 어떻게 다시 만들 것인지에 대한 설계 문서입니다. 전체 재현 범위와 제공/미제공 구분은 [README.md](README.md)를 참조하세요.

---

## 1. 논문 인프라 역설계

`DataFetcher`는 URL·토큰만 비워졌을 뿐 **요청/응답 형태가 코드에 그대로 남아 있어** 원래 인프라 구조를 읽을 수 있습니다. 아래는 코드 근거에 기반한 재구성입니다.

### 1.1 arXiv 저장소는 Elasticsearch

`_get_data_arxiv()`는 `/api/search_arxiv`에 다음을 전송합니다.

```python
{"abstract": keyword, "title": keyword, "start_id": last_id, "projection": ..., "limit": "200"}
```

응답에서 `data.datas[]`를 순회하며 `_source`를 꺼내 논문 dict로 씁니다. `_source`는 Elasticsearch 히트 포맷입니다.

시사점:
- 263만 편을 **title/abstract 전문 색인**으로 올려두고 **키워드 매칭**으로 조회합니다. 이 단계는 벡터 검색이 아닙니다 (벡터 검색은 이후 `PaperFilter`의 coarse 단계에서 수행).
- `start_id` 커서 기반 페이지네이션, 배치 200건(`BATCH_SIZE`), 키워드당 최대 1,000건(`SINGLE_WORD_LIMIT`).

### 1.2 Google Scholar 쪽은 MongoDB + 비동기 크롤러 큐

`_get_data()`는 `dbName: "crawler_spider"`에 다음 필터를 보냅니다.

```python
{"_id": {"$gt": last_id}, "search_id": str(search_id)}
```

MongoDB 쿼리 문법 그대로입니다. 수집 흐름은 다음과 같습니다.

1. `task_submit()` — `CRAWLER-PY-GOOGLE-SCHOLAR-SEARCH` 큐에 검색 작업을 넣고 `search_id`를 발급
2. `task_track_for_google_scholar()` — `google_scholar_monitor` 컬렉션을 폴링하며 `status`, `final_succ_count`, `final_fail_count`, `meta_count`로 완료 판정
3. 완료 후 `google_scholar` 컬렉션에서 `search_id`로 결과 수집 (페이지당 10건)

즉 **검색과 수집이 비동기로 분리된 크롤러 팜**이며, 타임아웃은 5분(`CRAWLING_TIMEOUT`)입니다.

### 1.3 전문·그림은 수집 시점에 미리 처리

`ARXIV_PROJECTION`이 결정적 단서입니다.

```python
ARXIV_PROJECTION = "_id, title, authors, detail_url, abstract, md_text, reference, detail_id, image"
```

`md_text`(전문 Markdown)와 `image`가 **DB에 이미 저장된 필드**입니다. 즉 PDF → Markdown 변환과 그림 추출을 검색 시점이 아니라 **수집·색인 시점에 배치로** 끝내둔 구조입니다. 저장소에 파싱 코드가 한 줄도 없는 이유가 이것입니다 — 파이프라인 밖의 별도 인프라였습니다.

**재현 관점의 결론: 우리가 새로 만들어야 하는 것은 검색 API 래퍼가 아니라 "전문이 채워진 논문 저장소"입니다.**

---

## 2. 규모 재해석 — 263만 편은 필수가 아니다

논문의 263만 편은 위압적이지만, 서베이 1편 생성에 실제로 소비되는 양은 훨씬 적습니다.

| 단계 | 논문/코드 값 | 규모 |
|---|---|---|
| 리콜 풀 상한 | `DEFAULT_PAPER_POOL_LIMIT = 1024` (논문 θ=1000) | ~1,000편 |
| coarse 필터 통과 | `COARSE_GRAINED_TOPK = 200` | 200편 |
| fine 필터 통과 | `MIN_FILTERED_LIMIT = 150` | 150~200편 |
| AttributeTree 입력 | `MD_TEXT_LENGTH = 20000` 토큰으로 절단 | 편당 ~20k 토큰 |

263만 편은 **빠른 키워드 조회를 위한 정적 색인**일 뿐이며, 재현에 전량이 필요하지 않습니다. 논문 Table 4의 20개 토픽을 전부 재현해도 중복 제외 **2만 편 규모**입니다.

### 이미 있는 캐시 계층

`DataFetcher`에는 점진적 축적을 전제한 캐시가 이미 구현되어 있습니다.

- `datasets/raw/papers/{id}.json` — 논문 개별 저장
- `datasets/raw/mappings.json` — title ↔ id 매핑
- `cache/key_words_cache.json` — 키워드 → id 목록
- `DEFAULT_DATA_FETCHER_ENABLE_CACHE = True`

따라서 **"전량 미러링 먼저"가 아니라 온디맨드로 채워 로컬 코퍼스를 누적**하는 방식이 코드 설계와 일치합니다.

---

## 3. 핵심 설계 판단 — 전문 파싱을 뒤로 미루기

전문 파싱(PDF → Markdown)이 압도적 병목입니다. GPU 파서 기준 논문당 수 초~수십 초로, 1,000편이면 수 시간 규모입니다.

그런데 파이프라인이 각 단계에서 **실제로 읽는 필드**를 따라가 보면 전문이 필요한 시점은 상당히 늦습니다.

| 단계 | 코드 | 실제 사용 필드 |
|---|---|---|
| 리콜 — 임베딩/클러스터링 | `paper_recaller.py:129` `"Title: " + title + "\nAbstract: " + abstract` | `title`, `abstract` |
| 필터 — coarse (벡터) | `paper_filter.py` `Document(text=title + abstract)` | `title`, `abstract` |
| 필터 — fine (LLM 판정) | `paper_filter.py` `load_prompt(..., Abstract=paper["abstract"])` | `abstract` |
| 전처리 — 유형 분류 | `data_cleaner.py` `get_paper_type` | `abstract` |
| **전처리 — AttributeTree** | `data_cleaner.py` `get_attri` | **`md_text` (전문)** |

**결론: 필터를 통과한 150~200편만 전문 파싱하면 됩니다.** 1,000편 전부 파싱 대비 **5~7배 절감**이며, 20개 토픽 재현 시 파싱 대상이 2만 편에서 3~4천 편으로 줄어듭니다.

### 3.1 이 설계를 막고 있는 코드 두 곳

지연 파싱을 적용하려면 아래 두 지점을 손봐야 합니다. 논문 저자들은 DB에 전문이 미리 있었으므로 문제가 되지 않았던 부분입니다.

**(1) 리콜 단계에서 전문 없는 논문을 버림** — `data_cleaner.py` `quick_check()`

```python
def quick_check(self) -> list[dict]:
    papers_with_md = [paper for paper in self.papers if "md_text" in paper]  # ← 전문 없으면 폐기
```

`PaperRecaller._clean_paper_pool()`이 이 함수를 호출하므로, 전문 없이 리콜된 논문은 풀에 남지 못합니다. 지연 파싱을 하려면 이 필터를 제거하고 전문 확보를 필터 이후로 옮겨야 합니다.

**(2) 초록이 짧으면 전문을 참조** — `data_cleaner.py` `complete_abstract()`

```python
if "abstract" in paper and len(paper["abstract"]) > 500:
    continue
match = re.search(pattern, paper["md_text"], re.IGNORECASE)   # ← md_text 없으면 KeyError
```

**arXiv 초록에는 500자 미만이 드물지 않으므로 실제로 터질 수 있는 경로입니다.** `md_text` 부재를 가드하도록 수정이 필요합니다.

두 변경 모두 국소적이며 기존 동작(전문이 있는 경우)을 바꾸지 않습니다.

---

## 4. 구성 요소별 기술 선택

### 4.1 메타데이터 검색 (arXiv)

| 방식 | 장점 | 단점 | 판단 |
|---|---|---|---|
| arXiv API 직접 호출 | 구현 즉시 가능, 항상 최신 | rate limit, 복잡한 질의 제약 | **초기 단계 채택** |
| Kaggle arXiv 메타데이터 덤프 + 로컬 색인 | 오프라인·고속, 논문 구조에 근접 | 월 단위 갱신, 초기 적재 필요 | 트래픽 증가 시 전환 |
| Elasticsearch 구축 | 논문과 동일 구조 | 운영 부담이 규모에 비해 과함 | 불필요 |

로컬 색인이 필요해지는 시점에도 **SQLite FTS5나 DuckDB로 충분합니다.** 대상이 수만~수백만 행이라 ES까지 갈 이유가 없습니다.

### 4.2 비arXiv 커버리지 (Google Scholar 대체)

Google Scholar 크롤링은 ToS 위반 소지와 적극적인 봇 차단으로 **재현 목적에 부적합**합니다. 대체안:

- **OpenAlex** — 무료, 사실상 무제한, 2억 4천만 건 규모. 1순위 권장
- **Semantic Scholar API** — S2ORC 전문 접근 가능, API 키 필요

`from` 필드 값만 유지하면 (`"arxiv"` / `"google"`) 상위 코드는 영향받지 않습니다. `eval/data/ref/`의 기존 데이터와 비교할 때 출처 분포가 달라진다는 점만 기록해 두면 됩니다.

### 4.3 전문 확보 (PDF → Markdown)

**arXiv는 LaTeX 소스를 직접 받을 수 있어 PDF 파싱을 우회할 수 있습니다.** 정확도·속도 모두 파싱보다 유리하므로 1순위 경로로 삼습니다.

| 경로 | 적용 대상 | 비고 |
|---|---|---|
| LaTeX 소스 → Markdown | arXiv 논문 대부분 | 가장 정확·고속. 수식/구조 보존 |
| PDF 파서 (MinerU, marker 등) | 소스 미제공 arXiv, 비arXiv | GPU 필요, 느림 |
| `pymupdf4llm` 등 경량 파서 | 폴백 | 품질 낮음, 최후 수단 |

그림 추출(`image` 필드)도 이 단계에서 함께 처리하면 README 5단계(멀티모달 복구)까지 이어집니다.

### 4.4 BibTeX

`complete_bib()`는 `reference` 필드가 없으면 제목 기반으로 `@article{...}`을 자동 생성하므로 **필수는 아닙니다.** 다만 인용 품질 평가(`eval_citation.py`)의 신뢰도를 위해 arXiv 메타데이터로 제대로 만들어 넣는 편이 좋습니다.

### 4.5 비용 참고

리콜 단계 임베딩은 `EmbedAgent.batch_local_embed()` — **로컬 HuggingFace 모델(`bge-base-en-v1.5`)이라 API 비용이 발생하지 않습니다.** 유료 호출은 fine 필터(초록당 1회)와 AttributeTree 추출(전문당 1회)에 집중됩니다.

---

## 5. 실행 계획

### 5.1 선행 조건 — 평가 지표 먼저

**코퍼스 구축 전에 README 2단계(문헌 관련성 평가 3종)를 먼저 붙이기를 권합니다.** 근거:

- 코퍼스를 만들어도 IoU / Relevance_semantic / Relevance_LLM 이 없으면 "논문만큼 잘 검색되는가"를 판정할 수 없습니다.
- 재료가 이미 있습니다: `eval/data/ref/`(기계 검색 결과 2,419편) + `eval/data/human/`(사람 작성 서베이 22편) → IoU 계산 기반 확보.
- 논문 Table 3의 기준값(SurveyX IoU 0.55 / Relevance_semantic 0.4226 / Relevance_LLM 0.7689)과 직접 대조 가능합니다.

### 5.2 단계

| 단계 | 내용 | 산출물 |
|---|---|---|
| C0 | `quick_check()` / `complete_abstract()` 가드 수정 (3.1절) | 지연 파싱 가능 상태 |
| C1 | arXiv API 기반 `search_on_arxiv()` 구현. 기존 캐시 규약 준수 | 초록 수준 리콜 동작 |
| C2 | OpenAlex 기반 `search_on_google()` 대체 구현 | 비arXiv 커버리지 |
| C3 | 전문 확보 파이프라인 (LaTeX 소스 우선, PDF 파서 폴백) — 필터 통과분만 | `md_text` 채워진 논문 |
| C4 | 20개 토픽 리콜 → 5.1의 지표로 논문 Table 3과 대조 | 검색 품질 수치 |
| C5 | (선택) 그림 추출 추가 → 멀티모달 복구 | `image` 필드 |

### 5.3 인터페이스 계약

`DataFetcher`의 두 메서드 시그니처만 지키면 `PaperRecaller` / `PaperFilter`는 **수정 불필요**합니다.

```python
def search_on_arxiv(self, key_words: str) -> list[dict]:   # 쉼표로 구분된 키워드
def search_on_google(self, key_words: str, page: str, time_s: str = "", time_e: str = "") -> list[dict]:
```

반환 dict 스키마는 [README.md 3절](README.md#3-evaldataref--이미-있는-코퍼스-샘플)에 정리된 형식을 따릅니다. 최소 요구 필드는 `_id`, `title`, `abstract`, `from`이며, `md_text`는 C3에서 채웁니다.

---

## 6. 미결 사항

- **전문 절단 기준**: `MD_TEXT_LENGTH = 20000` 토큰으로 앞부분만 남깁니다. 논문에 절단 전략 언급이 없어, 서론 위주로 잘리는 것이 AttributeTree 품질에 미치는 영향은 미검증입니다.
- **`search_on_arxiv`의 무력화된 필터**: docstring은 "overlap 2 이상"이라 하지만 실제 조건은 `id_counter[_id] >= 1`이라 동작하지 않습니다. C1에서 의도대로 복원할지 현행 유지할지 결정이 필요합니다. 복원하면 리콜 정밀도는 오르고 재현율은 떨어집니다.
- **출처 분포 차이**: 논문/기존 데이터는 arXiv 86% + Google Scholar 14%인데, OpenAlex로 대체하면 분포가 달라져 Table 3 수치와의 직접 비교에 편차 요인이 됩니다.
- **재현 대상 스냅샷**: 논문 데이터 기준일은 2025-02-10입니다. 현재 시점 데이터로 리콜하면 논문 이후 발표된 문헌이 섞여 IoU가 구조적으로 낮게 나옵니다. 날짜 상한 필터를 걸지 결정이 필요합니다 (`search_on_google`에 `time_s`/`time_e` 인자가 이미 존재).
