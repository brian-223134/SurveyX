"""scripts/collect_run.py 단위 테스트 — 합성 task 디렉터리와 합성 kisti_data 루트로 run.json 을 만든다.

실행:  /data2/chanjoong/miniforge3/envs/surveyx/bin/python -m unittest discover -s tests -v

검증 항목 (docs/kisti-run.md §5)
- 구조: survey.tex 의 섹션·소절·단어·\\cite, references.bib 의 항목·id 유형(eprint / doi / url)
- 매칭 키: arXiv → 10.48550/arxiv.<base id>(버전 제거), DOI → 소문자
- recall/precision: 분모는 gap_to_80_refs.jsonl 의 tier == in_view
- 누수: 제외 키가 refs·원문에 있으면 clean=False, GT 제목이 bib title 에 있으면 검출
- 요청 기록: status 별 수, 429, 템플릿 매칭(실제 프롬프트 파일 기준), draft/소절
- env 스냅샷이 없으면 모델·프로파일은 null (현재 .env 로 대체하지 않음)
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
for p in (REPO_ROOT, REPO_ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import collect_run  # noqa: E402

TITLE = "Visual Adversarial Attacks and Defenses in the Physical World"
GT_TITLE = TITLE + ": A Survey"
SLUG, DOMAIN = "physical-adversarial-attacks", "security"
TWIN = "2211.01671"

SURVEY_TEX = r"""
\documentclass{article}
\begin{document}
\section{Introduction}
Adversarial patches fool detectors \cite{k1, k2} in the physical world.
\subsection{Scope}
We survey printable attacks \cite{k2}.
\section{Attacks}
\subsection{Patch attacks}
Many methods exist \cite{k3}. Unknown key \cite{k9}.
\bibliography{references}
\end{document}
"""

REFERENCES_BIB = """@article{k1,
  title={Adversarial Patch},
  year={2017},
  eprint={1712.09665v2},
  archivePrefix={arXiv},
  url={http://arxiv.org/abs/1712.09665v2}
}
@article{k2,
  title={Physical Adversarial Attack on a Detector},
  year={2023},
  journal={ACM Computing Surveys},
  doi={10.1145/3589334.3645719},
  url={https://doi.org/10.1145/3589334.3645719}
}
@article{k3,
  title={Robust Physical-World Attacks},
  year={2018},
  url={http://arxiv.org/abs/1707.08945}
}
@article{k4,
  title={No Identifier Here At All For This Entry},
  year={2020},
  journal={Somewhere}
}
"""


def record_prefix(template_rel: str) -> str:
    """ChatAgent.update_record 가 남기는 request 필드와 같은 방식 (request[:200] 에서 개행 제거)."""
    text = (collect_run.PROMPT_ROOT / template_rel).read_text(encoding="utf-8")
    return text[:collect_run.RECORD_SHOW_LENGTH].replace("\n", "")


def stats_line(status: int, code: int, template_rel: str | None, resp: str = "resp") -> str:
    req = record_prefix(template_rel) if template_rel else "something else entirely that matches no template"
    return f"{status}||{code}||{req}||{resp}"


class CollectRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.outputs = self.tmp / "outputs"
        self.kisti = self.tmp / "kisti_data"
        self.task_id = "2026-09-08-0528_Visua"
        self._make_kisti_root()
        self._make_task_dir()
        patches = [
            mock.patch.object(collect_run, "OUTPUTS", self.outputs),
            mock.patch.object(collect_run, "KISTI_ROOT", self.kisti),
            mock.patch.object(collect_run, "ADAPTER_DIR", self.tmp / "no-adapter"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    # ---- fixtures
    def _make_kisti_root(self):
        (self.kisti / "data" / "views" / "kisti-2512").mkdir(parents=True)
        (self.kisti / "data" / "topics.kisti.jsonl").write_text(json.dumps({
            "title": TITLE, "n_gt_refs": 165, "gt_doi": "10.1145/3793659", "domain": DOMAIN, "slug": SLUG,
        }) + "\n", encoding="utf-8")
        view = self.kisti / "data" / "views" / "kisti-2512"
        (view / "exclude_keys.txt").write_text(
            f"10.1145/3793659\tgt:{DOMAIN}/{SLUG}\n10.48550/arxiv.{TWIN}\ttwin:{TWIN}\n", encoding="utf-8")
        (view / "view_manifest.json").write_text('{"view_name": "kisti-2512"}', encoding="utf-8")
        cand = self.kisti / "candidates"
        (cand / DOMAIN / SLUG).mkdir(parents=True)
        (cand / DOMAIN / SLUG / "refs.json").write_text(json.dumps({
            "candidate": {"gt": {"title": GT_TITLE, "doi": "10.1145/3793659"}}}), encoding="utf-8")
        rows = [
            {"slug": SLUG, "tier": "in_view", "kisti_doi": "10.48550/arxiv.1712.09665"},   # k1 적중
            {"slug": SLUG, "tier": "in_view", "kisti_doi": "10.1145/3589334.3645719"},     # k2 적중
            {"slug": SLUG, "tier": "in_view", "kisti_doi": "10.1000/not-cited"},           # 미적중
            {"slug": SLUG, "tier": "t1_arxiv", "kisti_doi": "10.48550/arxiv.1707.08945"},  # 분모 밖 (k3)
            {"slug": "other-slug", "tier": "in_view", "kisti_doi": "10.1000/other"},
        ]
        (cand / "gap_to_80_refs.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    def _make_task_dir(self, env_snapshot: bool = True):
        d = self.outputs / self.task_id
        (d / "metrics").mkdir(parents=True)
        (d / "latex").mkdir()
        (d / "tmp_config.json").write_text(json.dumps({
            "title": TITLE, "key_words": "a, b, c", "topic": "…", "task_id": self.task_id}), encoding="utf-8")
        (d / "latex" / "survey.tex").write_text(SURVEY_TEX, encoding="utf-8")
        (d / "latex" / "references.bib").write_text(REFERENCES_BIB, encoding="utf-8")
        (d / "metrics" / "token_monitor.json").write_text(json.dumps({
            "generate content": {"meta-llama/llama-3.3-70b-instruct": {
                "input_tokens": 1000, "output_tokens": 200, "total_cost": 0.5}},
            "post refine": {"meta-llama/llama-3.3-70b-instruct": {
                "input_tokens": 100, "output_tokens": 20, "total_cost": 0.25}},
        }), encoding="utf-8")
        (d / "metrics" / "time_monitor.json").write_text(json.dumps({
            "retrieve paper": {"start": "2026-09-08 05:28:20", "end": "2026-09-08 05:30:20", "duration": 120.0},
            "post refine": {"start": "2026-09-08 06:00:00", "end": "2026-09-08 06:28:20", "duration": 1700.0},
            "compile latex": {"start": "2026-09-09 00:00:00", "end": "2026-09-09 00:00:07", "duration": 7.0},
        }), encoding="utf-8")
        draft = "content_generator/fulfill_content.md"
        lines = [
            stats_line(1, 200, draft), stats_line(1, 200, draft), stats_line(2, 200, draft),   # draft 3회(1 폐기)
            stats_line(1, 200, "outline_generator/write_primary_outline.md"),
            stats_line(0, 429, draft),                                                        # 429 (재시도됨)
            stats_line(3, 200, "section_rewriter/compress_sections.md"),                     # 잘림 채택
            stats_line(1, 200, None),                                                         # other
        ]
        (d / "metrics" / "request_stats.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        if env_snapshot:
            (d / "metrics" / "env.snapshot.json").write_text(json.dumps({
                "SURVEYX_DEFAULT_MODEL": "meta-llama/llama-3.3-70b-instruct",
                "OPENROUTER_PROVIDER_ONLY": "akashml/fp8", "SURVEYX_TEMPERATURE": "0.6",
                "SURVEYX_MAX_TOKENS": "8192", "SURVEYX_DATA_SOURCE": "kisti", "KISTI_VIEW": "kisti-2512",
                "OPENROUTER_API_KEY": "sk-or-…",
            }), encoding="utf-8")
        (d / "metrics" / "credits.json").write_text(json.dumps({"measured_usd": 0.81}), encoding="utf-8")
        (d / "metrics" / "run_args.json").write_text(json.dumps({
            "args": f'--title "{TITLE}" --key_words "{TITLE}"', "status": "ok", "returncode": 0}), encoding="utf-8")

    # ---- tests
    def test_structure_and_refs(self):
        r = collect_run.build(self.task_id)
        s = r["structure"]
        self.assertEqual((s["sections"], s["subsections"]), (2, 2))
        self.assertTrue(s["from_tex"])
        self.assertGreater(s["words"], 10)
        self.assertEqual(s["citation_runs"], 4)
        self.assertEqual(s["references"], 3)                 # 인용된 k1 k2 k3 (k9 는 bib 에 없음)
        self.assertEqual(s["references_bib_total"], 4)      # bib 전편 (k4 는 미인용)
        self.assertIsNone(s["pdf_pages"])                    # survey.pdf 없음
        self.assertEqual(r["refs"]["arxiv"], 2)
        self.assertEqual(r["refs"]["doi"], 1)
        self.assertEqual(r["refs"]["other"], 0)              # 미인용 k4 는 세지 않는다
        self.assertEqual(r["refs"]["match_keys"], sorted([
            "10.48550/arxiv.1712.09665", "10.1145/3589334.3645719", "10.48550/arxiv.1707.08945"]))

    def test_score_against_in_view_denominator(self):
        r = collect_run.build(self.task_id)
        self.assertEqual(r["gt"]["slug"], SLUG)
        self.assertEqual(r["gt"]["n_gt_refs_in_view"], 3)
        self.assertEqual(r["gt"]["gt_title"], GT_TITLE)
        sc = r["score"]
        self.assertEqual(sc["hits"], 2)
        self.assertEqual(sc["refs_identifiable"], 3)
        self.assertAlmostEqual(sc["recall"], 2 / 3, places=4)
        self.assertAlmostEqual(sc["precision"], 2 / 3, places=4)

    def test_requests_and_draft_ratio(self):
        r = collect_run.build(self.task_id)
        q = r["requests"]
        self.assertEqual(q["records"], 7)
        self.assertEqual(q["ok"], 4)
        self.assertEqual(q["http_errors"], {"429": 1})
        self.assertEqual(q["truncated_discarded"], 1)
        self.assertEqual(q["truncated_accepted"], 1)
        self.assertEqual(q["draft_calls"], 3)                # 429 건은 제외, 폐기 건은 포함
        self.assertEqual(r["draft_calls_per_subsection"], 1.5)
        self.assertEqual(r["requests_by_template"]["other"], 1)
        self.assertEqual(r["truncation_retries"], 1)
        self.assertEqual(r["truncated_calls"], 1)

    def test_env_snapshot_and_costs(self):
        r = collect_run.build(self.task_id)
        self.assertEqual(r["model"], "meta-llama/llama-3.3-70b-instruct")
        self.assertEqual(r["provider_pin"], "akashml/fp8")
        self.assertEqual(r["temperature"], "0.6")
        self.assertEqual(r["max_tokens"], "8192")
        self.assertEqual(r["data_source"], "kisti")
        self.assertEqual(r["cost_total_usd"], 0.75)
        self.assertEqual(r["cost_measured_usd"], 0.81)
        self.assertEqual(r["duration_sec"], 3600)            # 05:28:20 → 06:28:20, compile 제외
        self.assertEqual(r["stage_durations_sec"]["compile latex"], 7.0)
        self.assertEqual(r["status"], "ok")
        self.assertIsNotNone(r["view_manifest_sha256"])

    def test_missing_env_snapshot_leaves_profile_null(self):
        (self.outputs / self.task_id / "metrics" / "env.snapshot.json").unlink()
        r = collect_run.build(self.task_id)
        self.assertIsNone(r["model"])
        self.assertIsNone(r["max_tokens"])
        self.assertTrue(r["env_source"].startswith("none"))
        self.assertEqual(r["view"], "kisti-2512")            # 누수 검사 기본 view

    def test_leak_clean(self):
        r = collect_run.build(self.task_id)
        self.assertTrue(r["leak"]["clean"])
        self.assertEqual(r["leak"]["exclude_keys"], 2)

    def test_cites_inside_input_files_count(self):
        d = self.outputs / self.task_id / "latex"
        (d / "figs").mkdir()
        (d / "figs" / "table_1.tex").write_text("\\begin{table}Row \\cite{k4}\\end{table}\n", encoding="utf-8")
        tex = d / "survey.tex"
        tex.write_text(tex.read_text(encoding="utf-8").replace("\\bibliography{references}",
                                                                "\\input{figs/table_1}\n\\bibliography{references}"),
                       encoding="utf-8")
        r = collect_run.build(self.task_id)
        self.assertEqual(r["structure"]["references"], 4)   # k4 가 표 안에서 인용됨
        self.assertEqual(r["structure"]["citation_runs"], 5)
        self.assertEqual(r["refs"]["other"], 1)

    def test_leak_detects_twin_and_gt_title(self):
        # 미인용이라도 bib(=검색 풀)에 들어오면 누수다
        bib = self.outputs / self.task_id / "latex" / "references.bib"
        bib.write_text(REFERENCES_BIB + f"""@article{{k5,
  title={{{GT_TITLE}}},
  year={{2022}},
  eprint={{{TWIN}}},
  archivePrefix={{arXiv}},
  url={{http://arxiv.org/abs/{TWIN}}}
}}
""", encoding="utf-8")
        r = collect_run.build(self.task_id)
        lk = r["leak"]
        self.assertFalse(lk["clean"])
        self.assertEqual([h["reason"] for h in lk["ids_in_refs"]], [f"twin:{TWIN}"])
        self.assertEqual([h["reason"] for h in lk["ids_in_text"]], [f"twin:{TWIN}"])
        self.assertEqual([h["key"] for h in lk["gt_title_in_bib"]], ["k5"])

    def test_unknown_topic_has_no_gt(self):
        cfg = self.outputs / self.task_id / "tmp_config.json"
        cfg.write_text(json.dumps({"title": "A Survey on Edge Computing", "key_words": "", "task_id": self.task_id}),
                       encoding="utf-8")
        r = collect_run.build(self.task_id)
        self.assertIsNone(r["gt"])
        self.assertIsNone(r["score"])
        self.assertTrue(r["leak"]["clean"])

    def test_write_run_and_table(self):
        out = collect_run.write_run(self.task_id)
        self.assertTrue(out.exists())
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["task_id"], self.task_id)
        table = collect_run.table()
        self.assertIn(self.task_id, table)
        self.assertIn("66.7%/66.7% (n=3)", table)
        self.assertIn("| clean |", table)

    def test_view_snapshot_resolves_preserved_view_dir(self):
        """같은 경로에서 view 가 교체된 뒤에도, 실행 시작 시점 스냅샷의 manifest sha 로 보존본(-v1)을 찾아
        그 exclude_keys 로 누수를 검사하고 version 은 스냅샷 값을 쓴다."""
        views = self.kisti / "data" / "views"
        v1 = views / "kisti-2512-v1"
        v1.mkdir()
        (v1 / "view_manifest.json").write_text(json.dumps({
            "view_name": "kisti-2512", "created_at": "2026-09-07T05:10:55+00:00",
            "counts": {"view_papers": 1651701}, "files_sha256": {"papers.parquet": "c7b8d4e7" + "0" * 56}}),
            encoding="utf-8")
        (v1 / "exclude_keys.txt").write_text("10.48550/arxiv.1712.09665\ttwin:1712.09665\n", encoding="utf-8")  # k1 = 누수
        snap = collect_run.view_snapshot("kisti-2512-v1")
        snap["view"] = "kisti-2512"
        (self.outputs / self.task_id / "metrics" / "view.snapshot.json").write_text(json.dumps(snap), encoding="utf-8")
        r = collect_run.build(self.task_id)
        self.assertEqual(r["view"], "kisti-2512")
        self.assertEqual(r["view_version"], "c7b8d4e7")
        self.assertEqual(r["view_papers"], 1651701)
        self.assertTrue(r["view_source"].startswith("metrics/view.snapshot.json"))
        self.assertTrue(r["leak"]["keys_from"].endswith("kisti-2512-v1"))
        self.assertFalse(r["leak"]["clean"])
        self.assertEqual(r["leak"]["exclude_keys"], 1)

    def test_view_without_snapshot_uses_current_dir_and_flags_it(self):
        r = collect_run.build(self.task_id)
        self.assertTrue(r["view_source"].startswith("current view dir"))
        self.assertIsNone(r["view_version"])                 # fixture manifest 에 files_sha256 없음
        self.assertTrue(r["leak"]["keys_from"].endswith("kisti-2512"))
        self.assertEqual(r["leak"]["exclude_keys"], 2)

    def test_attri_summary_from_log(self):
        log = self.tmp / "run.log"
        log.write_text("x\n... - attribute tree: 150/196 papers have attri (repaired 118, unresolved 46 after 3 passes)\n",
                       encoding="utf-8")
        (self.outputs / self.task_id / "metrics" / "run_args.json").write_text(
            json.dumps({"args": "a", "status": "ok", "log_path": str(log)}), encoding="utf-8")
        r = collect_run.build(self.task_id)
        self.assertEqual(r["attri"], {"with_attri": 150, "papers": 196, "repaired": 118, "unresolved": 46, "passes": 3})
        self.assertIsNone(collect_run.parse_attri_summary(self.tmp / "missing.log"))

    def test_parse_dotenv_masks_secrets(self):
        env_file = self.tmp / ".env"
        env_file.write_text("OPENROUTER_API_KEY=sk-or-v1-abcdef123456\nSURVEYX_TEMPERATURE=0.6\n# c\nexport X='y'\n",
                            encoding="utf-8")
        env = collect_run.parse_dotenv(env_file)
        self.assertEqual(env["OPENROUTER_API_KEY"], "sk-or-…")
        self.assertEqual(env["SURVEYX_TEMPERATURE"], "0.6")
        self.assertEqual(env["X"], "y")


if __name__ == "__main__":
    unittest.main()
