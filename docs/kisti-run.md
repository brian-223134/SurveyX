# KISTI corpus 실행 — 디코딩 프로파일·편당 기록 (2026-09-08 기준)

SurveyX 쪽 **현행 정본**이다. corpus·adapter·topic·평가 규약의 정본은 `kisti_data/docs/asg/AGENT-HANDOFF.md`(4 agent 공통)와 `kisti_data/docs/asg/surveyx.md`(SurveyX 설계)이고, 이 문서는 그 조건을 SurveyX 코드에 어떻게 맞췄는지와 실행·기록 절차를 적는다. 결정이 바뀌면 §7 결정 로그부터 고친다.

## 0. 한눈에

| 항목 | 값 |
|---|---|
| 목표 | 4 agent(AutoSurvey · SurveyForge · SurveyX · LLM×MapReduce-V2)를 같은 corpus·백본·topic 25편으로 돌려 GT 참고문헌 대비 recall·precision 비교 |
| corpus | KISTI Science Data Lake 파생 스토어 → view `kisti-2512` 1,651,701편. asg-common-corpus(bench-2512)는 2026-09-07부로 미사용 |
| 데이터 소스 | `.env` `SURVEYX_DATA_SOURCE=kisti` → `KistiFetcher`(view parquet ILIKE + body_store 원문 + authors/venue BibTeX). 스모크 통과(2026-09-08: 검색 1,912편, 원문 2편, provenance 출력) |
| 백본 | `meta-llama/llama-3.3-70b-instruct` @ OpenRouter, provider 핀 `akashml/fp8`, fallback 없음 |
| 디코딩 프로파일 | **temperature 0.6(전 호출) · max_tokens 8192 · 잘림 재요청 최대 10회** — `.env` 4줄, §3 |
| 출력 분량 | 통제하지 않는다. SurveyX 기본값(섹션·소절 수, 단어 수, refs 수는 agent 속성으로 기록) |
| 실행 | `scripts/run_kisti.py --slug <slug>` 또는 `--all` (§4). 파이프라인 코드는 `tasks/full_run.py` 그대로 |
| 기록 | 편당 `outputs/<task_id>/run.json` (`scripts/collect_run.py`, §5). `.gitignore` 예외로 커밋에 들어간다 |
| 진행 | 25편 본배치 **미착수**. 1편 파일럿(plain text 원문의 AttributeTree 확인) 선행 |

## 1. 데이터 소스 — KISTI adapter

- 분기: `src/modules/preprocessor/data_fetcher.py::get_data_fetcher()` (`5b19afe`). `KISTI_ADAPTER_DIR`(기본 `/data2/chanjoong/kisti_data/adapter`)를 `sys.path`에 넣고 `surveyx.kisti_fetcher.KistiFetcher`를 쓴다. surveyx env(duckdb 1.3.2)에서 parquet·sqlite만 읽으므로 subprocess 위임이 없다.
- id는 불투명 키다(arXiv base id 또는 DOI 문자열). BibTeX는 arXiv면 `eprint`/`arxiv.org/abs`, DOI면 `doi`/`doi.org`. `collect_run.py`는 이 두 필드에서 평가용 매칭 키(`doi` ∨ `10.48550/arxiv.<base id>`)를 만든다.
- **DOI id 함정(수정됨, 2026-09-08)**: `save_papers`가 `_id`를 파일명으로 그대로 써서 DOI의 `/`가 하위 디렉터리를 만들었고, `DataCleaner.load_json_dir`은 최상위 `.json`만 읽어 첫 파일럿에서 필터 통과 150편 중 **DOI 논문 84편이 통째로 사라졌다**(arXiv 66편만 AttributeTree 진입). `safe_filename()`으로 파일명만 치환한다(`_id` 값은 그대로, 파일명은 목록으로만 읽힘). 중단 실행은 `outputs/aborted-doi-path-bug-2026-09-08-0528_Visua/`에 보관. 회귀 테스트 `tests/test_preprocessor_utils.py`.
- 원문은 s2orc/pmc 추출 plain text다. AttributeTree 프롬프트가 markdown 구조를 기대하는지는 **1편 파일럿에서 확인**할 것(미확인).
- 스모크: `SURVEYX_DATA_SOURCE=kisti PYTHONPATH=/data2/chanjoong/kisti_data/adapter $PY -m surveyx.kisti_fetcher`

## 2. 8/31 실측 — 프로파일 결정의 근거

edge computing 1편(bench-2512, 같은 백본·provider 핀, temperature 원 설정 0.5/0.3, max_tokens 미전송). 요청 기록 1,907건을 프롬프트 템플릿별로 다시 센 것(`collect_run.py`와 같은 방식).

