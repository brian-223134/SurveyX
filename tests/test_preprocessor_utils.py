"""전처리 유틸 단위 테스트 — KISTI DOI id 가 파일 경로를 깨뜨리지 않는지.

실행:  /data2/chanjoong/miniforge3/envs/surveyx/bin/python -m unittest discover -s tests -v

2026-09-08 파일럿에서 save_papers 가 `_id` 를 파일명으로 그대로 써서 DOI id 의 '/' 가 하위 디렉터리를
만들었고, DataCleaner.load_json_dir 은 최상위 .json 만 읽어 DOI 논문 84/150 편이 유실됐다.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.modules.preprocessor.utils import safe_filename, save_papers  # noqa: E402
from src.modules.preprocessor.data_cleaner import DataCleaner  # noqa: E402


class SafeFilenameTest(unittest.TestCase):
    def test_arxiv_id_unchanged(self):
        self.assertEqual(safe_filename("2211.01671"), "2211.01671")

    def test_doi_slash_and_colon_replaced(self):
        self.assertEqual(safe_filename("10.1109/tvcg.2019.2934631"), "10.1109_tvcg.2019.2934631")
        self.assertEqual(safe_filename("10.1007/978-3-030:12345"), "10.1007_978-3-030_12345")

    def test_title_fallback_whitespace(self):
        self.assertEqual(safe_filename("A Survey / On Things"), "A_Survey___On_Things")


class SavePapersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_doi_and_arxiv_ids_land_in_one_flat_dir(self):
        papers = [
            {"_id": "2211.01671", "title": "A", "md_text": "x"},
            {"_id": "10.1109/tvcg.2019.2934631", "title": "B", "md_text": "y"},
            {"_id": "10.63345/sjaibt.v2.i4.101", "title": "C", "md_text": "z"},
            {"title": "No Id Paper", "md_text": "w"},
        ]
        out = self.tmp / "jsons"
        save_papers(papers, out)
        files = sorted(p.name for p in out.iterdir())
        self.assertTrue(all(p.is_file() for p in out.iterdir()), "하위 디렉터리가 생기면 안 된다")
        self.assertEqual(files, ["10.1109_tvcg.2019.2934631.json", "10.63345_sjaibt.v2.i4.101.json",
                                 "2211.01671.json", "No_Id_Paper.json"])
        # 내용(_id 포함)은 그대로 — 파일명만 치환된다
        self.assertEqual(json.loads((out / "10.1109_tvcg.2019.2934631.json").read_text())["_id"],
                         "10.1109/tvcg.2019.2934631")

    def test_cleaner_sees_every_saved_paper(self):
        papers = [{"_id": f"10.1109/x.{i}", "title": f"T{i}", "md_text": "body"} for i in range(5)]
        papers.append({"_id": "2301.00001", "title": "arxiv", "md_text": "body"})
        papers.append({"_id": "10.1000/nomd", "title": "no md_text"})
        out = self.tmp / "jsons"
        save_papers(papers, out)
        cleaner = DataCleaner.__new__(DataCleaner)      # __init__ 없이 load_json_dir 만 사용
        cleaner.load_json_dir(out)
        self.assertEqual(len(cleaner.papers), 6)          # md_text 없는 1편만 제외
        self.assertEqual(sorted(p["_id"] for p in cleaner.papers)[:2], ["10.1109/x.0", "10.1109/x.1"])


if __name__ == "__main__":
    unittest.main()
