# SurveyX 재현 (Reproduction)

이 저장소는 [IAAR-Shanghai/SurveyX](https://github.com/IAAR-Shanghai/SurveyX)의 포크로, **[SurveyX 논문(arXiv:2502.14776)](https://arxiv.org/abs/2502.14776)을 재현하는 것**을 목적으로 합니다.

원본 저장소는 논문의 전체 시스템 중 **오프라인 처리 부분만** 공개한 축소판입니다. 따라서 재현 작업의 실질은 "코드를 새로 짜는 것"이 아니라 **공개되지 않은 데이터 수집 계층을 다시 만들고, 논문에 보고된 수치를 측정할 평가 수단을 갖추는 것**입니다.

- 원본 프로젝트 소개 및 데모: [IAAR-Shanghai/SurveyX README](https://github.com/IAAR-Shanghai/SurveyX/blob/main/README.md)
- 예시 산출물: [`examples/`](examples/) 디렉터리

---

## 1. 논문 파이프라인 개요

![surveyx_frame](assets/SurveyX.png)

논문은 서베이 작성을 두 단계로 나눕니다.

**Preparation Phase (§3.1)** — 문헌 확보와 전처리
1. *References Acquisition*: Keyword Expansion 알고리즘(Algorithm 1)으로 키워드를 넓혀가며 논문을 리콜하고, 2단계 필터링(임베딩 Top-K → LLM 판정)으로 관련성 낮은 문헌을 제거
2. *References Pre-processing*: **AttributeTree** — 논문 유형별(method/benchmark/theory/survey) 템플릿으로 핵심 정보만 구조화 추출. 전문을 그대로 넣는 대신 정보 밀도를 높여 컨텍스트 윈도우를 절약

**Generation Phase (§3.2)** — 생성과 정제
3. *Outline Generation*: **Outline Optimization** — 1차 개요 생성 → 논문별 hint 생성 → 2차 개요 생성 → 중복 제거 → 재구성
4. *Content Generation*: subsection 단위 생성. 이미 쓴 본문을 문맥으로 넘겨 일관성 유지
5. *Post Refinement*: RAG 기반 재작성(인용 정확도·문체 개선) + 표/그림 생성

---

## 2. 제공되는 것 vs. 논문에만 있는 것

재현 계획을 세우려면 이 경계가 가장 중요합니다.

### ✅ 제공됨 — 그대로 실행 가능

| 구성 요소 | 위치 |
|---|---|
| Keyword Expansion 알고리즘 (Algorithm 1) | `paper_recaller.py` — 클러스터링·키워드 생성·선택 로직 전부 |
| 2단계 문헌 필터링 (coarse embedding → fine LLM) | `paper_filter.py` |
| AttributeTree 추출 로직 + 4종 템플릿 | `data_cleaner.py`, `resources/LLM/prompts/preprocessor/attri_tree_for_*.md` |
| Outline Optimization 전 5단계 | `outlines_generator.py` |
| 본문 생성 (subsection 단위, 문맥 전달) | `content_generator.py` |
| RAG 기반 재작성 | `rag_refiner.py` |
| 표·그림 생성 (LaTeX 빌더 일체) | `latex_*_builder.py` |
| 프롬프트 전문 (40여 개) | `resources/LLM/prompts/` |
| LaTeX 템플릿·스타일 | `resources/latex/` |
| 콘텐츠 품질 평가 5종 (Coverage, Structure, Relevance, Synthesis, Critical Analysis) | `eval/eval_content.py` |
| 인용 품질 평가 (Recall, Precision, NLI 기반) | `eval/eval_citation.py` |
| **평가용 참고문헌 코퍼스 (22개 토픽, 2,419편)** | `eval/data/ref/` — [3절](#3-evaldataref--이미-있는-코퍼스-샘플) 참조 |
| 생성 결과 샘플 22편, 사람 작성 서베이 22편 | `eval/data/svx/`, `eval/data/human/` |

### ❌ 논문에 있으나 제공되지 않음

| 논문 내용 | 저장소 상태 | 비고 |
|---|---|---|
| **오프라인 arXiv 데이터베이스 (약 263만 편)** | 없음 | §3.1.1. 데이터 자체가 미공개 |
| **Google Scholar 크롤러 시스템** | `DataFetcher`에 껍데기만 존재 | `CRAWLER_BASE_URL = ""`, `_get_db_authentication()`은 `pass`, `task_submit()`의 `url = f""`. 사내 큐/DB 서버에 붙는 코드 |
| **PDF → Markdown 문서 파싱** | 없음 | 저장소에 파싱 코드가 전무. 그래서 사용자가 `.md`를 직접 만들어 넣어야 함 |
| **멀티모달 문서 파싱 (그림 추출)** | 없음 | `paper["image"]`를 소비하는 코드만 있고 채우는 코드는 없음 |
| **MLLM 기반 그림 검색·삽입** | `FigRetrieveRefiner`는 있으나 비활성 | `post_refiner.py`에서 호출이 주석 처리 + `FIG_RETRIEVE_URL`/`TOKEN` 전부 `""` (사내 API) |
| **문헌 관련성 평가 3종** (IoU, Relevance_semantic, Relevance_LLM) | 없음 | §4.1. 검색 알고리즘 성능을 측정할 수단이 없음 |
| 사람 평가 프로토콜 (Label Studio, 박사과정 6인) | 없음 | 코드화 대상 아님 |
| `resources/dummy_data/` | 없음 | 여러 파일의 `__main__` 테스트가 참조하지만 부재 |
| 로컬 LLM / 로컬 임베딩 엔드포인트 | 자리표시자 | `LOCAL_URL = "LOCAL_URL"` 등 |

> **정리: 빠진 것은 알고리즘이 아니라 데이터와 그 수집 인프라입니다.** `DataFetcher` 한 클래스가 Preparation Phase의 입력 전체를 담당하는데, 이 부분만 사내 인프라 의존으로 제거되어 있습니다. 따라서 재현의 핵심 과제는 **코퍼스 구축**입니다.

---

## 3. `eval/data/ref/` — 이미 있는 코퍼스 샘플

평가용 데이터로 들어 있지만, 실질적으로는 **Preparation Phase의 완성된 출력 샘플**입니다 (153MB, 22개 토픽, 2,419편).

- 출처: arXiv 2,083편 + Google Scholar 336편
- `paper_type` 분포: method 1,541 / benchmark 410 / survey 280 / theory 188
- 필드 충족률: `title`·`abstract`·`bib_name`·`paper_type`·`attri`·`mount_outline` 100%, `md_text` 99%, `image` 13%

파이프라인이 기대하는 논문 dict 스키마:

```jsonc
{
  "from": "arxiv",                    // 출처
  "detail_id": "arXiv:2202.05662",    // 원본 식별자
  "title": "...",
  "abstract": "...",
  "md_text": "# ... ",                // 논문 전문(Markdown). AttributeTree 추출 입력
  "bib_name": "shah2022novelchaos...", // \cite{} 키
  "paper_type": "method",             // method | benchmark | theory | survey
  "attri": { "background": "...", ... },        // AttributeTree
  "mount_outline": [{"section number": "3.3", "key information": "..."}],
  "similarity_score": 0.54,
  "image": null                        // 멀티모달용(대부분 비어 있음)
}
```

**의미**: 크롤러가 없어도 목표 산출 형식의 정답지가 저장소 안에 있습니다. 코퍼스를 새로 구축할 때 이 스키마를 그대로 맞추면 상위 모듈을 수정할 필요가 없고, 구축 전에도 이 데이터로 Generation Phase를 재현·검증할 수 있습니다.

---

## 4. 논문 ↔ 코드 매핑

| 논문 | 코드 | 상태 |
|---|---|---|
| §3.1.1 Keyword Expansion (Algorithm 1) | [`paper_recaller.py`](src/modules/preprocessor/paper_recaller.py) `recall_papers_iterative` | ✅ KMeans `n=|K_pool|+1`, 클러스터별 LLM 키워드 생성, rank 기반 선택, topic 가중치 ×2 |
| §3.1.1 2-step filtration | [`paper_filter.py`](src/modules/preprocessor/paper_filter.py) `coarse_grained_sort` + `fine_grained_sort` | ✅ 임베딩 Top-K(200) → LLM 관련성 판정 |
| §3.1.1 retrieval data source | [`data_fetcher.py`](src/modules/preprocessor/data_fetcher.py) | ❌ **비어 있음 — 유일한 구멍** |
| §3.1.2 AttributeTree | [`data_cleaner.py`](src/modules/preprocessor/data_cleaner.py) `get_paper_type` + `get_attri` | ✅ 논문 Appendix B의 4개 템플릿 그대로 |
| §3.2.1 Outline Optimization | [`outlines_generator.py`](src/models/generator/outlines_generator.py) `run` | ✅ 5단계가 논문과 일치 |
| §3.2.2 Content Generation | [`content_generator.py`](src/models/generator/content_generator.py) `content_fulfill_iter` | ✅ |
| §3.2.3 RAG-based Rewriting | [`rag_refiner.py`](src/modules/post_refine/rag_refiner.py) | ✅ |
| §3.2.3 Figure & Table Generation | [`latex_figure_builder.py`](src/modules/latex_handler/latex_figure_builder.py) 외 | ✅ |
| §3.2.3 MLLM 기반 그림 검색 | [`fig_retrieve_refiner.py`](src/modules/post_refine/fig_retrieve_refiner.py) | ⚠️ 비활성 |
| §4.1 content / citation 평가 | [`eval/eval_content.py`](eval/eval_content.py), [`eval/eval_citation.py`](eval/eval_citation.py) | ✅ |
| §4.1 reference relevance | — | ❌ 미구현 |

---

## 5. 환경 구축

- Python 3.10+
- LaTeX 환경: `sudo apt update && sudo apt install texlive-full`
- `pip install -r requirements.txt`

**⚠️ `requirements.txt`를 그대로 설치하면 실행이 막힙니다. 먼저 아래를 수정하세요.**

| 문제 | 조치 |
|---|---|
| `fitz==0.0.1.dev2`는 동명이인 패키지 | `latex_generator.py`의 `import fitz`는 PyMuPDF를 요구 → `PyMuPDF`로 교체 |
| `llama-index-embeddings-huggingface` 누락 | `EmbedAgent`가 `HuggingFaceEmbedding`을 임포트하므로 추가 |
| `config.py`의 `REMOTE_URL` 기본값이 `https://openai.com/...` | `https://api.openai.com/v1/chat/completions`가 정확 |

LLM 설정은 [`src/configs/config.py`](src/configs/config.py):

```python
REMOTE_URL = "https://api.openai.com/v1/chat/completions"
TOKEN = "sk-xxxx..."
DEFAULT_CHATAGENT_MODEL = "gpt-4o-mini"   # 논문은 전 구간 gpt-4o-2024-08-06 사용
ADVANCED_CHATAGENT_MODEL = "gpt-4o"
DEFAULT_EMBED_ONLINE_MODEL = "BAAI/bge-base-en-v1.5"   # 논문과 동일
```

> 논문은 검색·평가 임베딩에 `bge-base-en-v1.5`, LLM 에이전트는 전 구간 `gpt-4o-2024-08-06`을 사용했습니다. 수치를 비교하려면 `DEFAULT_CHATAGENT_MODEL`도 `gpt-4o`로 맞춰야 합니다(비용 증가).

---

## 6. 실행

실행할 때마다 `outputs/<task_id>/`가 생성됩니다 (예: `outputs/2025-06-18-0935_keyword/`).

```bash
# 오프라인 전체 파이프라인 (사용자가 준비한 .md 참고문헌 사용)
python tasks/offline_run.py \
  --title "Your Survey Title" \
  --key_words "keyword1, keyword2, ..." \
  --ref_path "path/to/your/reference/dir"
```

```bash
# 단계별 실행 (디버깅용)
export task_id="your_task_id"
python tasks/workflow/03_gen_outlines.py --task_id $task_id
python tasks/workflow/04_gen_content.py  --task_id $task_id
python tasks/workflow/05_post_refine.py  --task_id $task_id
python tasks/workflow/06_gen_latex.py    --task_id $task_id
```

`tasks/workflow/01_fetch_data.py`(문헌 수집)와 `full_run.py`는 `DataFetcher`에 의존하므로 **현재는 동작하지 않습니다.**

산출물: `survey.pdf`(최종), `outlines.json`(개요), `latex/`(소스), `tmp/`(중간 파일).

---

## 7. 재현 로드맵

**0단계 — 환경 수정.** 5절의 세 항목 처리.

**1단계 — Generation Phase 재현.** 참고문헌 md 10~20개로 `offline_run.py`를 끝까지 실행해 outline → content → post_refine → LaTeX 전 구간을 검증. 논문 §3.2 전체를 확인하는 셈이고, 프롬프트와 데이터 스키마 감을 잡을 수 있어 이후 작업에 가장 도움이 됩니다.

**2단계 — 평가 수단 확보.** §4.1의 문헌 관련성 3종(IoU, Relevance_semantic, Relevance_LLM)을 구현. `eval/data/ref/`(기계 검색 결과)와 `eval/data/human/`(사람 작성 서베이)이 있으므로 IoU 계산 기반은 갖춰져 있습니다. **3단계보다 먼저 해야** 코퍼스 품질을 측정할 수 있습니다.

**3단계 — 코퍼스 구축 (핵심 과제).** `DataFetcher`의 `search_on_arxiv(key_words) -> list[dict]`와 `search_on_google(...) -> list[dict]` 시그니처만 지키면 상위 `PaperRecaller`/`PaperFilter`는 수정 불필요. 반환 dict는 3절 스키마를 따르면 되고, 그중 `md_text`(전문)가 AttributeTree 입력이라 최종 품질을 좌우합니다. 논문의 사내 인프라 대신 arXiv API + OpenAlex 조합이 현실적이며, 전문은 PDF → Markdown 변환 파이프라인이 별도로 필요합니다.

> 📄 **상세 설계는 [REPRODUCTION.md](REPRODUCTION.md)에 별도로 정리했습니다** — 논문 인프라 역설계(Elasticsearch + MongoDB 크롤러 큐), 규모 재해석(263만 편이 필수가 아닌 이유), 전문 파싱을 필터 이후로 미루는 설계와 그에 필요한 코드 수정 지점, 기술 선택 비교, 실행 단계 C0~C5.

**4단계 — 전체 재현 실험.** 논문 Table 4의 20개 토픽으로 서베이를 생성하고 Table 1(콘텐츠·인용 품질), Table 3(문헌 관련성)과 대조. Table 2의 ablation은 대부분 설정값으로 재현 가능합니다(`DEFAULT_ITERATION_LIMIT=0`으로 keyword expansion 제거, `get_attri` 결과 대신 `md_text` 직접 투입 등).

**5단계 (선택) — 멀티모달 복구.** `post_refiner.py`의 주석 처리된 `fig_retrieve_refiner.run(...)`을 되살리고 `FIG_RETRIEVE_URL` 계열을 자체 파이프라인으로 대체.

---

## 8. 재현 시 주의 — 확인된 논문·코드 불일치

- **`search_on_arxiv`의 무력화된 필터**: docstring은 "overlap이 2 이상인 결과를 반환"이라 하지만 실제 조건은 `id_counter[_id] >= 1`이라 필터가 동작하지 않습니다. 3단계에서 이 함수를 다시 쓸 때 의도대로 고칠지 결정이 필요합니다.
- **키워드 선택 기준**: 논문 본문 산문("평균 거리는 최소, 최대 거리는 최대")과 논문 수식 (1)(2)(3)이 서로 반대인데, 코드는 **수식**을 따릅니다(평균 거리가 큰 쪽 + 최대 거리가 작은 쪽 선호). 재현 시 수식 기준이 맞다고 보면 됩니다.
- **파라미터 차이**: 논문 θ=1000 vs 코드 `DEFAULT_PAPER_POOL_LIMIT=1024`, 코드에는 논문에 없는 `DEFAULT_ITERATION_LIMIT=3` 상한이 있습니다.
- **본문 길이 제한**: `MD_TEXT_LENGTH=20000` 토큰으로 전문을 잘라 AttributeTree에 넣습니다.

---

## 9. 실험 결과

### 9.1 Edge Computing 서베이 1편 생성 (2026-08-31)

공통 코퍼스 어댑터 + OpenRouter 백본 전환 후 첫 엔드투엔드 실행 기록.

**세팅**

| 항목 | 값 |
|---|---|
| 백본 LLM | `meta-llama/llama-3.3-70b-instruct` (OpenRouter, provider `akashml/fp8` 고정) |
| 임베딩 | `BAAI/bge-base-en-v1.5` (로컬, 비용 $0) |
| 코퍼스 | asg-common-corpus `v0.1-poc`, view `surveyeval-2512` (cutoff 2025-12-31) |
| 입력 | `--title "A Survey on Edge Computing"`, 키워드 6개 (LLM 보충 없음) |
| task_id | `2026-08-31-1231_edge_` |

**문헌 깔때기**: 리콜 1,318편 → coarse/fine 필터 200편 → 전문 확보 199편(실패 1) → 정제 후 199편 인용 풀

**소요 시간** — 총 **3시간 7분** (12:31~15:38, LaTeX 컴파일 제외)

| 단계 | 소요 |
|---|---|
| 리콜 (Keyword Expansion) | 2분 |
| 필터 (coarse+fine) | 3분 |
| 전문 확보 (arXiv fetch, 200편 순차) | 24분 |
| 정제 + AttributeTree (199편) | 51분 |
| 아웃라인 생성 | 6분 |
| 본문 생성 (39개 소절) | 56분 |
| 사후 정제 (RAG 재작성 등) + 표 생성 | 45분 |

**비용** — **실측 $1.94** (`check_credits.py` 전후 차이. TokenMonitor 토큰 합계 기준 추정 $2.30)

- 총 토큰: 입력 9.52M / 출력 0.77M
- 지배 구간: AttributeTree 추출(입력 6.13M, 64%) > 본문 생성(2.52M)
- 참고: 원 논문 세팅(gpt-4o)이었다면 동일 토큰량에 약 $31 — 약 16배 절감

**산출물** — [`outputs/2026-08-31-1231_edge_/survey.pdf`](outputs/2026-08-31-1231_edge_/survey.pdf)

| 항목 | 값 |
|---|---|
| 분량 | 27페이지, 103,302자 (14,188단어) |
| 생성 그림 | TikZ 7개 (구조도 1 + 분류 트리 6) |
| 참고문헌 | 199편 — 저자 175편(88%)·연도·arXiv id, 출판 venue 64편(32%, 예: IEEE IoT Journal) 표기. 나머지는 실제 preprint. (`scripts/rebuild_references.py`로 보강 후 재컴파일) |

**특이사항 (재현 시 참고)**

- llama의 JSON 형식 실패로 hint 마운트 누락 10/199편(5%) — gpt-4o 대비 형식 준수력 차이의 실측치
- 429 rate limit 1회 (tenacity 재시도로 흡수, `CHAT_AGENT_WORKERS=4` 기준)
- 표 미포함의 원인: 표 자체는 5개 생성됐으나 **중복 콘텐츠 품질 게이트(값 유사도 ≥0.5)에서 전원 기각** — llama의 속성 추출이 반복적인 데서 기인 (버그 아님, `latex_list_table_builder.py`)
- LaTeX 컴파일은 PATH 최우선의 MiKTeX(패키지 불완전)로 최초 실패 → `.env`의 `SURVEYX_TEX_BIN=/usr/bin`(TeX Live)으로 고정해 해결
- 최초 산출물의 참고문헌이 제목만 있었던 원인: 공통 코퍼스가 `reference`(BibTeX) 필드를 제공하지 않아 `complete_bib()` 폴백 동작 → 어댑터가 arXiv 메타데이터(+로컬 스냅샷 저자 조인)로 완성형 BibTeX을 채우도록 수정
- 출판 venue 표기: OpenAlex 미러의 works_locations(6.1억 행)에서 코퍼스 947K편 중 256,760편(27%)의 venue를 `scripts/build_venue_lookup.py`로 1회 추출(`datasets/venue_lookup.parquet`, 3.1MB) → 어댑터가 검색 시 즉시 조인. lookup이 없으면 "arXiv preprint" 폴백

---

## 참고

원 논문:

```bibtex
@misc{liang2025surveyxacademicsurveyautomation,
      title={SurveyX: Academic Survey Automation via Large Language Models}, 
      author={Xun Liang and Jiawei Yang and Yezhaohui Wang and Chen Tang and Zifan Zheng and Shichao Song and Zehao Lin and Yebin Yang and Simin Niu and Hanyu Wang and Bo Tang and Feiyu Xiong and Keming Mao and Zhiyu li},
      year={2025},
      eprint={2502.14776},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2502.14776}, 
}
```

- 원본 저장소: [IAAR-Shanghai/SurveyX](https://github.com/IAAR-Shanghai/SurveyX)
- 논문 전문: [SurveyX.pdf](SurveyX.pdf)

생성된 서베이는 연구 보조 결과물이며 학술 기준 준수를 보장하지 않습니다. 내용의 정확성은 반드시 직접 검증해야 합니다.
