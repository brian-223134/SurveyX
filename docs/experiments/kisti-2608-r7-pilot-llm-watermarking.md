# KISTI r7 파일럿 1편 — llm-watermarking (2026-11-11)

CSUR 2026 게재 GT 파일럿(r7) 중 AutoSurvey 가 먼저 돌린 것과 같은 topic 한 편을 SurveyX 로 생성·채점했다. 백본은 AutoSurvey r7 과 같은 DashScope intl `qwen-plus-2025-12-01`. **r6 이전·25 topic(r5) 결과와 같은 표에 놓지 않는다.**

## 0. 결과 행

| agent | topic 문자열(실제 사용) | 허용 / 전체 · 지문 | refs | recall (hit / 209) | precision | 누수 검사 | in / out 토큰 | 비용 $ | 재시도 · 잘림 · 429 | 소요 | 산출물 경로 · 커밋 |
|---|---|---|---:|---|---:|---|---|---:|---|---|---|
| SurveyX | 전체 제목 (`Securing Large Language Models: A Survey of Watermarking and Fingerprinting Techniques`) | 1,666,650 / 1,698,312 · `52a004ad` (끝 개행 규칙으로 해시하면 `675fdac8`) | 41 | 9 / 209 = 4.31% | 22.50% | 0건 | 8,605,443 / 849,048 | 4.4611 | HTTP 0 · 잘림 0 · 429 0 (markdown 상한 도달 9, 무한 루프 205회 후 재개) | 5시간 14분 (중단된 루프 86분 포함) | `SurveyX/outputs/2026-11-11-0736_Secur/` · `d2a2709`(상한 게이트) + 이 문서 커밋 |

- precision = 9 / 40 (식별 가능한 인용 40; 인용 41).
- 비용은 token_monitor × `LLM.yaml` 단가(in $0.4 / out $1.2 per 1M). DashScope 는 응답에 비용이 오지 않고 키 차분 조회도 하지 않는다(OpenRouter 아님).

## 1. 실행 조건

- 명령: `CUDA_VISIBLE_DEVICES=3 KISTI_VIEW=kisti-2608-r7 KISTI_GT_REFS_FILE=$K/candidates/csur2026_gt_refs.jsonl KISTI_TOPICS_FILE=$K/candidates/csur2026_topics.jsonl setsid nohup $PY scripts/run_kisti.py --slug llm-watermarking` (`--dry-run` 먼저 확인).
- 입력 sha: topics `d3acc763…` · gt_refs `dae62edc…` · 정책 `AutoSurvey/data/topic_policy.kisti-2608-r7.jsonl` `bae2d5a8…` — 지시와 일치. view `kisti-2608-r7` = `934adb11 / 2026-11-10T14:07:31Z` (1,698,312편, 제외 키 43).
- 백본: `qwen-plus-2025-12-01` @ `dashscope-intl.aliyuncs.com/compatible-mode/v1`, temperature 0.6, max_tokens 8192, 잘림 재요청 10, `enable_thinking` 미전송. `.env` 만 임시 교체(백업 `.env.bak-20261111-r7`).
- 생성 전 확인: 허용 1,666,650 / 1,698,312 (cutoff 이후 day 30,243 · month 1,416 · year 3, 허용 집합 안의 제외 id 0) — AutoSurvey 실측과 같다. 정책 행 `topic` = 넘긴 topic 문자열(경고 없음).
- 순서: 07:34 시작(단독). LLM×MapReduce-V2 가 약 10:50 부터(12:53 이전 종료) 같은 계정으로 동시에 돌았다(사용자 승인). SurveyX 쪽 429 는 0건이었다.

## 2. 무한 루프와 재개 — `SURVEYX_MARKDOWN_RETRY_MAX` (`d2a2709`)

본문 단계 소절 1.2(Dual-Scope Clarification and Conceptual Boundaries)의 첫 묶음에서 `content_generator.write_content_iteratively` 의 `while contains_markdown(res)` 가 끝나지 않았다. 이 루프는 **같은 프롬프트를 상한 없이** 다시 보내고, `contains_markdown` 은 한 줄에 `*` 두 개만 있어도 markdown 으로 본다. qwen-plus 는 거의 같은 응답(`…token sequences—i.e., *L…*`)을 내며 이탤릭을 일관되게 써서 **08:59–10:04 동안 205회 연속 거부**됐다. llama 에서는 소절당 4.1회로 저절로 끝나던 루프다(docs/kisti-run.md §3, 09-08 결정).

