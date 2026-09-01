# 실험 기록: Edge Computing 서베이 자동 생성 (2026-08-31)

공통 코퍼스 어댑터 + OpenRouter 백본 전환 후 SurveyX 파이프라인의 첫 엔드투엔드 실행 기록.
세미나 발표용 요약 문서이며, 원시 데이터는 `outputs/2026-08-31-1231_edge_/metrics/`(time_monitor.json, token_monitor.json)과 `outputs/credits.log`에 있다.

## 한눈에 보기 (TL;DR)

| 메트릭 | 값 |
|---|---|
| 총 비용 (실측) | **$2.28** (본 실행 $1.94 + Conclusion 복원 재실행 $0.34) |
| 총 소요 시간 | **3시간 7분** (12:31 ~ 15:38, LaTeX 컴파일 7.5초 별도) |
| 분량 | **28페이지**, 105,530자 / 14,495단어 (PDF 본문 기준) |
| 참고문헌 | **199편** 인용 (리콜 1,318편에서 필터링) |
| 총 토큰 | 입력 9.52M / 출력 0.77M |
| 백본 LLM | `meta-llama/llama-3.3-70b-instruct` (OpenRouter) |

원 논문 세팅(gpt-4o)으로 동일 토큰량을 처리했다면 약 $31 — **약 16배 절감**.

## 1. 실험 세팅

| 항목 | 값 |
|---|---|
| 백본 LLM | `meta-llama/llama-3.3-70b-instruct` (OpenRouter, provider `akashml/fp8` 고정) |
| 임베딩 | `BAAI/bge-base-en-v1.5` (로컬 GPU, 비용 $0) |
| 코퍼스 | asg-common-corpus `v0.1-poc`, view `surveyeval-2512` (cutoff 2025-12-31) |
| 입력 | `--title "A Survey on Edge Computing"`, 키워드 6개 (LLM 보충 없음) |
| 병렬도 | `CHAT_AGENT_WORKERS=4` |
| task_id | `2026-08-31-1231_edge_` |

같은 날 12:28의 `2026-08-31-1228_edge_`는 시작 직후 중단된 빈 실행(산출물 없음).

## 2. 문헌 깔때기

리콜 **1,318편** → coarse/fine 필터 **200편** → 전문 확보 **199편**(arXiv fetch 실패 1편) → 정제 후 인용 풀 **199편**

## 3. 소요 시간 — 단계별 분해

총 벽시계 시간 3시간 6분 44초 (2026-08-31 12:31:15 → 15:37:59). 이후 LaTeX 컴파일은 TeX 경로 수정을 거쳐 2026-09-01 00:52에 7.5초 소요.

| 단계 | 소요 | 비고 |
|---|---|---|
| 리콜 (Keyword Expansion) | 2분 02초 | |
| 필터 (coarse + fine) | 27분 | 전문 확보 24분 13초 포함 (200편 순차 arXiv fetch) |
| 정제 + AttributeTree 추출 | 50분 40초 | 199편 전문 처리, 최장 단계 |
| 아웃라인 생성 | 5분 56초 | |
| 본문 생성 | 56분 02초 | 39개 소절 |
| 사후 정제 (RAG 재작성 등) | 44분 38초 | 표 생성 2분 47초 포함 |
| LaTeX 컴파일 | 7.5초 | |

병목은 **정제(AttributeTree) 51분 + 본문 생성 56분**으로 전체의 57%. 전문 확보 24분은 arXiv 순차 다운로드라 병렬화 여지가 있음.

## 4. 비용 — 단계별 분해

실측(`check_credits.py` API 키 사용액 전후 차이): 본 실행 **$1.9363**, Conclusion 복원 재실행 **$0.3444**, 합계 **$2.2807**.

TokenMonitor가 추적한 LLM 콜 합계는 $1.887로, 실측과의 차이(~$0.05)는 재시도·미추적 콜 오버헤드.