| 항목 | 값 | 의미 |
|---|---|---|
| 요청 성공 | 1,903 / 1,907 (실패 4건 모두 429) | HTTP 재시도(tenacity 30회·지수 백오프)로 충분. 동시성 4 유지 |
| 출력 토큰 합계 | 0.77M | 루프 오염 없음. draft 호출 평균 ≈ 1.2K 토큰 |
| 섹션 단위 호출 최대 입력 | 2,937단어 (compress·rewrite) | ≈ 4~5K 토큰 → **8192 가드에 정상 출력이 걸리지 않는다** |
| draft 호출 / 소절 | 127 / 31 = **4.1회** | `content_generator`의 `contains_markdown` 재요청 루프. llama가 굵게·목록 표기를 섞어 약 3/4이 거부됨 |
| 구조 (tex 기준) | 8섹션 / 31소절 / 8,928단어 / refs 199(인용 156) / 28쪽 | `collect_run.py` 계산(AutoSurvey `check_survey.measure`와 동일) |
| 비용·시간 | TokenMonitor $1.89 (실측 $2.28) / 186분 | 전문 확보 24분은 KISTI에서 사라짐 |

읽는 법: (a) SurveyX 프롬프트는 temperature 0.5에서 반복 루프를 일으키지 않았다(AutoSurvey가 temp 0에서 겪은 128K 토큰 호출 없음). (b) 대신 형식 거부 재요청이 소절당 3회 남짓 있다. 이것은 SurveyX 고유 동작(형식 기준 best-of-n)이고 인용 선택에 편향을 주지 않으므로 **코드를 두고 agent 속성으로 기록**한다. (c) temperature 0이면 같은 출력이 반복돼 이 루프가 무한이 된다 → temp 0 금지의 SurveyX 쪽 근거.

## 3. 디코딩 프로파일 — 무엇을 왜

`.env`(정본은 `.env.example`):

```
SURVEYX_TEMPERATURE=0.6
SURVEYX_MAX_TOKENS=8192
SURVEYX_RETRY_TRUNCATED=true
SURVEYX_MAX_TRUNCATED_RETRY=10
```

| 값 | 코드 | 근거 |
|---|---|---|
| temperature **0.6** 전 호출 | `ChatAgent.remote_chat`이 호출부 값(기본 0.5, outline 1차 0.3)을 덮어쓴다 (`config.CHAT_TEMPERATURE_OVERRIDE`) | 4 agent 공통 조건. AutoSurvey도 원 설정 1.0을 버리고 0.6으로 갔으므로 SurveyX만 원 설정을 두면 원칙이 어긋난다. 0.5→0.6의 recall 효과는 run-to-run 오차(±1.7%p) 아래라 결과는 바뀌지 않고, 각주 하나를 없애는 값이다. 미설정이면 원 설정 유지 |
| max_tokens **8192** | payload `max_tokens` (`config.CHAT_MAX_TOKENS`) | "원래 없었다"는 정확하지 않다 — 원 SurveyX의 gpt-4o(-mini)는 OpenAI API가 모델 상한 16,384에서 잘랐고, llama@OpenRouter로 오면서 그 암묵 상한이 사라졌다(AutoSurvey에서 128K 토큰 호출 실측). 8192는 그 상한의 복원이며 §2대로 정상 출력에는 영향 0. 없이 가면 HTTP 타임아웃 900초가 대신 가드 노릇을 하는데, 15분 안에 끝나는 1~2만 토큰 루프는 그대로 본문에 들어가고 타임아웃 호출의 비용도 그대로 나간다 |
| 잘림 재요청 최대 10회 | `finish_reason == "length"`면 버리고 재요청, 소진 시 마지막 응답 채택 (`CHAT_RETRY_TRUNCATED`, `CHAT_MAX_TRUNCATED_RETRY`) | 프로토콜 통일(AutoSurvey `baa46cc`와 같은 규칙). §2대로 SurveyX에서 발동 확률은 낮고 정상 호출엔 영향 0. 폐기한 응답의 토큰도 TokenMonitor에 더한다(과금되므로) |
| `contains_markdown` 루프 | **손대지 않음** (`content_generator.py:192`, `:370`, 상한 없음) | temperature 0.6에서 매 시도가 독립 표본이라 20회 연속 거부 확률 ≈ 0.1% 미만. 상한을 두면 그 극소수 소절에서 markdown이 LaTeX로 흘러가 `#` 때문에 컴파일이 깨질 수 있어 손해. 시도 횟수는 요청 기록으로 사후 집계(§5 `draft_calls_per_subsection`) |
| top_p 등 | 건드리지 않음 | 손잡이 1개 |

