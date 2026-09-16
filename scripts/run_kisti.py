#!/usr/bin/env python3
"""KISTI corpus 로 SurveyX 한 편(또는 topic 25편 배치)을 돌리고 편당 기록을 남긴다.

파이프라인 코드는 건드리지 않고 tasks/full_run.py 를 그대로 부른다. 이 스크립트가 하는 일은
실행 전후의 기록뿐이다 (docs/kisti-run.md §4):
  1. 전제 확인      .env 의 SURVEYX_DATA_SOURCE=kisti · 디코딩 프로파일 · view 디렉터리 · **topic 정책**
  2. 요청 기록 회전  outputs/tmp/request_stats.txt 는 전역 누적 파일 → 실행 전 .bak 으로 치워 편 단위로 만든다
  3. 실행 전 스냅샷  .env(키 마스킹, 실행 환경변수 KISTI_* 반영) · view 정체성 · OpenRouter 키 사용액(check_credits.py)
  4. 실행           KISTI_VIEW=<view> KISTI_TOPIC_ID=<slug> python tasks/full_run.py --title "<Topic>" --key_words "<Topic>"
  5. 실행 후        task 디렉터리 확인 → metrics/ 에 env.snapshot.json · view.snapshot.json · credits.json ·
                   run_args.json · request_stats.txt 저장 → scripts/collect_run.py 로 run.json 작성
                   (fetcher provenance 는 파이프라인이 metrics/fetcher_provenance.json 으로 남긴다)

topic 정책 (2026-09-14 규약, kisti_data/docs/asg/AGENT-HANDOFF.md §0): reference cutoff 를 2025-12-31 로 고정하지
않고 topic 별 GT 최초 공개일(retrieval_cutoff_at) 이전 문헌만 검색한다. KistiFetcher 가 KISTI_TOPIC_ID=<slug> 로
정책을 적용하므로 이 스크립트가 topic → slug 를 찾아 실행 환경변수로 넣는다(.env 에 두지 않는다 — topic 마다 다름).
정책 파일(AutoSurvey/data/topic_policy.<view>.jsonl)·sidecar(paper_dates.json)·topic 행이 없으면 실행 전에 멈춘다.
topics.kisti.jsonl 밖의 --title 은 slug 가 없어 정책을 걸 수 없다 → --no-policy 를 명시해야 돈다(비교 대상 아님).

사용 (반드시 surveyx env 의 python; view 는 KISTI_VIEW 환경변수 또는 --view, 새 규약은 kisti-2608):
  PY=/data2/chanjoong/miniforge3/envs/surveyx/bin/python
  KISTI_VIEW=kisti-2608 $PY scripts/run_kisti.py --slug instruction-tuning-llms      # topics.kisti.jsonl 의 slug
  $PY scripts/run_kisti.py --view kisti-2608 --title "Instruction Tuning for Large Language Models"
  KISTI_VIEW=kisti-2608 $PY scripts/run_kisti.py --all [--skip-done] [--limit N] [--dry-run]
  nohup env KISTI_VIEW=kisti-2608 $PY scripts/run_kisti.py --all --skip-done > outputs/kisti_batch.log 2>&1 &

topic 문자열은 topics.kisti.jsonl 의 title 을 그대로 --title 과 --key_words 양쪽에 준다
(--key_words 를 비우면 핵심어가 유실된다 — kisti_data/docs/asg/surveyx.md §2).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import collect_run  # noqa: E402

OUTPUTS = REPO_ROOT / "outputs"
LOG_DIR = OUTPUTS / "logs"
REQUEST_STATS = OUTPUTS / "tmp" / "request_stats.txt"
CREDITS_LOG = OUTPUTS / "credits.log"
KISTI_ROOT = collect_run.KISTI_ROOT
ADAPTER_DIR = collect_run.ADAPTER_DIR
TOPICS = KISTI_ROOT / "data" / "topics.kisti.jsonl"
FMT = "%Y-%m-%d %H:%M:%S"
PROFILE_KEYS = ("SURVEYX_TEMPERATURE", "SURVEYX_MAX_TOKENS", "OPENROUTER_PROVIDER_ONLY")
# 실행 환경변수가 .env 를 덮는 키 (config.py 의 load_dotenv 는 기존 환경변수를 덮지 않으므로 자식 프로세스에서도 이 값이 이긴다)
KISTI_ENV_KEYS = ("KISTI_VIEW", "KISTI_TOPIC_ID", "KISTI_TOPIC_POLICY", "KISTI_ADAPTER_DIR", "KISTI_FULLTEXT_LIMIT")
DEFAULT_VIEW = "kisti-2512"          # config.DEFAULT_VIEW 와 같음 — 전환은 결정 대기(AGENT-HANDOFF §0 6번)
POLICY_VIEW = "kisti-2608"           # 채점 분모 n_gt_refs_cutoff 가 정의된 view


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]


def load_topics() -> list[dict]:
    if not TOPICS.exists():
        return []
    return [json.loads(l) for l in TOPICS.read_text(encoding="utf-8").splitlines() if l.strip()]


def resolve_slug(title: str, topics: list[dict] | None = None) -> str | None:
    """topics.kisti.jsonl 의 title 과 (공백·기호 무시) 일치하는 행의 slug. 없으면 None."""
    want = collect_run.norm_title(title)
    for t in (topics if topics is not None else load_topics()):
        if collect_run.norm_title(t.get("title", "")) == want:
            return t.get("slug")
    return None


def effective_env(dotenv: dict) -> dict:
    """.env(마스킹) 위에 실행 환경변수 KISTI_* 를 얹는다 — 이것이 자식 full_run.py 가 실제로 보는 값이다."""
    eff = dict(dotenv)
    for k in KISTI_ENV_KEYS:
        if os.environ.get(k):
            eff[k] = os.environ[k]
    return eff


def log(msg: str):
    print(f"[{datetime.now().strftime(FMT)}] {msg}", flush=True)


# --------------------------------------------------------------------------- preconditions
def check_env(env: dict, allow_source: bool) -> str:
    view = env.get("KISTI_VIEW") or DEFAULT_VIEW
    src = env.get("SURVEYX_DATA_SOURCE")
    if src != "kisti" and not allow_source:
        sys.exit(f".env SURVEYX_DATA_SOURCE={src!r} — KISTI 실행은 'kisti' 여야 한다 (--allow-source 로 무시)")
    view_dir = KISTI_ROOT / "data" / "views" / view
    if not (view_dir / "papers.parquet").exists():
        sys.exit(f"view 가 없다: {view_dir} (adapter/common/view.py 로 먼저 만들 것)")
    missing = [k for k in PROFILE_KEYS if not env.get(k)]
    if missing:
        log(f"WARN 디코딩 프로파일 미설정: {missing} — 원 SurveyX 동작으로 돌아간다 (docs/kisti-run.md §3)")
    return view


def check_policy(view: str, slug: str, env: dict) -> dict:
    """KistiFetcher 와 같은 규칙으로 정책 행·sidecar 를 실행 전에 확인한다(fail-fast — 크레딧을 쓰기 전에 멈춘다).
    돌려주는 dict 는 run_args.json 에 기록된다. 허용 집합 자체는 여기서 만들지 않는다(fetcher 가 만들고 provenance 로 남긴다)."""
    if str(ADAPTER_DIR) not in sys.path:
        sys.path.insert(0, str(ADAPTER_DIR))
    try:
        from common.retrieval_policy import find_topic_policy, load_topic_policy  # type: ignore
    except Exception as e:
        sys.exit(f"adapter 를 불러올 수 없다 ({ADAPTER_DIR}): {e!r} — KISTI_ADAPTER_DIR 확인")
    path = env.get("KISTI_TOPIC_POLICY") or find_topic_policy(view)
    if not path or not Path(path).exists():
        sys.exit(f"topic 정책 파일 없음 (KISTI_TOPIC_POLICY 또는 AutoSurvey/data/topic_policy.{view}.jsonl) — "
                 f"AutoSurvey scripts/build_topic_policy.py --view {view}")
    rows = load_topic_policy(path)
    row = rows.get(slug)
    if row is None:
        sys.exit(f"정책 파일에 topic_id={slug!r} 행이 없다: {path}")
    if row.get("status") != "ok":
        sys.exit(f"정책 행 status={row.get('status')!r} — cutoff 미확정 topic 은 실행하지 않는다 ({slug}, {path})")
    sidecar = KISTI_ROOT / "data" / "views" / view / "paper_dates.json"
    if not sidecar.exists():
        sys.exit(f"sidecar 없음: {sidecar} — adapter/common/paper_dates.py --view {view}")
    if view != POLICY_VIEW:
        log(f"WARN view={view} — 채점 분모 n_gt_refs_cutoff 는 {POLICY_VIEW} 기준이다 (AGENT-HANDOFF §0). "
            f"새 규약 실행은 KISTI_VIEW={POLICY_VIEW} 로")
    return {"topic_id": slug, "retrieval_cutoff_at": row.get("retrieval_cutoff_at"),
            "exclude_ids": row.get("exclude_ids") or [], "policy_file": str(path),
            "corpus_snapshot_id": row.get("corpus_snapshot_id"), "sidecar": str(sidecar)}


def credits_snapshot(label: str) -> dict | None:
    """scripts/check_credits.py 를 불러 키 사용액을 읽는다. 실패해도 실행은 계속한다."""
    try:
        out = subprocess.check_output(
            [sys.executable, str(REPO_ROOT / "scripts" / "check_credits.py"), "--label", label,
             "--log", str(CREDITS_LOG)], text=True, cwd=REPO_ROOT, timeout=60)
    except Exception as e:  # 네트워크·키 문제
        log(f"WARN credits snapshot failed ({label}): {e}")
        return None
    m = re.search(r"key\([^)]*\):.*?used=\$([\d.]+)", out)
    a = re.search(r"account:.*?used=\$([\d.]+)", out)
    return {"label": label, "at": datetime.now().strftime(FMT),
            "key_used_usd": float(m.group(1)) if m else None,
            "account_used_usd": float(a.group(1)) if a else None, "raw": out.strip()}


def rotate_request_stats() -> Path | None:
    if REQUEST_STATS.exists() and REQUEST_STATS.stat().st_size > 0:
        bak = REQUEST_STATS.with_name(f"request_stats.{datetime.now().strftime('%Y%m%d-%H%M%S')}.bak")
        shutil.move(str(REQUEST_STATS), str(bak))
        log(f"rotated {REQUEST_STATS.name} → {bak.name}")
        return bak
    return None


def find_task_dir(title: str, since: float) -> Path | None:
    cands = []
    for cfg in OUTPUTS.glob("*/tmp_config.json"):
        if cfg.stat().st_mtime < since - 5:
            continue
        try:
            if json.loads(cfg.read_text(encoding="utf-8")).get("title") == title:
                cands.append(cfg.parent)
        except Exception:
            continue
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def done_titles() -> set[str]:
    done = set()
    for rj in OUTPUTS.glob("*/run.json"):
        try:
            r = json.loads(rj.read_text(encoding="utf-8"))
            if r.get("status") == "ok" and r.get("structure", {}).get("pdf_pages"):
                done.add(r.get("topic"))
        except Exception:
            pass
    return done


# --------------------------------------------------------------------------- one topic
def run_topic(title: str, dry_run: bool = False, allow_source: bool = False,
              slug: str | None = None, no_policy: bool = False) -> Path | None:
    env_masked = effective_env(collect_run.parse_dotenv(REPO_ROOT / ".env"))
    view = check_env(env_masked, allow_source)
    env_masked["KISTI_VIEW"] = view
    # topic 정책: slug(= 정책 topic_id) 를 자식 프로세스 환경변수 KISTI_TOPIC_ID 로 넣는다
    slug = slug or resolve_slug(title)
    policy = None
    child_env = {**os.environ, "PYTHONUNBUFFERED": "1", "KISTI_VIEW": view}
    if no_policy:
        child_env.pop("KISTI_TOPIC_ID", None)
        env_masked.pop("KISTI_TOPIC_ID", None)
        log("WARN --no-policy: topic 정책 없이 실행 — 2026-09-14 규약 비교 대상이 아니다 (2026년 문헌이 샐 수 있음)")
    elif slug is None:
        sys.exit(f"topic 이 {TOPICS.name} 에 없어 정책(KISTI_TOPIC_ID)을 걸 수 없다: {title!r} — "
                 f"정책 없이 돌리려면 --no-policy 를 명시할 것")
    else:
        policy = check_policy(view, slug, env_masked)
        child_env["KISTI_TOPIC_ID"] = slug
        env_masked["KISTI_TOPIC_ID"] = slug
    file_slug = slug or slugify(title)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"kisti_{file_slug}_{ts}.log"
    cmd = [sys.executable, str(REPO_ROOT / "tasks" / "full_run.py"), "--title", title, "--key_words", title]
    env_prefix = " ".join(f"{k}={child_env[k]}" for k in ("KISTI_VIEW", "KISTI_TOPIC_ID") if child_env.get(k))
    log(f"topic: {title}")
    log(f"cmd: {env_prefix} {' '.join(repr(c) if ' ' in c else c for c in cmd)}")
    log(f"view: {view} · log: {log_path}")
    if policy:
        log(f"policy: topic_id={policy['topic_id']} cutoff<{policy['retrieval_cutoff_at']} "
            f"exclude {len(policy['exclude_ids'])} · {policy['policy_file']}")
    if dry_run:
        return None

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    rotate_request_stats()
    # view 정체성은 시작 시점에 찍는다 — 같은 경로에서 교체될 수 있다(2026-09-08 v1→v2, 파일럿 수집이 그 직후였다)
    vsnap = collect_run.view_snapshot(view)
    log(f"view snapshot: version={vsnap.get('version')} papers={vsnap.get('view_papers')} "
        f"manifest={str(vsnap.get('manifest_sha256'))[:8]} exclude_keys={vsnap.get('exclude_keys')}")
    before = credits_snapshot(f"before:{file_slug}")
    started = time.time()
    with log_path.open("w", encoding="utf-8") as fw:
        proc = subprocess.run(cmd, cwd=REPO_ROOT, stdout=fw, stderr=subprocess.STDOUT, env=child_env)
    ended = time.time()
    after = credits_snapshot(f"after:{file_slug}")
    status = "ok" if proc.returncode == 0 else "failed"
    log(f"full_run.py exited {proc.returncode} ({status}) in {int(ended - started) // 60}m")

    task_dir = find_task_dir(title, started)
    if task_dir is None:
        # task 디렉터리조차 없으면(전처리 초반 실패) 요청 기록만 보존
        if REQUEST_STATS.exists():
            keep = REQUEST_STATS.with_name(f"request_stats.failed.{file_slug}.{ts}.txt")
            shutil.move(str(REQUEST_STATS), str(keep))
            log(f"no task dir; request stats kept at {keep}")
        return None

    metrics = task_dir / "metrics"
    metrics.mkdir(parents=True, exist_ok=True)
    (metrics / "env.snapshot.json").write_text(json.dumps(env_masked, indent=2, ensure_ascii=False) + "\n",
                                               encoding="utf-8")
    (metrics / "view.snapshot.json").write_text(json.dumps(vsnap, indent=2, ensure_ascii=False) + "\n",
                                                encoding="utf-8")
    measured = None
    if before and after and before.get("key_used_usd") is not None and after.get("key_used_usd") is not None:
        measured = round(after["key_used_usd"] - before["key_used_usd"], 4)
    (metrics / "credits.json").write_text(
        json.dumps({"before": before, "after": after, "measured_usd": measured}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    (metrics / "run_args.json").write_text(json.dumps({
        "args": f'--title "{title}" --key_words "{title}"', "status": status, "returncode": proc.returncode,
        "view": view, "topic_id": (slug if policy else None), "policy": policy,
        "env_overrides": {k: child_env[k] for k in KISTI_ENV_KEYS if child_env.get(k)},
        "started_at": datetime.fromtimestamp(started).strftime(FMT),
        "ended_at": datetime.fromtimestamp(ended).strftime(FMT),
        "log_path": (str(log_path.relative_to(REPO_ROOT)) if log_path.is_relative_to(REPO_ROOT)
                     else str(log_path)),
        "python": sys.executable,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if REQUEST_STATS.exists():
        shutil.move(str(REQUEST_STATS), str(metrics / "request_stats.txt"))

    try:
        out = collect_run.write_run(task_dir.name)
        r = json.loads(out.read_text(encoding="utf-8"))
        s, sc, lk = r["structure"], r.get("score") or {}, r["leak"]
        log(f"run.json: {out}")
        pol = r.get("retrieval_policy") or {}
        log(f"  view {r.get('view')}@{r.get('view_version_label')} · "
            f"policy {pol.get('retrieval_cutoff_at') or '없음'} (allowed {pol.get('allowed')}, violations {r.get('policy_check', {}).get('violations') if r.get('policy_check') else '-'}) · "
            f"cost TM ${r['cost_total_usd']} · measured {r.get('cost_measured_usd')} · "
            f"{s['sections']}/{s['subsections']} · {s['words']} words · refs {s['references']} · "
            f"draft/sub {r.get('draft_calls_per_subsection')} · trunc {r['truncation_retries']}/{r['truncated_calls']} · "
            f"recall {sc.get('recall')} precision {sc.get('precision')} · leak {'clean' if lk['clean'] else 'LEAK!'}")
        return out
    except Exception as e:
        log(f"WARN collect_run failed: {e!r} — 나중에 `scripts/collect_run.py --task_id {task_dir.name}` 로 재시도")
        return None


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--title", help="topic 문자열 (그대로 --title/--key_words 에 준다)")
    g.add_argument("--slug", help="topics.kisti.jsonl 의 slug")
    g.add_argument("--all", action="store_true", help="topics.kisti.jsonl 25편 순차 실행")
    ap.add_argument("--skip-done", action="store_true", help="run.json 이 있고 PDF 까지 만들어진 topic 은 건너뛴다")
    ap.add_argument("--limit", type=int, default=0, help="--all 에서 최대 편수 (0 = 전부)")
    ap.add_argument("--dry-run", action="store_true", help="실행하지 않고 명령만 출력")
    ap.add_argument("--allow-source", action="store_true", help="SURVEYX_DATA_SOURCE 가 kisti 가 아니어도 진행")
    ap.add_argument("--view", help=f"KISTI view (기본: 환경변수 KISTI_VIEW → .env → {DEFAULT_VIEW}; 새 규약은 {POLICY_VIEW})")
    ap.add_argument("--no-policy", action="store_true",
                    help="topic 정책(KISTI_TOPIC_ID) 없이 실행 — topics.kisti.jsonl 밖의 --title 에만. 비교 대상 아님")
    args = ap.parse_args()
    if args.view:
        os.environ["KISTI_VIEW"] = args.view

    topics = load_topics()
    if args.title:
        titles = [(args.title, resolve_slug(args.title, topics))]
    elif args.slug:
        hit = [t["title"] for t in topics if t.get("slug") == args.slug]
        if not hit:
            sys.exit(f"slug not found in {TOPICS}: {args.slug}")
        titles = [(hit[0], args.slug)]
    else:
        titles = [(t["title"], t.get("slug")) for t in topics]
        if args.skip_done:
            done = done_titles()
            titles = [(t, s) for t, s in titles if t not in done]
            log(f"skip-done: {len(done)} done, {len(titles)} remaining")
        if args.limit:
            titles = titles[: args.limit]

    results = []
    for i, (title, slug) in enumerate(titles, 1):
        log(f"===== [{i}/{len(titles)}] =====")
        try:
            results.append((title, run_topic(title, dry_run=args.dry_run, allow_source=args.allow_source,
                                             slug=slug, no_policy=args.no_policy)))
        except SystemExit:
            raise
        except Exception as e:
            log(f"ERROR {title}: {e!r}")
            results.append((title, None))
    if not args.dry_run:
        log("===== summary =====")
        for title, out in results:
            log(f"{'OK ' if out else 'NG '} {title} → {out}")


if __name__ == "__main__":
    main()
