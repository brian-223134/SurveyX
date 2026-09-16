"""pseudo survey pipeline — tasks/full_run.py 를 가짜로 대신해 runner → 기록 체인을 끝까지 돌리는 mock 테스트.

실행:  /data2/chanjoong/miniforge3/envs/surveyx/bin/python -m unittest tests.test_pseudo_pipeline -v

무엇을 검증하나
  scripts/run_kisti.py(topic→slug, KISTI_TOPIC_ID 주입, 정책 사전 점검, metrics 기록)
  → [pseudo full_run: 검색(정책 안) → 필터 → 게이트 → bib/tex/monitor/provenance 산출]
  → scripts/collect_run.py(run.json: 구조·refs·recall/precision·누수·retrieval_policy·policy_check)
  의 결과 run.json 이 아래 EXPECTED_* 와 일치하는지. LLM·DuckDB·실 corpus·kisti_data adapter 는 전혀 쓰지 않는다
  (adapter 는 같은 인터페이스의 가짜 모듈을 tmp 에 써서 sys.path 에 넣는다).

입력 형태(실제 파일 형식을 그대로 축소한 것)
  EXAMPLE_TOPIC        kisti_data/data/topics.kisti.jsonl 의 한 행
  EXAMPLE_POLICY_ROW   AutoSurvey/data/topic_policy.<view>.jsonl 의 한 행
  EXAMPLE_SIDECAR      data/views/<view>/paper_dates.json ({"meta", "dates": {id: "YYYY[-MM[-DD]]"}})
  EXAMPLE_GT_REFS      candidates/gap_to_80_refs.jsonl (tier == in_view 가 분모)
  EXAMPLE_CORPUS       view papers.parquet 의 레코드 (id 규칙 B: arXiv base id 또는 소문자 DOI)
출력 형태
  EXPECTED_RUN_WITH_POLICY / EXPECTED_RUN_NO_POLICY  run.json 의 결정적 필드 부분집합 (시각·git·경로는 제외)

시나리오
  cutoff 2022-11-03. corpus 5편 중 4편이 cutoff 이전, 1편(2303.01234)이 이후. GT refs 3편이 view 안(in_view).
  pseudo pipeline 은 검색 밖 경로를 흉내 내 2303.01234 를 필터 통과 풀에 끼워 넣는다 →
    정책 on : 검색 4편(2303 제외) + 끼워 넣기 1 → 게이트가 1편 차단 → bib 4편, 사후 재판정 위반 0, recall 2/3
    정책 off: 검색 5편 → 게이트 무동작 → bib 5편(2303 포함), retrieval_policy null, 비교 대상 아님
"""