요청 기록(`outputs/tmp/request_stats.txt`, `ChatAgent.update_record`)의 status: **1** 정상 · **0** HTTP 오류(재시도됨) · **2** 잘림 폐기 · **3** 잘림 채택(재요청 소진). 파일이 새로 만들어질 때 첫 기록이 두 번 적히던 원 코드 버그는 고쳤다(편마다 파일을 회전시키므로 첫 요청이 항상 2회로 세어지는 문제였다).

가드 실측(2026-09-08, `SURVEYX_MAX_TOKENS=20`으로 강제): OpenRouter 응답의 `finish_reason`이 `length`로 오고, 재요청 2회 후 채택, status 2·2·3으로 기록됨. 재요청 off면 status 3 한 건.

한계: HTTP 오류로 tenacity가 함수를 다시 시작하면 잘림 재요청 카운터가 0으로 돌아간다(최악 10×30이 아니라 실제로는 429 몇 건이라 무시 가능).

## 4. 실행 절차 — `scripts/run_kisti.py`

파이프라인 코드는 부르기만 한다. 스크립트가 하는 일은 실행 전후의 기록이다.

```bash
PY=/data2/chanjoong/miniforge3/envs/surveyx/bin/python
$PY scripts/run_kisti.py --slug instruction-tuning-llms            # 1편
$PY scripts/run_kisti.py --title "<Topic>"                          # topics.kisti.jsonl 밖의 topic도 가능 (GT 없음)
nohup $PY scripts/run_kisti.py --all --skip-done > outputs/kisti_batch.log 2>&1 &   # 25편
$PY scripts/run_kisti.py --all --dry-run                            # 명령만 확인
```

1. 전제 확인: `.env`의 `SURVEYX_DATA_SOURCE=kisti`, view 디렉터리, 디코딩 프로파일 3키(없으면 경고만).
2. `outputs/tmp/request_stats.txt`(전역 누적)를 `.bak`으로 회전 → 이번 편의 기록만 남게 한다.
3. 실행 전 스냅샷: `.env`(키 마스킹), OpenRouter 키 사용액(`scripts/check_credits.py`, `outputs/credits.log`에도 append).
4. `tasks/full_run.py --title "<Topic>" --key_words "<Topic>"` (topic 문자열은 `topics.kisti.jsonl`의 `title` 그대로, 양쪽에). 로그 `outputs/logs/kisti_<slug>_<ts>.log`.
5. 실행 후: `outputs/<task_id>/`를 title로 찾아 `metrics/`에 `env.snapshot.json` · `credits.json`(전후 차분 = 실측 비용) · `run_args.json` · `request_stats.txt` 저장 → `collect_run.py`로 `run.json`.

실패 시: task 디렉터리가 있으면 `run_args.json.status=failed`로 남기고 `run.json`도 만든다. 없으면 요청 기록만 `request_stats.failed.<slug>.<ts>.txt`로 보존. `--skip-done`은 `run.json.status == ok`이고 PDF 쪽수가 있는 topic만 건너뛴다.

## 5. 편당 기록 — `outputs/<task_id>/run.json`

`scripts/collect_run.py --task_id <task_id>` (실행 직후 자동). 과거 실행은 `--request_stats <경로>`로. 집계 표는 `--table`.

| 필드 | 출처 | 비고 |
|---|---|---|
| `topic` `key_words_expanded` `args` `status` `started_at` `log_path` | `tmp_config.json` · `metrics/run_args.json` | |
| `model` `provider_pin` `temperature` `max_tokens` `retry_truncated` `data_source` `view` `fulltext_limit` | `metrics/env.snapshot.json` | 스냅샷이 없으면 **null** — 현재 `.env`로 대체하지 않는다(그 실행의 조건이 아니므로). `env_source`에 표시 |
| `view_manifest_sha256` `package` `git.{surveyx,kisti_data}` | view manifest 파일 sha256 · adapter `PACKAGE_VERSION` · 두 저장소 HEAD/dirty | |
| `stages` `cost_total_usd` `stage_durations_sec` `duration_sec` | `token_monitor.json` · `time_monitor.json` | 소요는 첫 단계 시작 → 마지막 단계 끝(LaTeX 컴파일 제외) |
| `cost_measured_usd` | `metrics/credits.json` | OpenRouter 키 사용액 전후 차분 |
| `requests` `requests_by_template` `truncated_calls` `truncation_retries` `draft_calls_per_subsection` | `metrics/request_stats.txt` | status별 수, 429 수, 템플릿별 호출 수(요청 prefix 200자 매칭), draft = `fulfill_content(_iteratively)` |
| `structure` | `latex/survey.tex` · `references.bib` · `survey.pdf` | sections/subsections/words(AutoSurvey `check_survey.measure`와 같은 계산), references(bib 항목)·references_cited(본문 `\cite` 유니크)·citation_runs·pdf_pages |
| `refs.{arxiv,doi,other,match_keys}` | `references.bib` | 매칭 키 = `doi` 소문자 ∨ `10.48550/arxiv.<base id>` |
| `gt` `score` | `kisti_data/data/topics.kisti.jsonl` · `candidates/gap_to_80_refs.jsonl`(`tier == in_view`) | recall = 적중/분모(in_view), precision = 적중/identifiable refs. topic이 25편 밖이면 null |
| `leak` | view `exclude_keys.txt` 38키 · GT 제목 | 키가 refs 매칭 키·본문/bib 원문에 0회, GT 제목이 bib title에 0회 → `clean: true`. 제목 검사는 bib에만(topic 문자열이 GT 제목에서 왔으므로 본문엔 당연히 나온다) |

