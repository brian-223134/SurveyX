# 실험 기록: Instruction Tuning 서베이 — 중단된 실행 (2026-09-03)

벤치마크 view `bench-2512`로 전환한 뒤의 첫 실행. **완주하지 못했다.**
전문(full text) 확보 단계에서 arXiv API rate limit으로 154편 중 113편이 실패해,
41편만 남은 시점에 의도적으로 중단했다.

산출물은 지우지 않고 `outputs/2026-09-03-0333_Instr/`에 보존했다
(`jsons/` 154편, `metrics/`). 서베이 본문·PDF는 없다.

## 한눈에 보기 (TL;DR)

| 메트릭 | 값 |
|---|---|
| 결과 | **중단** — AttributeTree 진입 직후 |
| 중단 사유 | 전문 확보 실패율 **73%** (113/154, arXiv 429) |
| 소요 시간 | 19분 (03:33:06 ~ 03:52) |
| 실측 비용 | **$0.0389** (키 사용액 차분, TokenMonitor $0.0334) |
| 재시도 가능 여부 | **가능** — 일시적 실패는 캐시에 동결되지 않음 (§4) |

중단이 아니었다면 41편으로 서베이를 썼을 것이다. 이 토픽의 GT eligible이 153편이라
41편으로는 reference recall 비교가 성립하지 않고, 3시간·$2 남짓을 써서 버릴 산출물이
나온다. 비용의 87%를 차지하는 AttributeTree 진입 직후에 세워 소모를 최소화했다.

## 1. 실험 세팅

| 항목 | 값 |
|---|---|
| 백본 LLM | `meta-llama/llama-3.3-70b-instruct` (OpenRouter, provider `akashml/fp8` 고정) |
| 임베딩 | `BAAI/bge-base-en-v1.5` (로컬) |
| 코퍼스 | asg-common-corpus `v0.1-poc`, view **`bench-2512`** (947,451편) |
| view manifest sha256 | `d4c16c499ecbff88c08387c48784f7cd2f759b4ee6928f2af67655c2866c0d86` |
| 입력 | `--title` = `--key_words` = `"Instruction Tuning for Large Language Models"` (§3) |
| GT | ACM CSUR 2026-01-08, `10.1145/3777411`, cov 89% / elig 153 |
| task_id | `2026-09-03-0333_Instr` |

누수 검증: 리콜 2,566편(키워드 4종 합집합)에 `gt_exclude.txt` 15 id 잔존 0.
이 토픽의 GT preprint 쌍둥이 `2308.10792`가 view에서 제거된 것을 직접 확인했다.

## 2. 문헌 깔때기 — Edge 실행과 비교

| 단계 | Edge (2026-08-31, `surveyeval-2512`) | Instruction Tuning (`bench-2512`) |
|---|---:|---:|
| 리콜 | 1,318편 | 1,089편 |
| coarse+fine 필터 | 200편 | 154편 |
| **전문 확보** | **199편 (실패 1)** | **41편 (실패 113)** |

리콜·필터 감소는 키워드 수 차이(6개 → 4개)와 토픽 폭 차이로 설명되는 정상 범위다.
문제는 전문 확보 한 단계에서만 발생했다.

## 3. 단계별 시간

| 단계 | 소요 | 비고 |
|---|---|---|
| 리콜 | 1분 54초 | |
| 필터 (coarse+fine) | 16분 44초 | 전문 확보 13분 15초 포함 |
| └ 전문 확보 | 13분 15초 | 154편 중 41편 성공 |
| 정제(AttributeTree) | — | 진입 직후 중단 |

## 4. 원인 — arXiv API rate limit

실패 113건의 분해:

| 사유 | 건수 |
|---|---:|
| `HTTP Error 429: Unknown Error` | 108 |
| `HTTP Error 429: Too Many Requests` | 3 |
| 타임아웃 | 2 |

**막힌 엔드포인트는 `arxiv.org/e-print`가 아니라 `export.arxiv.org/api/query`다.**
`ArxivFullTextProvider.fetch()`가 다운로드 전에 `latest_version()`으로 API를 한 번 더
치는데(`providers.py`), 그쪽이 throttle됐다. 중단 후 `e-print`를 직접 받아보면 HTTP 200이
정상적으로 떨어지므로, e-print만 보고 "arXiv 정상"이라 판단하면 오진한다.

즉 **논문 1편당 arXiv 호출이 2회**다. 25편 배치는 25 × ~150편 × 2 = 약 7,500회가 되므로
이 구조가 배치의 최대 리스크다.

지수 백오프(15/30/60/120초, 4회)는 **정상 동작한다.** 파이프라인 실행 중에는 그 로그가
보이지 않았는데, `fill_md_text()`가 헬퍼 subprocess의 stderr를 `returncode != 0`일 때만
기록하기 때문이다(`common_corpus_fetcher.py`). 파이프라인 밖에서 stderr를 살려 재현하니
`일시적 오류 HTTP Error 429 (…api/query?id_list=…) — 120s 후 재시도 (4/4)`가 그대로 찍혔다.
throttle이 백오프 창(총 225초)보다 오래 지속돼 4회를 모두 소진하고 포기한 것이다.