import hashlib
import json
import shutil
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
for p in (REPO_ROOT, REPO_ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import collect_run  # noqa: E402
import run_kisti  # noqa: E402
from tests.test_collect_run import record_prefix  # noqa: E402  (실제 프롬프트 템플릿 prefix → 요청 기록 매칭)

# =============================================================================== 예시 입력
VIEW = "kisti-2608"
TITLE = "Visual Adversarial Attacks and Defenses in the Physical World"
SLUG, DOMAIN = "physical-adversarial-attacks", "security"
GT_DOI, TWIN = "10.1145/3793659", "2211.01671"
CUTOFF = "2022-11-03"

EXAMPLE_TOPIC = {
    "title": TITLE, "n_gt_refs": 150, "gt_doi": GT_DOI, "domain": DOMAIN, "slug": SLUG,
    "n_gt_refs_source": "kisti_eligible_anycs", "retrieval_cutoff_at": CUTOFF,
    "n_gt_refs_cutoff": 3, "n_gt_refs_cutoff_pool": 4, "n_gt_refs_cutoff_view": "kisti-2608 c1a0c6b3",
    "n_gt_refs_cutoff_rule": "identifiable ∧ upper_bound(ref date) < retrieval_cutoff_at ∧ in view ∧ upper_bound(record date) < retrieval_cutoff_at",
}

EXAMPLE_POLICY_ROW = {
    "topic_id": SLUG, "topic": TITLE, "domain": DOMAIN, "gt_doi": GT_DOI, "gt_arxiv_id": None, "twin_arxiv_id": TWIN,
    "gt_first_public_at": CUTOFF, "gt_first_public_source": f"arxiv:{TWIN} v1 published (twin)",
    "retrieval_cutoff_at": CUTOFF, "exclude_ids": [GT_DOI, TWIN],
    "corpus_snapshot_id": "kisti-2608 papers.parquet sha256:c1a0c6b3" + "0" * 56, "view": VIEW, "status": "ok",
}

EXAMPLE_VIEW_MANIFEST = {
    "view_name": VIEW, "created_at": "2026-09-14T13:18:56+00:00", "counts": {"view_papers": 5},
    "files_sha256": {"papers.parquet": "c1a0c6b3" + "0" * 56},
}

# 레코드 공개일: day / month / year — 문자열 길이 = 정밀도. 판정은 upper_bound(date) < cutoff.
EXAMPLE_SIDECAR = {
    "meta": {"created_at": "2026-09-14T13:26:00Z", "by_precision": {"day": 2, "month": 3}, "view_papers_sha256": "c1a0c6b3"},
    "dates": {
        "1712.09665": "2017-12",                     # arXiv YYMM (month)
        "10.1109/cvpr.2018.00175": "2018-06-18",     # OpenAlex publication_date (day)
        "1906.11897": "2019-06",
        "10.1145/3319535.3354265": "2019-11-06",
        "2303.01234": "2023-03",                     # cutoff 이후 → 정책이 막는다
        TWIN: "2022-11",                             # GT 선행판 — exclude_ids 이자 2022-11-30 ≥ cutoff
    },
}

EXAMPLE_GT_REFS = [   # tier == in_view 3편 = 분모. 2303.01234 는 cutoff 이후(post) 라 분모 밖
    {"slug": SLUG, "tier": "in_view", "key": "1712.09665", "kisti_doi": "10.48550/arxiv.1712.09665", "record_date": "2017-12", "allowed": True},
    {"slug": SLUG, "tier": "in_view", "key": "10.1109/cvpr.2018.00175", "kisti_doi": "10.1109/cvpr.2018.00175", "record_date": "2018-06-18", "allowed": True},
    {"slug": SLUG, "tier": "in_view", "key": "1906.11897", "kisti_doi": "10.48550/arxiv.1906.11897", "record_date": "2019-06", "allowed": True},
    {"slug": SLUG, "tier": "post", "key": "2303.01234", "kisti_doi": "10.48550/arxiv.2303.01234", "record_date": "2023-03", "allowed": False},
    {"slug": "other-slug", "tier": "in_view", "key": "10.1000/other", "kisti_doi": "10.1000/other", "allowed": True},
]

EXAMPLE_CORPUS = [   # view papers.parquet 레코드 (GT 본체·twin 은 view 가 이미 뺐다)
    {"id": "1712.09665", "doi": "10.48550/arxiv.1712.09665", "arxiv_id": "1712.09665", "year": 2017, "cited_by_count": 900,
     "title": "Adversarial Patch", "abstract": "We present a method to create universal, robust, targeted adversarial image patches in the real world."},
    {"id": "10.1109/cvpr.2018.00175", "doi": "10.1109/cvpr.2018.00175", "arxiv_id": None, "year": 2018, "cited_by_count": 800,
     "title": "Robust Physical-World Attacks on Deep Learning Visual Classification", "abstract": "Physical adversarial examples on road signs fool classifiers."},
    {"id": "1906.11897", "doi": "10.48550/arxiv.1906.11897", "arxiv_id": "1906.11897", "year": 2019, "cited_by_count": 115,
     "title": "On Physical Adversarial Patches for Object Detection", "abstract": "Adversarial patches printed and placed in the scene attack detectors."},
    {"id": "10.1145/3319535.3354265", "doi": "10.1145/3319535.3354265", "arxiv_id": None, "year": 2019, "cited_by_count": 60,
     "title": "Seeing isn't Believing: Towards More Robust Adversarial Attack Against Real World Object Detectors",
     "abstract": "We propose adversarial attacks that remain effective under physical transformations."},
    {"id": "2303.01234", "doi": "10.48550/arxiv.2303.01234", "arxiv_id": "2303.01234", "year": 2023, "cited_by_count": 5,
     "title": "Physical Adversarial Attacks Revisited", "abstract": "A 2023 paper on physical adversarial attacks that must not be retrieved for a 2022 cutoff."},
]
EXAMPLE_AUTHORS = {"1712.09665": ["Tom B. Brown", "Dandelion Mané"], "10.1109/cvpr.2018.00175": ["Kevin Eykholt"]}
STRAY_ID = "2303.01234"              # 검색 밖 경로가 끼워 넣는 id (cutoff 이후)
CITED_IDS = ["1712.09665", "10.1109/cvpr.2018.00175", "10.1145/3319535.3354265"]   # 본문이 인용하는 3편 (GT 2 + 비GT 1)

# kisti_data/adapter/common 의 대역 — run_kisti.check_policy · collect_run.policy_check 가 쓰는 함수만 같은 규칙으로
FAKE_ADAPTER_SOURCES = {
    "common/__init__.py": "",
    "common/config.py": 'PACKAGE_VERSION = "pseudo_sdl"\n',
    "common/retrieval_policy.py": textwrap.dedent('''
        import calendar, datetime, json
        from pathlib import Path

        def upper_bound(s):
            if not s:
                return None
            parts = [int(x) for x in str(s).split("-")]
            if len(parts) == 1:
                return datetime.date(parts[0], 12, 31)
            if len(parts) == 2:
                return datetime.date(parts[0], parts[1], calendar.monthrange(parts[0], parts[1])[1])
            return datetime.date(*parts)

        def is_allowed(date_str, cutoff):
            c = cutoff if isinstance(cutoff, datetime.date) else datetime.date.fromisoformat(cutoff)
            ub = upper_bound(date_str)
            return ub is not None and ub < c

        def allowed_ids(dates, cutoff, exclude_ids=()):
            ex = {str(e).lower() for e in exclude_ids}
            return {pid for pid, d in dates.items() if pid.lower() not in ex and is_allowed(d, cutoff)}

        def find_topic_policy(view=None):
            p = Path(__file__).resolve().parent.parent / f"topic_policy.{view}.jsonl"
            return p if p.exists() else None

        def load_topic_policy(path):
            rows = {}
            for line in Path(path).read_text().splitlines():
                if line.strip() and not line.startswith("#"):
                    r = json.loads(line); rows[r["topic_id"]] = r
            return rows

        def load_paper_dates(view_dir_or_file):
            p = Path(view_dir_or_file)
            if p.is_dir():
                p = p / "paper_dates.json"
            if not p.exists():
                return {}, {}
            obj = json.loads(p.read_text())
            return obj["dates"], obj.get("meta", {})
    '''),
}

# =============================================================================== 기대 출력 (run.json 부분집합)
_ALLOWED_IDS = sorted(pid for pid in EXAMPLE_SIDECAR["dates"]
                      if pid not in EXAMPLE_POLICY_ROW["exclude_ids"] and pid != STRAY_ID)   # 4편
ALLOWED_SHA256 = hashlib.sha256("\n".join(_ALLOWED_IDS).encode()).hexdigest()

EXPECTED_RUN_WITH_POLICY = {
    "schema": "surveyx.run.v1",
    "topic": TITLE,
    "args": f'--title "{TITLE}" --key_words "{TITLE}"',
    "status": "ok",
    "returncode": 0,
    "data_source": "kisti",
    "view": VIEW,
    "view_version": "c1a0c6b3",
    "view_version_label": "c1a0c6b3 / 2026-09-14T13:18:56Z",
    "view_papers": 5,
    "package": "pseudo_sdl",
    "fetcher_provenance": {"data_source": "kisti", "view": VIEW, "package": "pseudo_sdl"},
    "retrieval_policy": {
        "topic_id": SLUG, "retrieval_cutoff_at": CUTOFF, "exclude_ids": [GT_DOI, TWIN],
        "allowed": 4, "total": 6, "excluded": {"exclude_id": 1, "after_cutoff_month": 1},
        "allowed_sha256": ALLOWED_SHA256,
        "rule": "upper_bound(record date) < cutoff ∧ id ∉ exclude_ids (search runs inside the allowed set)",
        "paper_dates": {"created_at": "2026-09-14T13:26:00Z"},
    },
    "policy_gate": {"stage": "after filter, before fulltext", "checked": 5, "blocked": 1, "blocked_ids": [STRAY_ID]},
    "policy_check": {"cutoff": CUTOFF, "checked": 4, "violations": 0, "violation_ids": [], "not_in_sidecar": 0},
    "policy_comparable": True,
    "policy_note": "ok",
    "cost_total_usd": 0.75,
    "cost_measured_usd": 0.5,
    "requests": {"available": True, "records": 5, "ok": 3, "http_errors": {"429": 1}, "truncated_discarded": 1,
                 "truncated_accepted": 0, "draft_calls": 3},
    "truncation_retries": 1,
    "truncated_calls": 0,
    "draft_calls_per_subsection": 1.5,
    "structure": {"sections": 2, "subsections": 2, "from_tex": True, "references": 3, "references_bib_total": 4,
                  "citation_runs": 3, "pdf_pages": None},
    "refs": {"arxiv": 1, "doi": 2, "other": 0,
             "match_keys": ["10.1109/cvpr.2018.00175", "10.1145/3319535.3354265", "10.48550/arxiv.1712.09665"]},
    "gt": {"domain": DOMAIN, "slug": SLUG, "gt_doi": GT_DOI, "n_gt_refs_eligible": 150,
           "retrieval_cutoff_at": CUTOFF, "n_gt_refs_cutoff": 3, "n_gt_refs_cutoff_view": "kisti-2608 c1a0c6b3",
           "n_gt_refs_in_view": 3},
    "score": {"denominator_matches_topics": True, "refs_identifiable": 3, "hits": 2, "recall": 0.6667, "precision": 0.6667,
              "hit_keys": ["10.1109/cvpr.2018.00175", "10.48550/arxiv.1712.09665"]},
    "leak": {"exclude_keys": 2, "ids_in_refs": [], "ids_in_text": [], "gt_title_in_bib": [], "clean": True},
}

EXPECTED_RUN_NO_POLICY = {
    "status": "ok",
    "retrieval_policy": None,
    "policy_gate": {"checked": 5, "blocked": 0, "blocked_ids": []},
    "policy_check": None,
    "policy_comparable": False,
    "policy_note": "정책 없음 — KISTI_TOPIC_ID 미설정 실행 (2026-09-14 규약 비교 대상 아님)",
    "structure": {"references": 3, "references_bib_total": 5},        # 2303.01234 가 풀(bib)에 들어온다
    "score": {"hits": 2, "recall": 0.6667, "precision": 0.6667},
    "leak": {"clean": True},
}


# =============================================================================== pseudo pipeline
def make_bibtex(rec: dict, authors: list[str] | None) -> str:
    """kisti_fetcher.make_bibtex 와 같은 형식 (첫 줄 '@article{key,' · arXiv 는 eprint · DOI 는 doi/url)."""
    import re
    arxiv = bool(rec["arxiv_id"])
    key = ("arxiv" if arxiv else "doi") + re.sub(r"[^0-9A-Za-z]", "_", rec["id"])
    lines = [f"@article{{{key},", f"  title={{{rec['title']}}},"]
    if authors:
        lines.append(f"  author={{{' and '.join(authors)}}},")
    lines.append(f"  year={{{rec['year']}}},")
    if arxiv:
        lines += [f"  journal={{arXiv preprint arXiv:{rec['id']}}},", f"  eprint={{{rec['id']}}},",
                  "  archivePrefix={arXiv},", f"  url={{http://arxiv.org/abs/{rec['id']}}}"]
    else:
        lines += [f"  doi={{{rec['doi']}}},", f"  url={{https://doi.org/{rec['doi']}}}"]
    lines.append("}")
    return "\n".join(lines)


class PseudoKistiFetcher:
    """KistiFetcher 의 대역 — 같은 인터페이스(search_on_arxiv · fill_md_text · is_allowed · provenance).
    KISTI_TOPIC_ID 가 있으면 정책 파일·sidecar 로 허용 집합을 만들고 검색이 그 **안에서만** 돈다."""

    def __init__(self, env: dict, view_dir: Path, policy_path: Path):
        self.view_name = env.get("KISTI_VIEW", "kisti-2512")
        self.provenance = {"data_source": "kisti", "view": self.view_name,
                           "view_manifest_sha256": hashlib.sha256((view_dir / "view_manifest.json").read_bytes()).hexdigest(),
                           "package": "pseudo_sdl"}
        self._allowed = None
        topic_id = env.get("KISTI_TOPIC_ID")
        if topic_id:
            from common.retrieval_policy import allowed_ids, load_paper_dates, load_topic_policy  # 가짜 adapter
            row = load_topic_policy(policy_path)[topic_id]
            dates, meta = load_paper_dates(view_dir)
            cutoff, excl = row["retrieval_cutoff_at"], row["exclude_ids"]
            self._allowed = allowed_ids(dates, cutoff, excl)
            ex = {e.lower() for e in excl}
            excluded = {}
            for pid, d in dates.items():
                if pid.lower() in ex:
                    excluded["exclude_id"] = excluded.get("exclude_id", 0) + 1
                elif pid not in self._allowed:
                    k = "after_cutoff_" + {1: "year", 2: "month", 3: "day"}[len(d.split("-"))]
                    excluded[k] = excluded.get(k, 0) + 1
            self.provenance["retrieval_policy"] = {
                "topic_id": topic_id, "topic": row.get("topic"), "retrieval_cutoff_at": cutoff,
                "gt_first_public_source": row.get("gt_first_public_source"), "exclude_ids": list(excl),
                "policy_file": str(policy_path),
                "rule": "upper_bound(record date) < cutoff ∧ id ∉ exclude_ids (search runs inside the allowed set)",
                "allowed": len(self._allowed), "total": len(dates), "excluded": excluded,
                "allowed_sha256": hashlib.sha256("\n".join(sorted(self._allowed)).encode()).hexdigest(),
                "sha256_rule": "sha256('\\n'.join(sorted(allowed_ids)))",
                "paper_dates": {k: meta.get(k) for k in ("created_at", "by_precision", "view_papers_sha256")},
            }

    def is_allowed(self, pid: str) -> bool:
        return True if self._allowed is None else pid in self._allowed

    def _record(self, rec: dict) -> dict:
        return {"_id": rec["id"], "detail_id": (f"arXiv:{rec['id']}" if rec["arxiv_id"] else f"doi:{rec['doi']}"),
                "arxiv_id": rec["arxiv_id"], "doi": rec["doi"], "title": rec["title"], "abstract": rec["abstract"],
                "year": rec["year"], "citation_count": rec["cited_by_count"], "from": "kisti",
                "reference": make_bibtex(rec, EXAMPLE_AUTHORS.get(rec["id"]))}

    def search_on_arxiv(self, key_words: str) -> list[dict]:
        """쉼표 구분 키워드 각각 title/abstract 부분 일치(대소문자 무시), 허용 집합 안에서, cited_by_count 내림차순."""
        id2paper = {}
        for kw in [k.strip().lower() for k in key_words.split(",") if k.strip()]:
            hits = [r for r in EXAMPLE_CORPUS
                    if (kw in r["title"].lower() or kw in r["abstract"].lower()) and self.is_allowed(r["id"])]
            for r in sorted(hits, key=lambda r: (-r["cited_by_count"], r["id"])):
                id2paper[r["id"]] = self._record(r)
        return list(id2paper.values())

    def fill_md_text(self, papers: list[dict]) -> list[dict]:
        for p in papers:
            if self.is_allowed(p["_id"]):
                p["md_text"] = f"# {p['title']}\n\n{p['abstract']}\n"
        return papers


class PseudoSurveyPipeline:
    """tasks/full_run.py 의 대역. run_kisti.run_topic 이 부르는 subprocess.run 자리에 들어가 같은 산출물 배치를 쓴다:
    tmp_config.json · metrics/{fetcher_provenance,token_monitor,time_monitor}.json · outputs/tmp/request_stats.txt ·
    latex/{survey.tex,references.bib}. preprocessor.py 의 provenance 기록·게이트와 같은 파일·키를 쓴다."""

    def __init__(self, outputs: Path, view_dir: Path, policy_path: Path, request_stats: Path):
        self.outputs, self.view_dir, self.policy_path, self.request_stats = outputs, view_dir, policy_path, request_stats
        self.calls = []
        self.bypass_gate = False        # True 면 게이트가 없는 파이프라인을 흉내 낸다 (사후 재판정 테스트용)

    def __call__(self, cmd, **kw):
        env = kw["env"]
        title = cmd[cmd.index("--title") + 1]
        key_words = cmd[cmd.index("--key_words") + 1]
        self.calls.append({"cmd": cmd, "env": {k: env.get(k) for k in ("KISTI_VIEW", "KISTI_TOPIC_ID")}})
        # utils.create_tmp_config 와 같은 task_id 규칙. 키워드 확장(LLM)은 하지 않고 "adversarial" 하나만 덧붙인다
        expanded = f"{key_words}, adversarial"
        task_id = datetime.now().strftime("%Y-%m-%d-%H%M_") + expanded[:5].replace(" ", "_")
        task = self.outputs / task_id
        (task / "metrics").mkdir(parents=True)
        (task / "latex").mkdir()
        (task / "tmp_config.json").write_text(json.dumps({"title": title, "key_words": expanded,
                                                            "topic": title, "task_id": task_id}), encoding="utf-8")

        # 1. 리콜 (preprocessor._save_fetcher_provenance 와 같은 기록)
        fetcher = PseudoKistiFetcher(env, self.view_dir, self.policy_path)
        prov_path = task / "metrics" / "fetcher_provenance.json"
        prov_path.write_text(json.dumps(fetcher.provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        pool = fetcher.search_on_arxiv(expanded)
        # 2. 필터 — 전부 통과. 그리고 검색 밖 경로(예: 인용 문자열 → id)를 흉내 내 cutoff 이후 논문을 끼워 넣는다
        if STRAY_ID not in {p["_id"] for p in pool}:
            pool.append(fetcher._record(next(r for r in EXAMPLE_CORPUS if r["id"] == STRAY_ID)))
        # 2.4 게이트 (preprocessor._apply_policy_gate 와 같은 규칙·기록)
        if self.bypass_gate:
            blocked, kept = [], list(pool)
        else:
            blocked = [p["_id"] for p in pool if not fetcher.is_allowed(p["_id"])]
            kept = [p for p in pool if fetcher.is_allowed(p["_id"])]
        prov = json.loads(prov_path.read_text(encoding="utf-8"))
        prov["policy_gate"] = {"stage": "after filter, before fulltext", "checked": len(pool),
                               "blocked": len(blocked), "blocked_ids": blocked[:50]}
        prov_path.write_text(json.dumps(prov, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        kept = fetcher.fill_md_text(kept)

        # 3~6. 정제·outline·본문·latex — bib 은 풀 전편, 본문은 CITED_IDS 만 인용 (unsrt: 인용된 것만 참고문헌)
        (task / "latex" / "references.bib").write_text("\n".join(p["reference"] for p in kept) + "\n", encoding="utf-8")
        key_of = {p["_id"]: p["reference"].split("{", 1)[1].split(",", 1)[0] for p in kept}
        cite = [key_of[i] for i in CITED_IDS if i in key_of]
        (task / "latex" / "survey.tex").write_text(textwrap.dedent(f"""
            \\documentclass{{article}}
            \\begin{{document}}
            \\section{{Introduction}}
            Adversarial patches fool detectors in the physical world \\cite{{{cite[0]}}}.
            \\subsection{{Scope}}
            We cover printable attacks on road signs \\cite{{{cite[1]}}}.
            \\section{{Attacks}}
            \\subsection{{Detector attacks}}
            Physical transformations keep the attack effective \\cite{{{cite[2]}}}.
            \\bibliography{{references}}
            \\end{{document}}
            """), encoding="utf-8")
        (task / "metrics" / "token_monitor.json").write_text(json.dumps({
            "recall paper": {"pseudo-llm": {"input_tokens": 100, "output_tokens": 10, "total_cost": 0.05}},
            "generate content": {"pseudo-llm": {"input_tokens": 1000, "output_tokens": 200, "total_cost": 0.7}},
        }), encoding="utf-8")
        (task / "metrics" / "time_monitor.json").write_text(json.dumps({
            "retrieve paper": {"start": "2026-09-16 10:00:00", "end": "2026-09-16 10:02:00", "duration": 120.0},
            "generate content": {"start": "2026-09-16 10:02:00", "end": "2026-09-16 10:30:00", "duration": 1680.0},
            "compile latex": {"start": "2026-09-16 11:00:00", "end": "2026-09-16 11:00:05", "duration": 5.0},
        }), encoding="utf-8")
        draft = record_prefix("content_generator/fulfill_content.md")
        outline = record_prefix("outline_generator/write_primary_outline.md")
        self.request_stats.parent.mkdir(parents=True, exist_ok=True)
        self.request_stats.write_text("\n".join([          # status 1 정상 · 0 HTTP 오류 · 2 잘림 폐기 · 3 잘림 채택
            f"1||200||{outline}||resp", f"1||200||{draft}||resp", f"2||200||{draft}||cut",
            f"1||200||{draft}||resp", f"0||429||{draft}||err"]) + "\n", encoding="utf-8")
        return mock.Mock(returncode=0)


# =============================================================================== 테스트
def assert_subset(tc: unittest.TestCase, expected, actual, path="run"):
    """expected 의 모든 키/원소가 actual 에 같은 값으로 있는지 (dict 는 재귀, 그 외는 동등)."""
    if isinstance(expected, dict):
        tc.assertIsInstance(actual, dict, path)
        for k, v in expected.items():
            tc.assertIn(k, actual, f"{path}.{k} 없음")
            assert_subset(tc, v, actual[k], f"{path}.{k}")
    else:
        tc.assertEqual(expected, actual, path)


class PseudoPipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.outputs = self.tmp / "outputs"
        self.kisti = self.tmp / "kisti_data"
        self.adapter = self.tmp / "adapter"
        self.request_stats = self.outputs / "tmp" / "request_stats.txt"
        self._write_inputs()
        self._install_fake_adapter()
        for target, name, value in [
            (run_kisti, "OUTPUTS", self.outputs), (run_kisti, "LOG_DIR", self.outputs / "logs"),
            (run_kisti, "REQUEST_STATS", self.request_stats), (run_kisti, "CREDITS_LOG", self.outputs / "credits.log"),
            (run_kisti, "KISTI_ROOT", self.kisti), (run_kisti, "TOPICS", self.kisti / "data" / "topics.kisti.jsonl"),
            (run_kisti, "ADAPTER_DIR", self.adapter),
            (collect_run, "OUTPUTS", self.outputs), (collect_run, "KISTI_ROOT", self.kisti),
            (collect_run, "ADAPTER_DIR", self.adapter),
        ]:
            p = mock.patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)
        import os
        for k in run_kisti.KISTI_ENV_KEYS:
            self.addCleanup(lambda k=k, v=os.environ.get(k): os.environ.update({k: v}) if v else os.environ.pop(k, None))
            os.environ.pop(k, None)
        os.environ["KISTI_VIEW"] = VIEW
        self.pipeline = PseudoSurveyPipeline(self.outputs, self.view_dir, self.policy_path, self.request_stats)

    # ---- 입력 파일 배치 (실제 kisti_data · AutoSurvey/data 의 경로 규칙과 같게)
    def _write_inputs(self):
        self.view_dir = self.kisti / "data" / "views" / VIEW
        self.view_dir.mkdir(parents=True)
        (self.kisti / "data" / "topics.kisti.jsonl").write_text(json.dumps(EXAMPLE_TOPIC) + "\n", encoding="utf-8")
        (self.view_dir / "view_manifest.json").write_text(json.dumps(EXAMPLE_VIEW_MANIFEST), encoding="utf-8")
        (self.view_dir / "papers.parquet").write_bytes(b"")          # 존재 확인용 (pseudo fetcher 는 EXAMPLE_CORPUS 를 읽는다)
        (self.view_dir / "paper_dates.json").write_text(json.dumps(EXAMPLE_SIDECAR), encoding="utf-8")
        (self.view_dir / "exclude_keys.txt").write_text(
            f"{GT_DOI}\tgt:{DOMAIN}/{SLUG}\n10.48550/arxiv.{TWIN}\ttwin:{TWIN}\n", encoding="utf-8")
        cand = self.kisti / "candidates"
        (cand / DOMAIN / SLUG).mkdir(parents=True)
        (cand / DOMAIN / SLUG / "refs.json").write_text(json.dumps(
            {"candidate": {"gt": {"title": TITLE + ": A Survey", "doi": GT_DOI}}}), encoding="utf-8")
        (cand / "gap_to_80_refs.jsonl").write_text("\n".join(json.dumps(r) for r in EXAMPLE_GT_REFS) + "\n", encoding="utf-8")
        self.policy_path = self.adapter / f"topic_policy.{VIEW}.jsonl"     # 가짜 adapter 의 find_topic_policy 가 여기서 찾는다
        self.adapter.mkdir(parents=True)
        self.policy_path.write_text("# pseudo policy\n" + json.dumps(EXAMPLE_POLICY_ROW) + "\n", encoding="utf-8")

    def _install_fake_adapter(self):
        for rel, src in FAKE_ADAPTER_SOURCES.items():
            p = self.adapter / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(src, encoding="utf-8")
        saved = {k: v for k, v in sys.modules.items() if k == "common" or k.startswith("common.")}
        for k in saved:
            del sys.modules[k]
        sys.path.insert(0, str(self.adapter))

        def restore():
            for k in [k for k in sys.modules if k == "common" or k.startswith("common.")]:
                del sys.modules[k]
            sys.modules.update(saved)
            if str(self.adapter) in sys.path:
                sys.path.remove(str(self.adapter))
        self.addCleanup(restore)

    def _run(self, **kwargs) -> dict:
        credits = iter([{"key_used_usd": 10.0}, {"key_used_usd": 10.5}])
        with mock.patch.object(collect_run, "parse_dotenv", return_value={
                "SURVEYX_DATA_SOURCE": "kisti", "SURVEYX_TEMPERATURE": "0.6", "SURVEYX_MAX_TOKENS": "8192",
                "OPENROUTER_PROVIDER_ONLY": "akashml/fp8", "OPENROUTER_API_KEY": "sk-or-…"}), \
                mock.patch.object(run_kisti, "credits_snapshot", side_effect=lambda label: next(credits)), \
                mock.patch.object(run_kisti.subprocess, "run", side_effect=self.pipeline):
            out = run_kisti.run_topic(TITLE, **kwargs)
        self.assertIsNotNone(out)
        return json.loads(out.read_text(encoding="utf-8"))

    # ---- tests
    def test_with_policy_matches_expected_run_json(self):
        run = self._run()
        self.assertEqual(self.pipeline.calls[0]["env"], {"KISTI_VIEW": VIEW, "KISTI_TOPIC_ID": SLUG})
        assert_subset(self, EXPECTED_RUN_WITH_POLICY, run)
        # 기록 파일이 실제 배치대로 남았는지
        m = self.outputs / run["task_id"] / "metrics"
        for f in ("env.snapshot.json", "view.snapshot.json", "credits.json", "run_args.json",
                  "request_stats.txt", "fetcher_provenance.json"):
            self.assertTrue((m / f).exists(), f)
        args = json.loads((m / "run_args.json").read_text(encoding="utf-8"))
        self.assertEqual((args["topic_id"], args["view"], args["policy"]["retrieval_cutoff_at"]), (SLUG, VIEW, CUTOFF))
        self.assertTrue(args["policy"]["policy_file"].endswith(f"topic_policy.{VIEW}.jsonl"))
        self.assertIn(f"| <{CUTOFF} (위반 0) |", collect_run.table())

    def test_without_policy_is_marked_not_comparable(self):
        run = self._run(no_policy=True)
        self.assertEqual(self.pipeline.calls[0]["env"], {"KISTI_VIEW": VIEW, "KISTI_TOPIC_ID": None})
        assert_subset(self, EXPECTED_RUN_NO_POLICY, run)
        self.assertIn("10.48550/arxiv.2303.01234", [e["match_key"] for e in collect_run.parse_bib(
            self.outputs / run["task_id"] / "latex" / "references.bib")])          # cutoff 이후 논문이 풀에 샜다
        self.assertIn("| 없음 (비교 대상 아님) |", collect_run.table())

    def test_policy_check_catches_leak_when_gate_is_bypassed(self):
        """게이트가 없었다면(검색 밖 경로로 들어온 cutoff 이후 논문이 풀에 남았다면) 사후 재판정이 잡아야 한다."""
        self.pipeline.bypass_gate = True
        run = self._run()
        self.assertEqual(run["policy_gate"]["blocked"], 0)
        self.assertEqual(run["policy_check"]["violations"], 1)
        self.assertEqual(run["policy_check"]["violation_ids"][0], {"id": STRAY_ID, "reason": f"date 2023-03 ≥ cutoff {CUTOFF}"})
        self.assertEqual(run["structure"]["references_bib_total"], 5)
        self.assertTrue(run["policy_comparable"])          # 정책 자체는 맞았다 — 위반 수로 걸러야 한다
        self.assertIn(f"| <{CUTOFF} (위반 1) |", collect_run.table())

    def test_dry_run_only_prechecks_policy(self):
        with mock.patch.object(collect_run, "parse_dotenv", return_value={"SURVEYX_DATA_SOURCE": "kisti"}), \
                mock.patch.object(run_kisti.subprocess, "run", side_effect=self.pipeline) as sp:
            self.assertIsNone(run_kisti.run_topic(TITLE, dry_run=True))
            sp.assert_not_called()
        self.assertEqual(self.pipeline.calls, [])

    def test_needs_review_policy_row_blocks_before_spending(self):
        self.policy_path.write_text(json.dumps({**EXAMPLE_POLICY_ROW, "status": "needs_review"}) + "\n", encoding="utf-8")
        with mock.patch.object(collect_run, "parse_dotenv", return_value={"SURVEYX_DATA_SOURCE": "kisti"}), \
                mock.patch.object(run_kisti, "credits_snapshot") as cs, \
                mock.patch.object(run_kisti.subprocess, "run", side_effect=self.pipeline) as sp:
            with self.assertRaises(SystemExit):
                run_kisti.run_topic(TITLE)
            sp.assert_not_called()
            cs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