AutoSurvey `run.json`과 겹치는 키(`topic` `args` `model` `provider_pin` `stages` `cost_total_usd` `truncated_calls` `truncation_retries` `structure` `duration_sec`)는 이름을 맞췄다.

## 5.1 테스트 — `tests/`

API 호출·파이프라인 실행 없이 mock 으로 위 동작을 고정한다(pytest 없이 표준 unittest).

```bash
/data2/chanjoong/miniforge3/envs/surveyx/bin/python -m unittest discover -s tests -v
```

| 파일 | 검증 |
|---|---|
| `tests/test_chat_agent.py` | temperature 오버라이드(호출부 0.3 → 0.6, batch 포함), max_tokens 전송/미전송, 잘림 폐기→재요청→정상(status 2·2·1), 소진 시 채택(status 3), 재요청 off, 폐기 응답 토큰 가산, HTTP 오류 status 0, 기록 파일 첫 줄 중복 없음 |
| `tests/test_collect_run.py` | 구조·refs id 유형·매칭 키(버전 제거·소문자), in_view 분모의 recall/precision, 누수(twin id·GT 제목) 검출과 clean, 요청 기록(status·429·템플릿 매칭·draft/소절), env 스냅샷 부재 시 null, `--table` |
| `tests/test_run_kisti.py` | 요청 기록 회전, task 디렉터리 탐색, `--skip-done` 판정, 크레딧 파싱, run_topic 이 metrics 4종과 run.json 을 남김(성공·실패·task 디렉터리 없음) |

## 6. 예산·주의

- 편당 예상 약 2.5h(8/31의 3h07m에서 전문 확보 24분 제외) · $2.3 실측 기준 → 25편 ≈ **60h · $57**. OpenRouter 키 잔여는 09-03 기준 $7.6 — **키 한도 상향 없이는 배치 불가**.
- 동시성은 `CHAT_AGENT_WORKERS=4` 유지. akashml 429는 tenacity가 흡수한다.
- plain text 원문 파일럿(§1) 전에는 배치를 시작하지 않는다.
- 결과표에는 topic ceiling·run-to-run 오차(±1.7%p 잠정)·refs 수를 병기하고, corpus가 다른 과거 실험(bench-2512 edge/instruction tuning)과 같은 표에 놓지 않는다.

## 7. 결정 로그

| 날짜 | 결정 | 근거 |
|---|---|---|
| 09-07 | `SURVEYX_DATA_SOURCE=kisti` 분기 | `5b19afe`, AGENT-HANDOFF §3 |
| 09-08 | temperature 0.6 전역 오버라이드(outline 0.3 포함) | §3. 4 agent 공통 조건, 미설정 시 원 설정 |
| 09-08 | max_tokens 8192 + 잘림 재요청 10회 | §3. OpenAI 시절 암묵 상한의 복원, 정상 출력 영향 0 |
| 09-08 | `contains_markdown` 루프 무변경, 사후 집계 | §2·§3. 소절당 4.1회 실측, temp 0.6에서 자기 제한 |
| 09-08 | 편당 run.json(`collect_run.py`)·runner(`run_kisti.py`), 파이프라인 코드 무변경 | §4·§5 |
| 09-08 | `.env` 데이터 소스 kisti로 전환, 스모크 통과 | §1 |
| 09-08 | `save_papers` 파일명 치환(DOI `/`) — 첫 파일럿 중단·재실행 | §1. 파이프라인 코드 변경이지만 동작 변화 없는 호환 수정 |
| 09-08 | mock 단위 테스트 `tests/` 34건 | §5.1 |

## 8. 관련 문서

- 4 agent 공통: `kisti_data/docs/asg/AGENT-HANDOFF.md` · `kisti_data/docs/asg/surveyx.md` · `kisti_data/adapter/surveyx/README.md`
- AutoSurvey 쪽 현행 방향·실측: `AutoSurvey/docs/direction-2026-09.md`
- 이전 단계(기록): `docs/common-corpus-adapter.md` · `docs/experiments/edge-computing-experiment.md` · `docs/experiments/instruction-tuning-aborted-run.md`
