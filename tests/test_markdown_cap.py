"""content_generator 의 contains_markdown 재요청 루프 상한(SURVEYX_MARKDOWN_RETRY_MAX) — API 호출 없이 mock.

상한 미설정(0) = 원 SurveyX 동작(markdown 이 없어질 때까지 무한 재요청), 설정 시 그 횟수 후 마지막 응답 채택.
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import src.models.generator.content_generator as cg  # noqa: E402


class FakeChat:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def remote_chat(self, prompt, model=None):
        self.calls += 1
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


def gen():
    return cg.ContentGenerator.__new__(cg.ContentGenerator)  # __init__ 은 task 디렉터리가 필요해 건너뛴다


class MarkdownCapTest(unittest.TestCase):
    def test_unset_keeps_original_loop(self):
        chat = FakeChat(["i.e., *L* x"] * 25 + ["plain text"])
        with mock.patch.object(cg, "CONTENT_MARKDOWN_RETRY_MAX", 0):
            res = gen().chat_until_no_markdown(chat, "p", where="t")
        self.assertEqual(res, "plain text")
        self.assertEqual(chat.calls, 26)

    def test_cap_adopts_last_response(self):
        chat = FakeChat(["i.e., *L* x"])
        with mock.patch.object(cg, "CONTENT_MARKDOWN_RETRY_MAX", 10), \
                self.assertLogs(cg.logger.name, level="WARNING") as lg:
            res = gen().chat_until_no_markdown(chat, "p", where="t")
        self.assertEqual(chat.calls, 10)
        self.assertEqual(res, "i.e., *L* x")
        self.assertTrue(any("markdown retry cap" in m for m in lg.output))

    def test_cap_not_hit_when_clean(self):
        chat = FakeChat(["**a**", "clean"])
        with mock.patch.object(cg, "CONTENT_MARKDOWN_RETRY_MAX", 10):
            res = gen().chat_until_no_markdown(chat, "p", where="t")
        self.assertEqual((res, chat.calls), ("clean", 2))


if __name__ == "__main__":
    unittest.main()
