# KISTI r4 PoC 1편 — llm-agent-optimization (2026-09-30)

corpus 쪽이 스냅샷 `kisti-2608-r4` 를 채택한 뒤(AGENT-HANDOFF §0, 2026-09-30) topic 정책을 건 SurveyX 첫 실행. 목적은 ① r4 view·정책·원문 경로(overlay bodies)가 SurveyX 에서 끝까지 도는지, ② run.json 기록·채점이 r4 분모와 맞는지 확인하는 것이다. **정책 적용 실행이라 비교 대상이지만, r2 이전 실행과는 분모가 달라(합계 2,543 → 4,010) 같은 표에 놓지 않는다.**

## 0. 한눈에

| 항목 | 값 |
|---|---|
| topic | A Survey on the Optimization of Large Language Model-based Agents (`llm-agent-optimization`, GT `10.1145/3789261`, twin `2503.12434`) |
| **view** | **kisti-2608-r4 = `32a77a48 / 2026-09-30T02:05:49Z`** (1,697,512편, 제외 키 43) |
| 정책 | cutoff **< 2025-03-16**, exclude 2 · 허용 **1,541,302** / 1,697,512 · 사후 재판정 위반 0 (bib 풀 189편) · 게이트 차단 0 / 193 |
| 소요 | **203분** (04:16 → 07:41 UTC) — 본문 116 · 후처리 38 · 정리(AttributeTree) 32 · 개요 8 · 필터 5 · 검색 4 |
| 비용 | TokenMonitor **$1.46** (실측 키 차분 $3.47 은 귀속 불가 — 같은 시간대에 AutoSurvey·SurveyForge·LLM×MR 이 같은 topic 을 r4 로 실행) |
| 문헌 깔때기 | 리콜 풀 2,028 → coarse 200 → fine 193 → 로드 189 |
| 원문 | **189편 전부 `kisti:body_store`**, overlay 0 · 없음 4(193 − 189) |
| 구조 | 7섹션 / 23소절 / 7,487단어(tex) / 23쪽 |
| refs | **인용 117** (arXiv 20 / DOI 97), bib 전편 189 |
| **recall / precision** | **0.0% / 0.0%** (0/190, 0/117) |
| 누수 | 0 — GT DOI `10.1145/3789261`·twin `2503.12434` 가 refs·본문·bib 에 0회, GT 제목 0 |
| 잘림 | 폐기 8 (fulfill_content 4 · compress_sections 4) / 채택 0 |
| 429 | 256, 모두 재시도로 흡수 (05:50 이후 0) |
| AttributeTree | 189/189 (repair 113, 미해결 0) — 파일럿 41/196 대비 복구 로직 효과 확인 |

## 1. 실행 조건

- 코드: SurveyX `feature/kisti-2608-r4` (`2f941d9`), adapter `kisti_data` `014b453`(overlay → body_store 원문 순서 수정 반영).
- 명령: `KISTI_VIEW=kisti-2608-r4 $PY scripts/run_kisti.py --slug llm-agent-optimization` — runner 가 `KISTI_TOPIC_ID` 주입, 정책 파일 `AutoSurvey/data/topic_policy.kisti-2608-r4.jsonl` 자동 탐색.
- 프로파일: llama-3.3-70b-instruct @ OpenRouter `akashml/fp8`(fallback 없음) · temperature 0.6 · max_tokens 8192 · 잘림 재요청 10 (AGENT-HANDOFF §4).
- 산출물: `outputs/2026-09-30-0418_A_Sur/` (`run.json`, `metrics/*.json`, `survey.pdf`).

## 2. 실행 전에 고친 것 — r4 채점 분모 (`61f6495`)

r4 의 `candidates/gap_to_80_refs.jsonl` 에서 overlay 로 들어온 GT ref 는 `kisti_doi` 가 비고 `view_id` 만 있다. `collect_run.gt_in_view_keys` 가 `kisti_doi` 만 읽어 이 topic 의 분모가 **190 이 아니라 128** 로 잡혔다(25 topic 합계 4,010 중 1,015행 누락). `view_id`(arXiv base id ∨ 소문자 DOI)로 같은 매칭 키를 만들게 고쳤고 `score.denominator_matches_topics == true` 를 확인했다.

- 합계는 키 집합 기준 4,001 로 topics 의 4,010 과 9 차이 — 6 topic 에서 같은 논문이 GT 에 두 번 실린 행(예: llm-watermarking `10.48550/arxiv.2310.08920`) 때문이며 이 topic 은 해당 없음(190 = 190). corpus 쪽 분모가 중복 행을 세는지는 corpus 쪽 확인 사항.
- `run_kisti.py` 의 채점 view 경고는 topic 행의 `n_gt_refs_cutoff_view` 를 기준으로 바꿨다(하드코딩 `kisti-2608` 이면 r4 실행마다 오경고).

## 3. 점검 결과

**허용 집합 지문 불일치 — 집합은 같고 표기 규칙만 다르다.** 허용 편수는 기댓값 1,541,302 와 일치하지만 provenance 의 `allowed_sha256` 은 `619a352e` (기댓값 `efe95869`). 같은 집합을 두 방식으로 해시하면 `"\n".join(sorted(ids))` = `619a352e`, 각 id 뒤에 `\n`(끝 개행 포함) = `efe95869`. KistiFetcher(adapter)는 앞 방식, AutoSurvey·SurveyForge `retrieval_policy.fingerprint` 는 뒤 방식이다. 4 agent 가 같은 값을 쓰려면 adapter 쪽을 맞춰야 한다(kisti_data 소관).

**overlay 원문 0편은 정상.** 로드된 189편 중 overlay `bodies.sqlite`(899편)에 있는 id 가 0이다 — 옛 adapter 문제가 아니라 overlay 추가분이 검색 풀에 들어오지 않았다.

**recall 0 의 원인은 검색어 확장.** SurveyX 의 키워드 생성이 `natural language processing, language model optimization, artificial intelligence` 를 붙이면서 "agent" 가 빠졌고, 클러스터 키워드도 `Multimodal Representation Learning` 이었다. 풀이 일반 LLM·NLP 서베이로 채워져(예: "A Review on Large Language Models…", "Natural Language Processing Advancements By Deep Learning: A Survey") 로드된 189편에 GT ref 가 **0편**이다. 개요도 "Optimization Techniques for Large Language Models" 등 에이전트 없는 LLM 최적화로 흘렀다. SurveyX 고유 검색 동작이므로 코드는 두고 agent 속성으로 기록한다(docs/kisti-run.md §2 원칙).

## 4. 다음

- 같은 topic 의 다른 agent 결과와 나란히 볼 때 recall 0 이 검색어 확장 탓인지(검색 풀 GT 0) 표에 주석으로 남긴다.
- 지문 규칙 통일은 kisti_data adapter 에 요청.
- 실측 비용은 agent 별 키 또는 순차 실행이 아니면 귀속되지 않는다(§6 키 분리).
