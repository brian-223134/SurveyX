# KISTI 파일럿 1편 — physical-adversarial-attacks (2026-09-08)

KISTI corpus(view `kisti-2512`) + 디코딩 프로파일(temperature 0.6 · max_tokens 8192 · 잘림 재요청)로 SurveyX를 처음 끝까지 돌린 기록. 목적은 ① plain text 원문에서 파이프라인이 도는지, ② DOI id가 어디서 깨지는지, ③ 편당 시간·비용·구조·recall의 실측. 수치는 `outputs/2026-09-08-0536_Visua/run.json`(커밋됨)과 `metrics/`에서 가져왔다. 실행 조건·절차의 정본은 [../kisti-run.md](../kisti-run.md).

## 0. 한눈에

| 항목 | 값 | 8/31 edge (bench-2512, 참고) |
|---|---|---|
| topic | Visual Adversarial Attacks and Defenses in the Physical World (sec #3, GT CSUR 10.1145/3793659, ceiling 68%) | A Survey on Edge Computing |
| 소요 | **151.7분** (05:36 → 08:08) | 186분 |
| 비용 | TokenMonitor **$1.43** (실측 키 차분 $2.66은 귀속 불가, §3) | $1.89 (실측 $2.28) |
| 문헌 깔때기 | 리콜 1,003 → coarse 200 → fine 196 → 원문 196/196 | 1,318 → 200 → 199 |
| 구조 | 6섹션 / 22소절 / 5,001단어(tex) / 16쪽 | 8 / 31 / 8,928 / 28쪽 |
| refs | **인용 69** (arXiv 35 / DOI 34), bib 전편 196 | 인용 156, bib 199 |
| recall / precision | **3.4% / 7.2%** (5/149, 5/69) | GT 없음 |
| 누수 | 0 (제외 키 38개, GT 제목) | 0 |
| 잘림 | 폐기 0 / 채택 0 | (가드 없음) |
| 429 | 59 (+503 1건), 모두 재시도로 흡수 | 4 |

## 1. 실행 조건

- 코드: SurveyX `accc2ac` (+ 이 기록과 함께 커밋한 `collect_run.py`의 인용 기준 수정), adapter `kisti_data` `b92e60b`, view manifest sha `eb569600…`.
- `.env`: `SURVEYX_DATA_SOURCE=kisti`, `SURVEYX_TEMPERATURE=0.6`, `SURVEYX_MAX_TOKENS=8192`, `SURVEYX_RETRY_TRUNCATED=true`(10회), provider `akashml/fp8`, workers 4, `CUDA_VISIBLE_DEVICES=4`.
- 명령: `scripts/run_kisti.py --slug physical-adversarial-attacks` → `tasks/full_run.py --title "<Topic>" --key_words "<Topic>"`.
- **첫 시도(05:28)는 7분 만에 중단**: `save_papers`가 DOI id의 `/`를 경로로 만들어 DOI 논문 84/150편이 AttributeTree에 들어가지 않았다(`outputs/aborted-doi-path-bug-2026-09-08-0528_Visua/`, TM $0.089). `safe_filename()`으로 고친 뒤(`16a2317`) 05:36 재실행이 이 기록이다.

## 2. 단계별 시간·비용

| 단계 | 소요 | TM 비용 | 비중 | 비고 |
|---|---:|---:|---:|---|
| 리콜 | 1.7분 | $0.001 | 0% | ILIKE, 키워드 확장 18회 |
| 전문 확보 | **0.1분** | — | — | body_store 즉시 조회. 8/31은 24분 |
| 필터 (coarse+fine) | 3.1분 | $0.027 | 2% | 429 대부분 여기서 |
| 정제 + AttributeTree | **66.6분** | **$0.998** | **70%** | 3패스, §4 |
| outline | 5.7분 | $0.054 | 4% | |
| 본문 생성 | 65.4분 | $0.318 | 22% | draft 127회 / 22소절 |
| 사후 정제 (rewrite·그림) | 8.8분 | $0.030 | 2% | 8/31은 44분 |
| 표·컴파일 | 0.2분 | $0.001 | 0% | 표 0개 채택 |
| 합계 | 151.7분 | $1.428 | | 입력 6.90M · 출력 0.66M 토큰 |

## 3. 비용 실측의 한계

키 사용액 차분은 $2.66이지만 **같은 OpenRouter 키로 SurveyForge 파일럿이 07:04부터 동시에 돌았다**(`SurveyForge/eval_out/pilot_physical-adv…`). 8/31 단독 실행에서 TM과 실측의 차이가 $0.05였으므로 SurveyX 몫은 약 $1.5로 본다. **다음 실행부터는 키를 agent별로 분리하거나 동시 실행을 피해야** `cost_measured_usd`가 의미를 가진다.

## 4. 파일럿 질문에 대한 답

### 4.1 plain text 원문 — 동작한다

body_store 원문(median 34K자)으로 DataCleaner의 abstract 정규식, 논문 유형 분류(method 158 · survey 25 · theory 7 · benchmark 6), AttributeTree 프롬프트가 모두 돌았다. 전문 확보가 24분에서 3초로 줄어 편당 시간이 35분 짧아졌다.

### 4.2 AttributeTree JSON 실패 — llama 고유, plain text 탓이 아님

| | 8/31 edge (arXiv markdown) | 파일럿 (KISTI plain text) |
|---|---:|---:|
| 논문 | 199 | 196 |
| attri 호출 | 479 (2.4/편) | 524 (2.67/편) |
| JSON 파싱 실패 | 428 | 328 (`Expecting ',' delimiter` 325 · invalid escape 3) |
| 3패스 후 attri 보유 | 73 (37%) | **41 (21%)** |
| outline 매핑 | 194/199 | 196/196 |

DataCleaner는 파싱 실패를 최대 3패스 재요청하고, 남은 논문은 attri 없이 유지한다(outline 매핑은 title·abstract로 되므로 196편 전부 매핑됨). 실패는 llama가 만든 JSON의 문법 오류라 원문 형식과 무관하다. **두 실행 모두 논문 과반이 속성 트리 없이 본문 생성에 들어간다**는 것은 llama × SurveyX의 속성으로 기록한다. json_repair 같은 복구를 넣으면 SurveyX 설계에 가까워지지만 agent 코드 변경이라 별도 결정 사항(§6).

### 4.3 DOI id — 파일명 하나가 깨졌고 나머지는 통과

`save_papers` 외에 DOI id에서 깨진 곳은 없었다. BibTeX(`doi`·`doi.org`), 인용 키(`doi10_1145_…`), 매칭 키(`collect_run.py`) 모두 정상. 인용된 69편 중 DOI 34편.

## 5. 결과 해석

- **recall 3.4%는 인용 수 69에 갇힌 값이다.** 검색 풀(bib 196편)에는 GT in_view 149편 중 **25편(16.8%)**이 들어왔지만 writer가 그중 5편만 인용했다. 풀 기준 16.8%는 AutoSurvey 같은 topic의 recall(8.1~13.4%, refs 156~240)보다 높다. SurveyX는 "적게, 풀 안에서 골라" 인용하는 agent이고, 결과표에는 refs 수를 공변량으로 반드시 병기한다(kisti-run.md §5).
- **분량이 8/31보다 작다.** 22소절·5,001단어·16쪽. 8/31(31소절·8,928단어·28쪽)과 topic·corpus가 달라 직접 비교는 안 되지만, 25편 배치에서 분량 분포를 볼 항목이다.
- **draft 재요청 5.77회/소절**(127/22, 거부율 83%). 8/31의 4.1회보다 높다. temperature 0.6에서 markdown 혼입이 늘었을 가능성이 있으나 n=1. 무한루프는 없었다.
- **잘림 0.** 8192 가드에 걸린 호출이 한 건도 없어 "정상 출력에 영향 0"이 실측으로 확인됐다.
- arXiv 논문의 인용률(35/78 = 45%)이 DOI 논문(34/118 = 29%)보다 높다. 원인 미상(주제 적합도일 수 있음).

## 6. 남은 결정·다음 단계

1. **AttributeTree JSON 복구를 넣을지** — 넣지 않으면 llama에서 SurveyX의 핵심 장치가 논문 21~37%에만 작동한 채 벤치마크를 돈다. 넣으면 원 코드 변경(파싱부 1곳). 사용자 결정 대기.
2. **키 분리** — 실측 비용을 쓰려면 agent별 키 또는 순차 실행.
3. **예산** — 편당 TM $1.43 · 152분 → 25편 ≈ **$36 · 63시간**(429 재시도 포함). 키 잔여 $2.57(08:08 기준)이라 한도 상향 없이는 배치 불가.
4. 25편 본배치는 위 1·3이 정리된 뒤 `scripts/run_kisti.py --all --skip-done`.