## 5. 재시도 가능성 — 실패는 동결되지 않았다

`FullTextResolver`는 **영구 오류만** `failure.json`으로 동결한다(파싱 실패 등).
429·타임아웃 같은 일시적 오류는 의도적으로 동결하지 않는다(`resolver.py:72`).
중단 후 캐시를 확인하니 `failure.json`은 3건뿐이고 113건의 429는 하나도 없다.

→ **재실행이 곧 재시도다.** 헬퍼의 `--retry-failed`는 파싱 실패에만 필요하다.

전문 캐시는 351편 → 448편으로 늘었다(성공분은 영구 보존).

## 6. 재개 절차

1. **throttle 해제 확인** — e-print가 아니라 API 엔드포인트로 확인해야 한다.
   ```bash
   curl -sI "https://export.arxiv.org/api/query?id_list=2306.04757" | head -1
   # HTTP/2 200 → 풀림 / 429 → 대기
   ```
2. **캐시 프리워밍** (LLM 비용 $0). id 목록은 보존된 `jsons/`에서 그대로 뽑는다.
   ```bash
   /data2/chanjoong/miniforge3/envs/asg-corpus/bin/python scripts/fetch_fulltext_batch.py \
       --corpus-dir /data2/chanjoong/survey-agent/asg-common-corpus \
       --ids-file <ids.txt> > prewarm.jsonl 2> prewarm.err
   ```
   `status: "ok"`가 140편 이상이면 본 실행을 건다. 파이프라인 밖에서 먼저 채우므로
   실패해도 크레딧이 나가지 않는다.
3. **본 실행** — 리콜·필터는 다시 돌지만(약 5분, $0.03) 전문은 캐시 히트라 즉시다.

## 7. 배치 설계에 반영할 것

- **프리워밍을 선행 단계로 고정한다.** 전문 확보를 파이프라인 안에서 처음 시도하면,
  실패 시 이미 리콜·필터 비용을 쓴 뒤라 손실이 크다.
- **`latest_version()` 우회를 검토한다.** `e-print/<id>`를 버전 접미사 없이 부르면 arXiv가
  최신판을 준다. API 호출이 절반으로 줄고 오늘 막힌 엔드포인트를 아예 쓰지 않는다.
  코퍼스 쪽 `providers.py` 수정이며, 캐시 메타데이터의 `version` 필드를 무엇으로 채울지
  결정이 필요하다(현재 `v3` 형태가 재현성 기록에 들어간다). **미결.**
- **`fill_md_text()`가 헬퍼 stderr를 성공 시에도 남기게 한다.** 오늘 진단이 유실된 원인이다.
  **미결.**
- 실패율이 높으면 **본 실행을 시작하지 않는다** — 41편짜리 산출물은 벤치마크 데이터가 아니다.

## 8. 함께 확인된 것 — title-only 입력의 topic 오염

이 실행 직전, 벤치마크 규약대로 `--title`만 주고 한 번 더 돌렸다가 1분 만에 중단했다.

- `generate_keyword.md`는 "이미 키워드가 있다"는 전제로 **추가** 3~4개만 요구한다
  → 빈 시드로 부르면 핵심어가 결과에 들어가지 않는다
- `generate_topic.md`는 `{key_word}`만 받고 title을 쓰지 않는다

실측: "Instruction Tuning for Large Language Models"에 대해 키워드가
`natural language processing, language model fine-tuning, artificial intelligence,
transformer architecture`로 나오고, 생성된 topic 문장에 "instruction tuning"이 한 번도
등장하지 않았다. topic은 필터·아웃라인·본문 생성을 전부 지배하므로 그대로 뒀으면
일반 NLP 서베이가 나왔을 것이다.

→ **`--key_words`에 Topic 문자열을 그대로 시드로 준다.** `utils.py:116`의 `>=6` 게이트와
`utils.py:128-131` 분기가 시드를 보존한 채 LLM 확장 3개를 덧붙인다. 사람 입력은 여전히
Topic 문자열 하나뿐이라 25편에 기계적으로 동일 적용된다. 코퍼스 쪽
`docs/surveyx-usage.md` §3에 규약으로 반영했다.

## 9. 관련 자료

- 실행 로그: `outputs/instruction_tuning_run.log`
- 보존 산출물: `outputs/2026-09-03-0333_Instr/`
- 완주한 이전 실행: [edge-computing-experiment.md](edge-computing-experiment.md)
- 어댑터 설계: [common-corpus-adapter.md](../common-corpus-adapter.md)
- 코퍼스 쪽 절차서: `../asg-common-corpus/docs/surveyx-usage.md`
