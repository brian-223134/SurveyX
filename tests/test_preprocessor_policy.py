"""preprocessor 의 topic 정책 훅(2026-09-14 규약) — fetcher provenance 기록과 허용 집합 게이트.

실행:  /data2/chanjoong/miniforge3/envs/surveyx/bin/python -m unittest tests.test_preprocessor_policy -v
(src.modules.preprocessor.preprocessor 임포트가 무거워 수십 초 걸릴 수 있다)

- _save_fetcher_provenance: fetcher.provenance(dict) 를 outputs/<task_id>/metrics/fetcher_provenance.json 으로; 없으면 아무것도 안 씀
- _apply_policy_gate: fetcher.is_allowed 가 False 인 `_id` 를 제거하고 policy_gate 를 provenance 파일에 덧붙임;
  is_allowed 가 없는 fetcher(원본 DataFetcher·common_corpus)는 무변경
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.modules.preprocessor import preprocessor as pp  # noqa: E402


class _PolicyFetcher:
    def __init__(self, allowed):
        self._allowed = set(allowed)
        self.provenance = {"data_source": "kisti", "view": "kisti-2608",
                           "retrieval_policy": {"topic_id": "t", "retrieval_cutoff_at": "2022-11-03",
                                                "allowed": 3, "total": 5, "allowed_sha256": "x"}}

    def is_allowed(self, pid):
        return pid in self._allowed


class _PlainFetcher:          # 원본 DataFetcher 처럼 provenance·is_allowed 가 없다
    pass


class PreprocessorPolicyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        p = mock.patch.object(pp, "OUTPUT_DIR", self.tmp)
        p.start()
        self.addCleanup(p.stop)
        self.task = "2026-09-16-0000_test"
        self.prov = self.tmp / self.task / "metrics" / "fetcher_provenance.json"

    def test_provenance_written_then_gate_appends(self):
        f = _PolicyFetcher(allowed={"a", "b"})
        pp._save_fetcher_provenance(f, self.task)
        prov = json.loads(self.prov.read_text(encoding="utf-8"))
        self.assertEqual(prov["retrieval_policy"]["retrieval_cutoff_at"], "2022-11-03")
        self.assertNotIn("policy_gate", prov)
        papers = [{"_id": "a"}, {"_id": "zzz"}, {"_id": "b"}, {"_id": "10.1145/3793659"}]
        kept = pp._apply_policy_gate(f, papers, self.task)
        self.assertEqual([p["_id"] for p in kept], ["a", "b"])
        gate = json.loads(self.prov.read_text(encoding="utf-8"))["policy_gate"]
        self.assertEqual((gate["checked"], gate["blocked"]), (4, 2))
        self.assertEqual(gate["blocked_ids"], ["zzz", "10.1145/3793659"])

    def test_all_allowed_blocks_nothing(self):
        f = _PolicyFetcher(allowed={"a", "b"})
        pp._save_fetcher_provenance(f, self.task)
        papers = [{"_id": "a"}, {"_id": "b"}]
        self.assertEqual(pp._apply_policy_gate(f, papers, self.task), papers)
        self.assertEqual(json.loads(self.prov.read_text(encoding="utf-8"))["policy_gate"]["blocked"], 0)

    def test_plain_fetcher_is_untouched(self):
        f = _PlainFetcher()
        pp._save_fetcher_provenance(f, self.task)
        self.assertFalse(self.prov.exists())
        papers = [{"_id": "anything"}]
        self.assertIs(pp._apply_policy_gate(f, papers, self.task), papers)


if __name__ == "__main__":
    unittest.main()