사용자 승인 후 처리:
1. `full_run` 에 SIGTERM (10:04:11). runner 가 `status=failed` 로 metrics 를 남겼고, 그 시점 지표를 `metrics/part1/` 에 보존.
2. env 게이트 추가: `SURVEYX_MARKDOWN_RETRY_MAX=N` 이면 N회 호출 후 마지막 응답 채택 + WARNING `markdown retry cap`. **미설정 = 원 동작(상한 없음)**. 단위 테스트 `tests/test_markdown_cap.py`.
3. 같은 task_id 로 `tasks/workflow/04_gen_content.py → 05_post_refine.py → 06_gen_latex.py` 재실행(10:06–12:50, 상한 10). 검색·필터·정리·개요 산출물(`jsons/`, `outlines.json`, `references.bib`)을 그대로 읽으므로 문헌 풀(41)·개요는 1부와 같다.
4. 지표 병합: `request_stats.txt` = 1부 510 + 2부 489 = 999건. `token_monitor`/`time_monitor` 는 재실행 때 `generate content` 라벨이 덮어써지므로 1부 본문 단계를 `generate content (aborted part1)` 라벨로 따로 더했다(비용 $0.7285, 85분 38초). `run_args.json` 에 `part1`·`resumed` 기록.

**상한 도달 9묶음** (소절 4개): Conceptual Foundations 4 · Dual-Scope 2 · Cross-Method Comparative Analysis 2 · Core Security Properties 1. 채택된 응답의 `*강조*` 가 tex 에 그대로 남았다(`*text watermarking*` 등 5곳 — PDF 에 별표가 보인다). `#` 로 인한 컴파일 실패는 없었다.

## 3. 점검 결과

**검색어 — 주제어는 남았다(r4 와 다름).** 확장 키워드 = 원 제목 · `LLM security` · `text watermarking` · `model fingerprinting`; 클러스터 키워드 `LLM alignment security vulnerabilities` · `Model Ownership Verification` · `Multimodal Intellectual Property Protection`. watermark / fingerprint 모두 유지.

**그러나 풀이 작다 — 구(句) 단위 ILIKE.** adapter `search_on_arxiv_single_word` 는 키워드 전체를 한 덩어리 부분 문자열로 찾는다. 허용 집합에서 키워드별 적중: 원 제목 0 · `LLM security` 44 · `text watermarking` 41 · `model fingerprinting` 13 · `Model Ownership Verification` 11 (참고: `watermark` 단독 2,824 · `fingerprint` 단독 6,219). 문헌 깔때기 **리콜 풀 109 → coarse 109 → fine 41 → 정리 41** (r4 는 2,028 → 193 → 189). 인용 상한이 41편이라 recall 상한은 41/209 = 19.6%, 실제 적중 9 (= 풀 안의 GT 9편, 전부 인용됨). SurveyX 고유 검색 동작이라 코드는 두었다.

**정책·누수.** 사후 재판정 위반 0 / 41, 게이트 차단 0 / 41, `policy_comparable = true`, `score.denominator_matches_topics = true` (209). 누수: GT DOI `10.1145/3773028` 이 refs·본문·bib 에 0회, GT 제목 bib 0회 → clean.

**허용 집합 지문.** adapter 규칙(`"\n".join(sorted)`) = `52a004ad…`, AutoSurvey·SurveyForge 규칙(끝 개행 포함) = `675fdac8d088420a…` 로 AutoSurvey 와 같은 집합(r4 PoC §3 과 같은 표기 차이).

## 4. 특이 사항

- **15분짜리 호출 1건** — 검색 2회차 키워드 생성(07:38:14 → 07:53:30). 응답은 정상(status 1)으로 돌아왔다. 검색 단계 16.8분 중 대부분.
- **section_words 파싱 실패 2건** — 응답에 `</answer>` 가 없어 `@retry(3)` 로 재요청, 회복(`<section_words>` 잔존 0).
- **section rewrite 원문 복귀 20건** — qwen 의 섹션 재작성 응답에 `\subsection` 이 첫 1개만 남아(원래 3–5개) `replace_environment_contents` 가 재작성을 버리고 원문을 썼다. 잘림 아님(status 2/3 0건). 해당 섹션은 후처리 다듬기가 빠진 채 본문 단계 결과 그대로.
- **pdflatex 유니코드** — SurveyX tex 변환기에는 유니코드 첨자·기호 치환이 없다. tex 에 ⁻ 3 · ₂ 2 · ⁸ 2 · ₁ · ₅ · ² · Δ 14 · → 11 · ≈ 9 · ≥ 7 · ≤ 7 · × 4 · ± 1 · 가타카나 5 · 키릴 а 1 이 남아 `Unicode character … not set up` 오류가 났지만 `latexmk -f` 라 PDF(42쪽)는 나왔다(해당 문자는 빠짐). MiKTeX 설정 오류는 없었다(11-11 수정 이후).
- 구조: 9섹션 / 33소절 / 21,126단어(tex) / 42쪽, 인용 41 (arXiv 30 / DOI 11), citation runs 711, draft 호출 378 (소절당 11.45 — 1부 루프 205회 포함).
- 단계 소요: 검색 16.8 · 필터 1.2 · 정리 7.5 · 개요 36.2 · 본문(1부, 중단) 85.6 · 본문(재개) 98.1 · 후처리 65.9 · 표 3.7 · LaTeX 0.2분. 루프 86분과 재개 공백 2분을 빼면 약 3시간 46분.
