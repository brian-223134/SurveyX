"""scripts/run_kisti.py 단위 테스트 — full_run.py 와 check_credits.py 를 mock 해 실행 없이 기록 절차를 검증한다.

실행:  /data2/chanjoong/miniforge3/envs/surveyx/bin/python -m unittest discover -s tests -v

검증 항목 (docs/kisti-run.md §4)
- 요청 기록 회전, task 디렉터리 탐색(title·시각), --skip-done 판정, 크레딧 파싱
- run_topic: metrics/ 에 env.snapshot.json · credits.json(전후 차분) · run_args.json · request_stats.txt 가 남고
  run.json 이 만들어진다; 실패(returncode≠0)도 status=failed 로 기록된다
- topic 정책(2026-09-14 규약): topic → slug 를 찾아 자식 프로세스 환경변수 KISTI_TOPIC_ID 로 넣고 KISTI_VIEW 를 함께
  넘긴다; topics.kisti.jsonl 밖의 title 은 --no-policy 없이는 거부; 정책 사전 점검(check_policy)은 행 없음·
  status≠ok·sidecar 없음에서 멈춘다
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
for p in (REPO_ROOT, REPO_ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import collect_run  # noqa: E402
import run_kisti  # noqa: E402

TITLE = "Visual Adversarial Attacks and Defenses in the Physical World"
SLUG = "physical-adversarial-attacks"
CUTOFF = "2022-11-03"
FAKE_POLICY = {"topic_id": SLUG, "retrieval_cutoff_at": CUTOFF, "exclude_ids": ["10.1145/3793659", "2211.01671"],
               "policy_file": "/fake/topic_policy.kisti-2608.jsonl", "corpus_snapshot_id": "fake", "sidecar": "/fake/paper_dates.json"}
CREDITS_OUT = (
    "2026-09-08 05:27:33 [x]  account: purchased=$4100.5500  used=$3406.8349  remaining=$693.7151\n"
    "2026-09-08 05:27:33 [x]  key(sk-or-v1-f7a...e3f): limit=$30.00  used=$24.6602  today=$0.0331  remaining=$5.3398\n"
)


class RunKistiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.outputs = self.tmp / "outputs"
        (self.outputs / "tmp").mkdir(parents=True)
        self.stats = self.outputs / "tmp" / "request_stats.txt"
        patches = [
            mock.patch.object(run_kisti, "OUTPUTS", self.outputs),
            mock.patch.object(run_kisti, "LOG_DIR", self.outputs / "logs"),
            mock.patch.object(run_kisti, "REQUEST_STATS", self.stats),
            mock.patch.object(run_kisti, "CREDITS_LOG", self.outputs / "credits.log"),
            mock.patch.object(run_kisti, "KISTI_ROOT", self.tmp / "kisti_data"),
            mock.patch.object(run_kisti, "TOPICS", self.tmp / "kisti_data" / "data" / "topics.kisti.jsonl"),
            mock.patch.object(collect_run, "OUTPUTS", self.outputs),
            mock.patch.object(collect_run, "KISTI_ROOT", self.tmp / "kisti_data"),
            mock.patch.object(collect_run, "ADAPTER_DIR", self.tmp / "no-adapter"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        # 실행 환경변수 KISTI_* 가 테스트 결과를 흔들지 않도록 비운다
        for k in run_kisti.KISTI_ENV_KEYS:
            self.addCleanup(lambda k=k, v=os.environ.get(k): os.environ.update({k: v}) if v else os.environ.pop(k, None))
            os.environ.pop(k, None)
        (self.tmp / "kisti_data" / "data").mkdir(parents=True)
        run_kisti.TOPICS.write_text(json.dumps({
            "title": TITLE, "slug": SLUG, "domain": "security", "gt_doi": "10.1145/3793659",
            "retrieval_cutoff_at": CUTOFF, "n_gt_refs_cutoff": 128}) + "\n", encoding="utf-8")

    # ---- helpers
    def _fake_task(self, task_id: str, title: str = TITLE, age_sec: float = 0.0) -> Path:
        d = self.outputs / task_id
        (d / "metrics").mkdir(parents=True)
        (d / "latex").mkdir()
        cfg = d / "tmp_config.json"
        cfg.write_text(json.dumps({"title": title, "key_words": "k", "task_id": task_id}), encoding="utf-8")
        (d / "metrics" / "token_monitor.json").write_text("{}", encoding="utf-8")
        (d / "metrics" / "time_monitor.json").write_text("{}", encoding="utf-8")
        (d / "latex" / "survey.tex").write_text("\\begin{document}\\section{A}\ntext\n", encoding="utf-8")
        (d / "latex" / "references.bib").write_text("", encoding="utf-8")
        if age_sec:
            import os
            os.utime(cfg, (time.time() - age_sec, time.time() - age_sec))
        return d

    # ---- small pieces
    def test_slugify(self):
        self.assertEqual(run_kisti.slugify("Visual Adversarial Attacks: In the Physical World!"),
                         "visual-adversarial-attacks-in-the-physical-world")

    def test_rotate_request_stats(self):
        self.assertIsNone(run_kisti.rotate_request_stats())          # 파일 없음
        self.stats.write_text("1||200||a||b\n", encoding="utf-8")
        bak = run_kisti.rotate_request_stats()
        self.assertFalse(self.stats.exists())
        self.assertTrue(bak.exists() and bak.name.startswith("request_stats.") and bak.suffix == ".bak")

    def test_find_task_dir_picks_matching_recent(self):
        self._fake_task("old_run", age_sec=3600)                        # 실행 이전 것
        self._fake_task("other_title", title="Something Else")
        want = self._fake_task("new_run")
        self.assertEqual(run_kisti.find_task_dir(TITLE, since=time.time() - 60), want)
        self.assertIsNone(run_kisti.find_task_dir("Missing Title", since=time.time() - 60))

    def test_done_titles_requires_ok_and_pdf(self):
        d = self._fake_task("done_run")
        (d / "run.json").write_text(json.dumps({"topic": TITLE, "status": "ok", "structure": {"pdf_pages": 20}}),
                                    encoding="utf-8")
        f = self._fake_task("failed_run", title="Failed Topic")
        (f / "run.json").write_text(json.dumps({"topic": "Failed Topic", "status": "failed",
                                                "structure": {"pdf_pages": None}}), encoding="utf-8")
        self.assertEqual(run_kisti.done_titles(), {TITLE})

    def test_credits_snapshot_parses_key_and_account(self):
        with mock.patch.object(run_kisti.subprocess, "check_output", return_value=CREDITS_OUT):
            snap = run_kisti.credits_snapshot("before:x")
        self.assertEqual(snap["key_used_usd"], 24.6602)
        self.assertEqual(snap["account_used_usd"], 3406.8349)

    def test_credits_snapshot_failure_is_none(self):
        with mock.patch.object(run_kisti.subprocess, "check_output", side_effect=OSError("no network")):
            self.assertIsNone(run_kisti.credits_snapshot("before:x"))

    def test_check_env_rejects_non_kisti_source(self):
        with self.assertRaises(SystemExit):
            run_kisti.check_env({"SURVEYX_DATA_SOURCE": "common_corpus"}, allow_source=False)

    # ---- topic 정책 (2026-09-14 규약)
    def test_resolve_slug_by_normalized_title(self):
        self.assertEqual(run_kisti.resolve_slug(TITLE), SLUG)
        self.assertEqual(run_kisti.resolve_slug(TITLE.lower() + "  "), SLUG)      # 공백·대소문자 무시
        self.assertIsNone(run_kisti.resolve_slug("Some Other Topic"))

    def test_effective_env_prefers_process_env(self):
        os.environ["KISTI_VIEW"] = "kisti-2608"
        eff = run_kisti.effective_env({"KISTI_VIEW": "kisti-2512", "SURVEYX_DATA_SOURCE": "kisti"})
        self.assertEqual(eff["KISTI_VIEW"], "kisti-2608")
        self.assertEqual(eff["SURVEYX_DATA_SOURCE"], "kisti")
        self.assertNotIn("KISTI_TOPIC_ID", eff)                               # topic 별 값은 .env 에 없다

    def _policy_fixture(self, status="ok", sidecar=True):
        pol = self.tmp / "topic_policy.kisti-2608.jsonl"
        pol.write_text("# comment\n" + json.dumps({"topic_id": SLUG, "retrieval_cutoff_at": CUTOFF, "status": status,
                                                    "exclude_ids": ["10.1145/3793659"]}) + "\n", encoding="utf-8")
        vdir = self.tmp / "kisti_data" / "data" / "views" / "kisti-2608"
        vdir.mkdir(parents=True, exist_ok=True)
        if sidecar:
            (vdir / "paper_dates.json").write_text('{"meta": {}, "dates": {}}', encoding="utf-8")
        return {"KISTI_TOPIC_POLICY": str(pol)}

    @unittest.skipUnless((run_kisti.ADAPTER_DIR / "common" / "retrieval_policy.py").exists(), "kisti_data adapter 없음")
    def test_check_policy_reads_row_and_sidecar(self):
        env = self._policy_fixture()
        pol = run_kisti.check_policy("kisti-2608", SLUG, env)
        self.assertEqual((pol["topic_id"], pol["retrieval_cutoff_at"], pol["exclude_ids"]), (SLUG, CUTOFF, ["10.1145/3793659"]))
        self.assertTrue(pol["policy_file"].endswith("topic_policy.kisti-2608.jsonl"))
        with self.assertRaises(SystemExit):                                    # 행 없음
            run_kisti.check_policy("kisti-2608", "unknown-slug", env)
        with self.assertRaises(SystemExit):                                    # cutoff 미확정
            run_kisti.check_policy("kisti-2608", SLUG, self._policy_fixture(status="needs_review"))
        with self.assertRaises(SystemExit):                                    # sidecar 없음
            shutil.rmtree(self.tmp / "kisti_data" / "data" / "views")
            run_kisti.check_policy("kisti-2608", SLUG, self._policy_fixture(sidecar=False))
        with self.assertRaises(SystemExit):                                    # 정책 파일 없음
            run_kisti.check_policy("kisti-2608", SLUG, {"KISTI_TOPIC_POLICY": str(self.tmp / "missing.jsonl")})

    def test_run_topic_injects_topic_id_and_view(self):
        os.environ["KISTI_VIEW"] = "kisti-2608"
        seen = {}

        def fake_full_run(cmd, **kw):
            seen.update(kw["env"])
            self._fake_task("2026-09-16-0300_Visua")
            return mock.Mock(returncode=0)

        with mock.patch.object(collect_run, "parse_dotenv", return_value={"SURVEYX_DATA_SOURCE": "kisti"}), \
                mock.patch.object(run_kisti, "check_env", side_effect=lambda env, allow: env["KISTI_VIEW"]), \
                mock.patch.object(run_kisti, "check_policy", return_value=FAKE_POLICY) as cp, \
                mock.patch.object(run_kisti, "credits_snapshot", return_value=None), \
                mock.patch.object(run_kisti.subprocess, "run", side_effect=fake_full_run):
            out = run_kisti.run_topic(TITLE)
        cp.assert_called_once()
        self.assertEqual(cp.call_args.args[:2], ("kisti-2608", SLUG))
        self.assertEqual(seen["KISTI_TOPIC_ID"], SLUG)                         # 자식 프로세스가 보는 정책 topic
        self.assertEqual(seen["KISTI_VIEW"], "kisti-2608")
        m = self.outputs / "2026-09-16-0300_Visua" / "metrics"
        args = json.loads((m / "run_args.json").read_text(encoding="utf-8"))
        self.assertEqual((args["topic_id"], args["view"], args["policy"]["retrieval_cutoff_at"]), (SLUG, "kisti-2608", CUTOFF))
        self.assertEqual(args["env_overrides"], {"KISTI_VIEW": "kisti-2608", "KISTI_TOPIC_ID": SLUG})
        snap = json.loads((m / "env.snapshot.json").read_text(encoding="utf-8"))
        self.assertEqual((snap["KISTI_VIEW"], snap["KISTI_TOPIC_ID"]), ("kisti-2608", SLUG))
        run = json.loads(out.read_text(encoding="utf-8"))
        self.assertIsNone(run["retrieval_policy"])                             # 파이프라인(mock)이 provenance 를 안 남겼다
        self.assertFalse(run["policy_comparable"])

    def test_run_topic_unknown_title_requires_no_policy(self):
        with mock.patch.object(collect_run, "parse_dotenv", return_value={"SURVEYX_DATA_SOURCE": "kisti"}), \
                mock.patch.object(run_kisti, "check_env", return_value="kisti-2608"), \
                mock.patch.object(run_kisti, "check_policy") as cp, \
                mock.patch.object(run_kisti.subprocess, "run") as sp:
            with self.assertRaises(SystemExit):
                run_kisti.run_topic("Some Other Topic")
            sp.assert_not_called()
            cp.assert_not_called()

    def test_run_topic_no_policy_strips_topic_id(self):
        os.environ["KISTI_TOPIC_ID"] = "stale-from-shell"
        seen = {}

        def fake_full_run(cmd, **kw):
            seen.update(kw["env"])
            return mock.Mock(returncode=1)

        with mock.patch.object(collect_run, "parse_dotenv", return_value={"SURVEYX_DATA_SOURCE": "kisti"}), \
                mock.patch.object(run_kisti, "check_env", return_value="kisti-2512"), \
                mock.patch.object(run_kisti, "check_policy") as cp, \
                mock.patch.object(run_kisti, "credits_snapshot", return_value=None), \
                mock.patch.object(run_kisti.subprocess, "run", side_effect=fake_full_run):
            run_kisti.run_topic("Some Other Topic", no_policy=True)
        cp.assert_not_called()
        self.assertNotIn("KISTI_TOPIC_ID", seen)
        self.assertEqual(seen["KISTI_VIEW"], "kisti-2512")

    # ---- run_topic end-to-end (subprocess mocked)
    def _run(self, returncode: int):
        env = {"SURVEYX_DATA_SOURCE": "kisti", "SURVEYX_TEMPERATURE": "0.6", "SURVEYX_MAX_TOKENS": "8192",
               "OPENROUTER_PROVIDER_ONLY": "akashml/fp8", "OPENROUTER_API_KEY": "sk-or-…"}

        def fake_full_run(cmd, **kw):
            self.assertIn("--key_words", cmd)
            self.assertEqual(cmd[cmd.index("--title") + 1], cmd[cmd.index("--key_words") + 1])
            self._fake_task("2026-09-08-0528_Visua")
            self.stats.write_text("1||200||req||resp\n0||429||req||err\n", encoding="utf-8")
            return mock.Mock(returncode=returncode)

        credits = iter([{"key_used_usd": 24.0}, {"key_used_usd": 26.5}])
        with mock.patch.object(collect_run, "parse_dotenv", return_value=env), \
                mock.patch.object(run_kisti, "check_env", return_value="kisti-2512"), \
                mock.patch.object(run_kisti, "check_policy", return_value=FAKE_POLICY), \
                mock.patch.object(run_kisti, "credits_snapshot", side_effect=lambda label: next(credits)), \
                mock.patch.object(run_kisti.subprocess, "run", side_effect=fake_full_run):
            return run_kisti.run_topic(TITLE)

    def test_run_topic_records_everything(self):
        out = self._run(returncode=0)
        self.assertIsNotNone(out)
        task = self.outputs / "2026-09-08-0528_Visua"
        m = task / "metrics"
        self.assertTrue((m / "request_stats.txt").exists())
        self.assertFalse(self.stats.exists())                        # 전역 파일은 옮겨졌다
        snap = json.loads((m / "env.snapshot.json").read_text(encoding="utf-8"))
        self.assertEqual(snap["SURVEYX_TEMPERATURE"], "0.6")
        vsnap = json.loads((m / "view.snapshot.json").read_text(encoding="utf-8"))
        self.assertEqual(vsnap["view"], "kisti-2512")          # 시작 시점 view 정체성 (fixture 엔 manifest 없음 → sha None)
        self.assertIn("captured_at", vsnap)
        self.assertEqual(json.loads((m / "credits.json").read_text(encoding="utf-8"))["measured_usd"], 2.5)
        args = json.loads((m / "run_args.json").read_text(encoding="utf-8"))
        self.assertEqual(args["status"], "ok")
        self.assertIn('--key_words "', args["args"])
        run = json.loads((task / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(run["status"], "ok")
        self.assertEqual(run["cost_measured_usd"], 2.5)
        self.assertEqual(run["requests"]["http_errors"], {"429": 1})
        self.assertEqual(run["temperature"], "0.6")
        self.assertEqual(run["provider_pin"], "akashml/fp8")

    def test_run_topic_failure_still_recorded(self):
        self._run(returncode=1)
        task = self.outputs / "2026-09-08-0528_Visua"
        self.assertEqual(json.loads((task / "metrics" / "run_args.json").read_text(encoding="utf-8"))["status"],
                         "failed")
        self.assertEqual(json.loads((task / "run.json").read_text(encoding="utf-8"))["status"], "failed")

    def test_run_topic_without_task_dir_keeps_stats(self):
        env = {"SURVEYX_DATA_SOURCE": "kisti"}

        def fake_full_run(cmd, **kw):
            self.stats.write_text("0||500||req||err\n", encoding="utf-8")
            return mock.Mock(returncode=1)

        with mock.patch.object(collect_run, "parse_dotenv", return_value=env), \
                mock.patch.object(run_kisti, "check_env", return_value="kisti-2512"), \
                mock.patch.object(run_kisti, "check_policy", return_value=FAKE_POLICY), \
                mock.patch.object(run_kisti, "credits_snapshot", return_value=None), \
                mock.patch.object(run_kisti.subprocess, "run", side_effect=fake_full_run):
            self.assertIsNone(run_kisti.run_topic(TITLE))
        kept = list((self.outputs / "tmp").glob("request_stats.failed.*.txt"))
        self.assertEqual(len(kept), 1)
        self.assertFalse(self.stats.exists())


if __name__ == "__main__":
    unittest.main()
