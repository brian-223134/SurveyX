"""repair_json_text 단위 테스트 — AttributeTree 응답의 결정적 형식 오류 복구.

실행:  /data2/chanjoong/miniforge3/envs/surveyx/bin/python -m unittest discover -s tests -v

배경(2026-09-08): attri_tree_for_*.md 의 출력 예시가 `"other info": [ "info1": "", "info2": {...} ]` 로
잘못돼 있고 llama-3.3-70b 가 이를 그대로 따라 표본 12건 중 10건이 같은 자리에서 json.loads 에 실패했다.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.modules.utils import repair_json_text  # noqa: E402
from src.modules.preprocessor.data_cleaner import DataCleaner  # noqa: E402

LLAMA_STYLE = """{
   "background": "Adversarial examples are of interest [1], see \\"quoted\\" text.",
   "problem": {
      "definition": "x",
      "key obstacle": "y"
   },
   "other info": [
      "info1": "Code at http://example.com/a.zip",
      "info2": {
         "info2.1": "Videos [a, b]",
         "info2.2": "PDF"
      }
   ]
}"""


class RepairJsonTextTest(unittest.TestCase):
    def test_valid_json_unchanged(self):
        s = '{"a": [1, 2, {"b": "c"}], "d": "e:f"}'
        self.assertEqual(repair_json_text(s), s)

    def test_kv_array_becomes_object(self):
        out = json.loads(repair_json_text(LLAMA_STYLE))
        self.assertEqual(out["other info"]["info1"], "Code at http://example.com/a.zip")
        self.assertEqual(out["other info"]["info2"]["info2.2"], "PDF")
        self.assertEqual(out["other info"]["info2"]["info2.1"], "Videos [a, b]")   # 문자열 안의 괄호는 무시
        self.assertEqual(out["background"], 'Adversarial examples are of interest [1], see "quoted" text.')

    def test_nested_kv_arrays_and_trailing_commas(self):
        s = '{"x": [ "k1": [ "k2": "v", ], "k3": 1, ], "y": [1, 2,], }'
        out = json.loads(repair_json_text(s))
        self.assertEqual(out, {"x": {"k1": {"k2": "v"}, "k3": 1}, "y": [1, 2]})

    def test_real_array_of_strings_untouched(self):
        s = '{"tags": ["a: b", "c"], "n": []}'
        self.assertEqual(json.loads(repair_json_text(s)), {"tags": ["a: b", "c"], "n": []})

    def test_unbalanced_input_does_not_hang(self):
        s = '{"other info": [ "info1": "unterminated'
        repair_json_text(s)   # 예외·무한루프 없이 반환하면 충분

    def test_real_samples_if_available(self):
        """세션 중 수집한 실제 llama 응답 표본(scratchpad)이 있으면 전부 복구되는지 확인. 없으면 건너뜀."""
        p = Path("/tmp/claude-1024/-data2-chanjoong-survey-agent-SurveyX/58fabb8d-106d-4a34-a153-55652209b149/scratchpad/attri/samples.json")
        if not p.exists():
            self.skipTest("no real samples")
        rows = json.loads(p.read_text(encoding="utf-8"))
        failed = [r for r in rows if r["error"]]
        for r in failed:
            json.loads(repair_json_text(r["cleaned"]))
        self.assertGreater(len(failed), 0)


class DataCleanerAttriRepairTest(unittest.TestCase):
    def _cleaner(self, papers):
        c = DataCleaner(papers=papers)
        return c

    def test_process_attri_uses_repair_and_counts(self):
        c = self._cleaner([{"title": "T", "md_text": "x"}])
        ok = c._DataCleaner__process_attri_response(LLAMA_STYLE, 0)
        self.assertTrue(ok)
        self.assertEqual(c.papers[0]["attri"]["other info"]["info2"]["info2.2"], "PDF")
        self.assertEqual(c.attri_repaired, 1)

    def test_process_attri_valid_json_not_counted_as_repair(self):
        c = self._cleaner([{"title": "T", "md_text": "x"}])
        self.assertTrue(c._DataCleaner__process_attri_response('```json\n{"a": 1}\n```', 0))
        self.assertEqual(c.papers[0]["attri"], {"a": 1})
        self.assertEqual(c.attri_repaired, 0)

    def test_process_attri_unrepairable_returns_false(self):
        c = self._cleaner([{"title": "T", "md_text": "x"}])
        self.assertFalse(c._DataCleaner__process_attri_response("not json at all {", 0))
        self.assertNotIn("attri", c.papers[0])

    def test_get_attri_retries_only_failures_and_logs_summary(self):
        papers = [{"title": "A", "md_text": "a", "paper_type": "method"},
                  {"title": "B", "md_text": "b", "paper_type": "method"}]
        c = self._cleaner(papers)
        chat = mock.Mock()
        # 1패스: A 는 llama 형식(복구됨), B 는 깨짐 → 2패스: B 만 재요청, 정상
        chat.batch_remote_chat.side_effect = [[LLAMA_STYLE, "{broken"], ['{"ok": true}']]
        with mock.patch("src.modules.preprocessor.data_cleaner.load_prompt", side_effect=lambda *a, **k: "p"):
            c.get_attri(chat)
        self.assertEqual(chat.batch_remote_chat.call_count, 2)
        self.assertEqual(len(chat.batch_remote_chat.call_args_list[1].args[0]), 1)
        self.assertEqual(c.papers[1]["attri"], {"ok": True})
        self.assertEqual(c.attri_repaired, 1)


if __name__ == "__main__":
    unittest.main()
