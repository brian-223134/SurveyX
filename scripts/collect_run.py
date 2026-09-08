#!/usr/bin/env python3
"""편당 run.json 매니페스트 — outputs/<task_id>/ 의 산출물과 metrics/ 에서 만든다.

왜 필요한가: TokenMonitor·TimeMonitor 는 단계별 토큰·시간만 남기고, 모델·provider·
temperature·max_tokens·view·잘림·재요청·누수 여부는 어디에도 남지 않는다. run.json 은
산출물 옆에 앉아 같은 커밋으로 들어가므로(.gitignore 예외) 재현 체인이 파일 단위로 닫힌다.
스키마는 AutoSurvey scripts/collect_run.py 의 run.json 과 맞춰 4 agent 를 한 표에서 join 한다.

사용:
    # 실행 직후 (scripts/run_kisti.py 가 자동 호출)
    python scripts/collect_run.py --task_id 2026-09-08-1200_Instr
    # 과거 실행 (metrics/ 에 request_stats 가 없으면 --request_stats 로 지정)
    python scripts/collect_run.py --task_id 2026-08-31-1231_edge_ --request_stats outputs/tmp/request_stats.txt
    # 집계 표 (outputs/*/run.json 전부)
    python scripts/collect_run.py --table

읽는 것 (모두 outputs/<task_id>/ 기준):
    tmp_config.json                 title · key_words(확장 후) · topic
    metrics/token_monitor.json      단계별 토큰·비용 (폐기한 잘림 응답 포함 — 과금되므로)
    metrics/time_monitor.json       단계별 시간
    metrics/request_stats.txt       요청 기록 (ChatAgent.update_record; run_kisti.py 가 전역 파일을 옮겨 둔 것)
                                    status 1 정상 · 0 HTTP 오류 · 2 잘림 폐기 · 3 잘림 채택
    metrics/env.snapshot.json       실행 시점 .env (키 마스킹) — 없으면 현재 .env 로 대체하고 표시
    metrics/credits.json            OpenRouter 키 사용액 전후 차분 (실측 비용)
    metrics/run_args.json           실행 인자·시작/종료 시각·returncode
    latex/survey.tex · latex/references.bib · survey.pdf
외부:
    $KISTI_DATA_ROOT/data/topics.kisti.jsonl          title → slug · gt_doi · n_gt_refs
    $KISTI_DATA_ROOT/data/views/<view>/exclude_keys.txt   누수 검사 키 38개 (GT 본체 + twin)
    $KISTI_DATA_ROOT/candidates/gap_to_80_refs.jsonl   tier == in_view 가 recall 분모
    $KISTI_DATA_ROOT/candidates/<domain>/<slug>/refs.json   GT 제목 (bib title 누수 검사)
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = REPO_ROOT / "outputs"
PROMPT_ROOT = REPO_ROOT / "resources" / "LLM" / "prompts"
KISTI_ROOT = Path(os.getenv("KISTI_DATA_ROOT", "/data2/chanjoong/kisti_data"))
ADAPTER_DIR = Path(os.getenv("KISTI_ADAPTER_DIR", str(KISTI_ROOT / "adapter")))

RECORD_SPLITTER = "||"
RECORD_SHOW_LENGTH = 200
DRAFT_TEMPLATES = ("content_generator/fulfill_content.md", "content_generator/fulfill_content_iteratively.md")
ARXIV_DOI_PREFIX = "10.48550/arxiv."
SECRET_RE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)", re.I)
ENV_KEYS_OF_INTEREST = [
    "SURVEYX_DEFAULT_MODEL", "SURVEYX_ADVANCED_MODEL", "OPENROUTER_PROVIDER_ONLY",
    "OPENROUTER_ALLOW_FALLBACKS", "SURVEYX_TEMPERATURE", "SURVEYX_MAX_TOKENS",
    "SURVEYX_RETRY_TRUNCATED", "SURVEYX_MAX_TRUNCATED_RETRY", "SURVEYX_HTTP_TIMEOUT",
    "SURVEYX_DATA_SOURCE", "KISTI_VIEW", "KISTI_FULLTEXT_LIMIT", "KISTI_ADAPTER_DIR",
]


# --------------------------------------------------------------------------- helpers
def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def git_state(repo: Path) -> dict:
    try:
        head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], text=True,
                                       stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True,
                                             stderr=subprocess.DEVNULL).strip())
        return {"head": head, "dirty": dirty}
    except Exception:
        return {"head": None, "dirty": None}


def parse_dotenv(path: Path, mask: bool = True) -> dict:
    """`.env` 를 dict 로. 키·토큰은 마스킹 (앞 6자 + '…')."""
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip("'\"")
        if mask and SECRET_RE.search(k) and v:
            v = v[:6] + "…"
        out[k] = v
    return out


def norm_title(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def arxiv_base(aid: str) -> str:
    return re.sub(r"v\d+$", "", aid.strip())


# --------------------------------------------------------------------------- request stats
def load_prompt_keys() -> list[tuple[str, str]]:
    """{템플릿 상대경로: 기록 prefix 키}. 기록은 request[:200] 에서 개행을 뺀 것이므로
    템플릿도 같은 방식으로 만들고 첫 치환 필드('{') 앞까지만 쓴다. 긴 키부터 매칭."""
    keys = []
    for p in sorted(PROMPT_ROOT.glob("**/*.md")):
        text = p.read_text(encoding="utf-8")
        raw = text[:RECORD_SHOW_LENGTH].replace("\n", "")
        key = raw.split("{")[0]
        if len(key) >= 40:
            keys.append((str(p.relative_to(PROMPT_ROOT)), key))
    keys.sort(key=lambda kv: -len(kv[1]))
    return keys


def match_template(request_prefix: str, keys: list[tuple[str, str]]) -> str:
    for name, key in keys:
        m = min(len(key), len(request_prefix))
        if m >= 40 and request_prefix[:m] == key[:m]:
            return name
    return "other"


def parse_request_stats(path: Path) -> dict:
    if not path or not path.exists():
        return {"available": False}
    keys = load_prompt_keys()
    status = Counter()
    http_errors = Counter()
    by_template = Counter()
    truncated_discarded_by_template = Counter()
    total = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split(RECORD_SPLITTER)
        if len(parts) < 3:
            continue
        total += 1
        st, code, req = parts[0].strip(), parts[1].strip(), parts[2]
        status[st] += 1
        tpl = match_template(req, keys)
        if st == "0":
            http_errors[code] += 1
            continue                      # 오류 요청은 템플릿 집계에서 제외 (재시도로 다시 세어진다)
        by_template[tpl] += 1
        if st == "2":
            truncated_discarded_by_template[tpl] += 1
    draft_calls = sum(by_template[t] for t in DRAFT_TEMPLATES)
    return {
        "available": True,
        "records": total,
        "ok": status["1"],
        "http_errors": dict(sorted(http_errors.items())),
        "http_error_total": status["0"],
        "truncated_discarded": status["2"],
        "truncated_accepted": status["3"],
        "draft_calls": draft_calls,
        "by_template": dict(by_template.most_common()),
        "truncated_discarded_by_template": dict(truncated_discarded_by_template),
    }


# --------------------------------------------------------------------------- structure / refs
def measure_tex(tex_path: Path) -> dict:
    """AutoSurvey scripts/check_survey.measure 와 같은 계산 (섹션·서브섹션·단어)."""
    if not tex_path.exists():
        return {"sections": None, "subsections": None, "words": None, "from_tex": False, "citation_runs": None,
                "cited_keys": []}
    body = tex_path.read_text(encoding="utf-8", errors="replace").split(r"\begin{document}")[-1]
    body = re.split(r"\\begin\{thebibliography\}|\\bibliography\{|\\section\*?\{References\}", body)[0]
    secs = len(re.findall(r"^\\section\{", body, re.M))
    subs = len(re.findall(r"^\\subsection\{", body, re.M))
    cite_runs = re.findall(r"\\cite[tp]?\{([^}]*)\}", body)
    cited = []
    for run in cite_runs:
        cited += [k.strip() for k in run.split(",") if k.strip()]
    words = len(re.findall(r"[A-Za-z][A-Za-z'-]*",
                           re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^}]*\})?", " ", body)))
    return {"sections": secs, "subsections": subs, "words": words, "from_tex": True,
            "citation_runs": len(cite_runs), "cited_keys": sorted(set(cited))}


def parse_bib(bib_path: Path) -> list[dict]:
    """references.bib → [{key, title, id_type, id, match_key}]. match_key 는 평가 규약의 매칭 키
    (doi 소문자 ∨ 10.48550/arxiv.<base id>)."""
    if not bib_path.exists():
        return []
    text = bib_path.read_text(encoding="utf-8", errors="replace")
    entries = []
    for chunk in re.split(r"^@", text, flags=re.M)[1:]:
        m = re.match(r"\w+\s*\{\s*([^,\s]+)\s*,", chunk)
        if not m:
            continue
        key = m.group(1)
        fields = {}
        for fm in re.finditer(r"^\s*(\w+)\s*=\s*\{(.*)\}\s*,?\s*$", chunk, re.M):
            fields[fm.group(1).lower()] = fm.group(2).strip()
        id_type, pid = "other", None
        if fields.get("eprint"):
            id_type, pid = "arxiv", arxiv_base(fields["eprint"])
        elif fields.get("doi"):
            id_type, pid = "doi", fields["doi"].lower()
        elif "arxiv.org/abs/" in fields.get("url", ""):
            id_type, pid = "arxiv", arxiv_base(fields["url"].split("arxiv.org/abs/")[-1])
        elif "doi.org/" in fields.get("url", ""):
            id_type, pid = "doi", fields["url"].split("doi.org/")[-1].lower()
        match_key = None
        if id_type == "arxiv":
            match_key = ARXIV_DOI_PREFIX + pid.lower()
        elif id_type == "doi":
            match_key = pid
        entries.append({"key": key, "title": fields.get("title", ""), "id_type": id_type, "id": pid,
                        "match_key": match_key})
    return entries


def pdf_pages(pdf: Path) -> int | None:
    if not pdf.exists():
        return None
    try:
        out = subprocess.check_output(["pdfinfo", str(pdf)], text=True, stderr=subprocess.DEVNULL)
        m = re.search(r"^Pages:\s+(\d+)", out, re.M)
        return int(m.group(1)) if m else None
    except Exception:
        return None


# --------------------------------------------------------------------------- GT / leak
def load_topics() -> list[dict]:
    p = KISTI_ROOT / "data" / "topics.kisti.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def find_topic(title: str) -> dict | None:
    want = norm_title(title)
    for t in load_topics():
        if norm_title(t["title"]) == want:
            return t
    return None


def gt_in_view_keys(slug: str) -> list[str]:
    p = KISTI_ROOT / "candidates" / "gap_to_80_refs.jsonl"
    if not p.exists():
        return []
    keys = []
    for l in p.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
        if r.get("slug") == slug and r.get("tier") == "in_view" and r.get("kisti_doi"):
            keys.append(r["kisti_doi"].lower())
    return sorted(set(keys))


def gt_title(domain: str, slug: str) -> str | None:
    r = read_json(KISTI_ROOT / "candidates" / domain / slug / "refs.json")
    try:
        return r["candidate"]["gt"]["title"]
    except (TypeError, KeyError):
        return None


def load_exclude_keys(view: str) -> list[tuple[str, str]]:
    p = KISTI_ROOT / "data" / "views" / view / "exclude_keys.txt"
    if not p.exists():
        return []
    out = []
    for l in p.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        parts = l.split("\t")
        out.append((parts[0].strip().lower(), parts[1].strip() if len(parts) > 1 else ""))
    return out


def leak_check(view: str, ref_entries: list[dict], texts: str, gt_title_str: str | None) -> dict:
    """GT 본체·twin 키(38개)가 refs 매칭 키·본문/bib 원문에 0회인지, GT 제목이 bib title 에 없는지.
    제목 검사는 bib 에만 한다 — topic 문자열이 GT 제목에서 왔으므로 본문에는 당연히 나온다."""
    keys = load_exclude_keys(view)
    ref_match = {e["match_key"] for e in ref_entries if e["match_key"]}
    low = texts.lower()
    in_refs, in_text = [], []
    for key, reason in keys:
        if key in ref_match:
            in_refs.append({"key": key, "reason": reason})
        needles = [key]
        if key.startswith(ARXIV_DOI_PREFIX):
            needles.append(key[len(ARXIV_DOI_PREFIX):])       # 맨 arXiv id (2211.01671)
        if any(n in low for n in needles):
            in_text.append({"key": key, "reason": reason})
    title_hits = []
    if gt_title_str:
        g = norm_title(gt_title_str)
        for e in ref_entries:
            b = norm_title(e["title"])
            if len(b) >= 30 and (g in b or b in g):
                title_hits.append({"key": e["key"], "title": e["title"]})
    return {"exclude_keys": len(keys), "ids_in_refs": in_refs, "ids_in_text": in_text,
            "gt_title_in_bib": title_hits,
            "clean": not in_refs and not in_text and not title_hits}


# --------------------------------------------------------------------------- build
def build(task_id: str, request_stats: Path | None = None) -> dict:
    task_dir = OUTPUTS / task_id
    if not task_dir.is_dir():
        sys.exit(f"no such task dir: {task_dir}")
    metrics = task_dir / "metrics"
    cfg = read_json(task_dir / "tmp_config.json", {}) or {}
    run_args = read_json(metrics / "run_args.json", {}) or {}

    # ---- env (실행 시점 스냅샷 우선)
    env = read_json(metrics / "env.snapshot.json")
    env_source = "metrics/env.snapshot.json"
    if env is None:
        # 실행 시점 스냅샷이 없으면(run_kisti.py 를 거치지 않은 과거 실행) 현재 .env 를 쓰지 않는다 —
        # 그 값은 그 실행의 조건이 아니다. 모델·temperature 등은 null 로 두고 출처만 남긴다.
        env = {}
        env_source = "none (run_kisti.py 를 거치지 않은 실행 — 모델·프로파일 필드는 기록 없음)"
    env_sel = {k: env.get(k) for k in ENV_KEYS_OF_INTEREST}
    view = env_sel.get("KISTI_VIEW") or "kisti-2512"      # 누수 검사 키의 출처 (기본 view)
    data_source = env_sel.get("SURVEYX_DATA_SOURCE")

    # ---- 토큰·시간
    tm = read_json(metrics / "token_monitor.json", {}) or {}
    stages = {}
    for label, models in tm.items():
        agg = {"in_tokens": 0, "out_tokens": 0, "cost_usd": 0.0}
        for _model, m in models.items():
            agg["in_tokens"] += int(m.get("input_tokens", 0))
            agg["out_tokens"] += int(m.get("output_tokens", 0))
            agg["cost_usd"] += float(m.get("total_cost", 0.0))
        agg["cost_usd"] = round(agg["cost_usd"], 4)
        stages[label] = agg
    cost_total = round(sum(s["cost_usd"] for s in stages.values()), 4)

    times = read_json(metrics / "time_monitor.json", {}) or {}
    fmt = "%Y-%m-%d %H:%M:%S"
    starts, ends = [], []
    stage_durations = {}
    for label, t in times.items():
        stage_durations[label] = t.get("duration")
        if label == "compile latex":
            continue
        try:
            starts.append(datetime.strptime(t["start"], fmt))
            ends.append(datetime.strptime(t["end"], fmt))
        except (KeyError, ValueError):
            pass
    duration_sec = int((max(ends) - min(starts)).total_seconds()) if starts and ends else None

    # ---- 요청 기록
    rs_path = request_stats or (metrics / "request_stats.txt")
    req = parse_request_stats(rs_path)

    # ---- 산출물
    tex = task_dir / "latex" / "survey.tex"
    bib = task_dir / "latex" / "references.bib"
    st = measure_tex(tex)
    cited_keys = st.pop("cited_keys")
    refs = parse_bib(bib)
    bib_keys = {e["key"] for e in refs}
    id_types = Counter(e["id_type"] for e in refs)
    structure = {
        "sections": st["sections"], "subsections": st["subsections"], "words": st["words"],
        "from_tex": st["from_tex"],
        "references": len(refs),
        "references_cited": len(set(cited_keys) & bib_keys),
        "citation_runs": st["citation_runs"],
        "pdf_pages": pdf_pages(task_dir / "survey.pdf"),
    }
    draft_per_sub = (round(req["draft_calls"] / st["subsections"], 2)
                     if req.get("available") and st["subsections"] else None)

    # ---- GT · recall/precision · 누수
    topic = find_topic(cfg.get("title", ""))
    gt = None
    score = None
    gt_title_str = None
    if topic:
        gt_title_str = gt_title(topic["domain"], topic["slug"])
        in_view = gt_in_view_keys(topic["slug"])
        ref_match = sorted({e["match_key"] for e in refs if e["match_key"]})
        hits = sorted(set(ref_match) & set(in_view))
        gt = {"domain": topic["domain"], "slug": topic["slug"], "gt_doi": topic.get("gt_doi"),
              "gt_title": gt_title_str, "n_gt_refs_eligible": topic.get("n_gt_refs"),
              "n_gt_refs_in_view": len(in_view)}
        score = {
            "denominator": "GT refs ∩ in_view (candidates/gap_to_80_refs.jsonl tier==in_view)",
            "refs_identifiable": len(ref_match),
            "hits": len(hits),
            "recall": round(len(hits) / len(in_view), 4) if in_view else None,
            "precision": round(len(hits) / len(ref_match), 4) if ref_match else None,
            "hit_keys": hits,
        }
    texts = ""
    for p in (tex, bib):
        if p.exists():
            texts += p.read_text(encoding="utf-8", errors="replace") + "\n"
    leak = leak_check(view, refs, texts, gt_title_str)

    # ---- provenance
    view_dir = KISTI_ROOT / "data" / "views" / view
    package = None
    try:
        sys.path.insert(0, str(ADAPTER_DIR))
        from common import config as _acfg  # type: ignore
        package = _acfg.PACKAGE_VERSION
    except Exception:
        pass
    credits = read_json(metrics / "credits.json")

    run = {
        "schema": "surveyx.run.v1",
        "generated_at": datetime.now().strftime(fmt),
        "task_id": task_id,
        "topic": cfg.get("title"),
        "key_words_expanded": cfg.get("key_words"),
        "args": run_args.get("args"),
        "status": run_args.get("status"),
        "returncode": run_args.get("returncode"),
        "started_at": run_args.get("started_at"),
        "ended_at": run_args.get("ended_at"),
        "log_path": run_args.get("log_path"),
        "model": env_sel.get("SURVEYX_DEFAULT_MODEL"),
        "advanced_model": env_sel.get("SURVEYX_ADVANCED_MODEL"),
        "provider_pin": env_sel.get("OPENROUTER_PROVIDER_ONLY"),
        "allow_fallbacks": env_sel.get("OPENROUTER_ALLOW_FALLBACKS"),
        "temperature": env_sel.get("SURVEYX_TEMPERATURE") or "원 설정 (0.5 / outline 0.3)",
        "max_tokens": env_sel.get("SURVEYX_MAX_TOKENS") or None,
        "retry_truncated": env_sel.get("SURVEYX_RETRY_TRUNCATED"),
        "max_truncated_retry": env_sel.get("SURVEYX_MAX_TRUNCATED_RETRY"),
        "env_source": env_source,
        "data_source": data_source,
        "view": view,
        "view_manifest_sha256": sha256_file(view_dir / "view_manifest.json"),
        "package": package,
        "fulltext_limit": env_sel.get("KISTI_FULLTEXT_LIMIT"),
        "git": {"surveyx": git_state(REPO_ROOT), "kisti_data": git_state(KISTI_ROOT)},
        "stages": stages,
        "stage_durations_sec": stage_durations,
        "cost_total_usd": cost_total,
        "cost_measured_usd": (credits or {}).get("measured_usd"),
        "duration_sec": duration_sec,
        "requests": {k: v for k, v in req.items() if k != "by_template"},
        "requests_by_template": req.get("by_template"),
        "truncated_calls": req.get("truncated_accepted"),
        "truncation_retries": req.get("truncated_discarded"),
        "draft_calls_per_subsection": draft_per_sub,
        "structure": structure,
        "refs": {"arxiv": id_types["arxiv"], "doi": id_types["doi"], "other": id_types["other"],
                 "match_keys": sorted({e["match_key"] for e in refs if e["match_key"]})},
        "gt": gt,
        "score": score,
        "leak": leak,
    }
    return run


def write_run(task_id: str, request_stats: Path | None = None) -> Path:
    run = build(task_id, request_stats)
    out = OUTPUTS / task_id / "run.json"
    out.write_text(json.dumps(run, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


# --------------------------------------------------------------------------- table
def table() -> str:
    rows = []
    for p in sorted(glob.glob(str(OUTPUTS / "*" / "run.json"))):
        r = read_json(Path(p), {})
        s, rq, sc, lk = r.get("structure", {}), r.get("requests", {}), r.get("score") or {}, r.get("leak", {})
        dur = f"{r['duration_sec'] // 60}m" if r.get("duration_sec") else "-"
        rows.append("| {tid} | {topic} | {cost} | {meas} | {dur} | {sec}/{sub} · {w} | {refs} ({ax}/{doi}) | {dps} | {td}/{ta} | {e429} | {rec}/{prec} (n={n}) | {leak} |".format(
            tid=r.get("task_id"), topic=(r.get("topic") or "")[:40],
            cost=f"${r.get('cost_total_usd', 0):.2f}",
            meas=(f"${r['cost_measured_usd']:.2f}" if r.get("cost_measured_usd") is not None else "-"),
            dur=dur, sec=s.get("sections"), sub=s.get("subsections"), w=s.get("words"),
            refs=s.get("references"), ax=r.get("refs", {}).get("arxiv"), doi=r.get("refs", {}).get("doi"),
            dps=r.get("draft_calls_per_subsection"),
            td=rq.get("truncated_discarded"), ta=rq.get("truncated_accepted"),
            e429=(rq.get("http_errors") or {}).get("429", 0),
            rec=(f"{sc['recall'] * 100:.1f}%" if sc.get("recall") is not None else "-"),
            prec=(f"{sc['precision'] * 100:.1f}%" if sc.get("precision") is not None else "-"),
            n=r.get("gt", {}).get("n_gt_refs_in_view") if r.get("gt") else "-",
            leak=("clean" if lk.get("clean") else "LEAK"),
        ))
    head = ("| task_id | topic | cost(TM) | cost(실측) | 소요 | sec/sub · words | refs (arXiv/DOI) | draft/sub "
            "| 잘림 폐기/채택 | 429 | recall/precision | 누수 |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
    return head + "\n" + "\n".join(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task_id", help="outputs/<task_id>")
    ap.add_argument("--request_stats", help="요청 기록 파일 경로 (기본 outputs/<task_id>/metrics/request_stats.txt)")
    ap.add_argument("--table", action="store_true", help="outputs/*/run.json 집계 표")
    ap.add_argument("--print", action="store_true", help="run.json 을 stdout 에도 출력")
    args = ap.parse_args()
    if args.table:
        print(table())
        return
    if not args.task_id:
        ap.error("--task_id 또는 --table")
    out = write_run(args.task_id, Path(args.request_stats) if args.request_stats else None)
    print(f"wrote {out}")
    if args.print:
        print(out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