| 단계 | 입력 토큰 | 출력 토큰 | 비용 | 비중 |
|---|---:|---:|---:|---:|
| 리콜 | 1.5K | 17 | $0.0002 | 0% |
| 필터 | 165K | 1.6K | $0.0257 | 1% |
| 정제 (AttributeTree) | 6,133K | 396K | $1.1578 | **61%** |
| 아웃라인 생성 | 309K | 39K | $0.0697 | 4% |
| 본문 생성 | 2,520K | 177K | $0.4845 | **26%** |
| RAG 재정제 | 14K | 3K | $0.0038 | 0% |
| 섹션 재작성 | 87K | 135K | $0.0943 | 5% |
| 그림 빌더 (TikZ) | 166K | 8.7K | $0.0302 | 2% |
| 표 생성 | 123K | 4.6K | $0.0212 | 1% |
| **합계** | **9,519K** | **766K** | **$1.887** | |

비용의 87%가 AttributeTree 추출 + 본문 생성 두 단계에 집중. 임베딩을 로컬로 돌려 임베딩 비용은 $0.

## 5. 산출물

최종 PDF: [`outputs/2026-08-31-1231_edge_/survey.pdf`](../outputs/2026-08-31-1231_edge_/survey.pdf) (워터마크판 `survey_wtmk.pdf` 별도)

| 항목 | 값 |
|---|---|
| 페이지 | 28페이지 (204KB) |
| 텍스트 길이 | 105,530자 / 14,495단어 (pdftotext 기준) |
| 구성 | 섹션 8개, 소절 31개 |
| 생성 그림 | TikZ 7개 (구조도 1 + 분류 트리 6) |
| 표 | 0개 — 5개 생성됐으나 중복 콘텐츠 품질 게이트에서 전원 기각 (아래 특이사항) |
| 참고문헌 | 199편 — 저자 175편(88%)·연도·arXiv id 표기, 출판 venue 64편(32%) 표기 |

## 6. 특이사항 (재현 시 참고)

- **llama의 형식 준수력**: JSON 형식 실패로 hint 마운트 누락 10/199편(5%). gpt-4o 대비 형식 준수력 차이의 실측치.
- **표 미포함**: 표 5개가 생성됐으나 중복 콘텐츠 품질 게이트(값 유사도 ≥0.5)에서 전원 기각. llama의 속성 추출이 반복적인 데서 기인한 것으로 버그 아님 (`latex_list_table_builder.py`).
- **Conclusion 통삭제 오폭**: `post_revise()`의 상투어구 필터가 "In conclusion, ..."으로 시작한 결론 본문 전체를 삭제 → 필터가 Conclusion 섹션 내부를 건너뛰도록 수정하고, 결론은 LLM 1콜로 재작성해 복원 (재실행 비용 $0.34).
- **LaTeX 컴파일 실패 → 해결**: PATH 최우선의 MiKTeX(패키지 불완전)로 최초 실패. `.env`의 `SURVEYX_TEX_BIN=/usr/bin`(TeX Live)으로 고정해 해결.
- **참고문헌 보강**: 공통 코퍼스에 BibTeX 필드가 없어 최초 산출물은 제목만 표기 → 어댑터가 arXiv 메타데이터로 완성형 BibTeX을 채우도록 수정(`scripts/rebuild_references.py`). venue는 OpenAlex 미러에서 1회 추출한 lookup(`datasets/venue_lookup.parquet`)으로 조인.
- **429 rate limit 1회**: tenacity 재시도로 흡수 (`CHAT_AGENT_WORKERS=4` 기준).

## 7. 관련 자료

- 상세 실행 로그: `outputs/edge_run.log`, `outputs/logs/`
- 코퍼스 어댑터 설계: [common-corpus-adapter.md](common-corpus-adapter.md)
- 재현 절차: [REPRODUCTION.md](../REPRODUCTION.md)
- README 요약: [README.md §9.1](../README.md)
