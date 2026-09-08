"""ChatAgent 디코딩 프로파일 단위 테스트 — requests.post 를 mock 해 API 호출 없이 검증한다.

실행:  /data2/chanjoong/miniforge3/envs/surveyx/bin/python -m unittest discover -s tests -v

검증 항목 (docs/kisti-run.md §3)
- SURVEYX_TEMPERATURE 오버라이드가 호출부 temperature(예: outline 0.3)를 덮어쓴다
- SURVEYX_MAX_TOKENS 가 payload 에 실리고, 미설정이면 실리지 않는다
- finish_reason=length → 폐기·재요청(status 2), 정상 응답에서 멈춤(status 1)
- 재요청 소진 → 마지막 응답 채택(status 3); 재요청 off → 즉시 채택(status 3)
- 폐기한 응답의 토큰도 TokenMonitor 에 더해진다
- HTTP 오류는 status 0 으로 기록되고 예외로 올라간다(tenacity 가 재시도)
- update_record: 새 파일의 첫 기록이 두 번 적히지 않는다
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import importlib  # noqa: E402

import requests  # noqa: E402

# src/models/LLM/__init__.py 가 클래스 ChatAgent 를 패키지 속성으로 노출하므로
# `import src.models.LLM.ChatAgent as m` 은 모듈이 아니라 클래스를 잡는다 → import_module 로 모듈을 얻는다.
ca_mod = importlib.import_module("src.models.LLM.ChatAgent")
ChatAgent = ca_mod.ChatAgent


def fake_response(content: str, finish_reason: str, status: int = 200, out_tokens: int = 5):
    r = mock.Mock()
    r.status_code = status
    r.text = json.dumps({
        "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 10, "completion_tokens": out_tokens},
    })
    r.raise_for_status = mock.Mock()
    return r


def profile(**kw):
    """모듈 상수(config 에서 import 된 이름)를 테스트 동안 바꾼다."""
    base = dict(CHAT_TEMPERATURE_OVERRIDE=0.6, CHAT_MAX_TOKENS=8192,
                CHAT_RETRY_TRUNCATED=True, CHAT_MAX_TRUNCATED_RETRY=10)
    base.update(kw)
    return mock.patch.multiple(ca_mod, **base)


class ChatAgentProfileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.stats = Path(self.tmp.name) / "request_stats.txt"
        p = mock.patch.object(ChatAgent, "Request_stats_file", self.stats)
        p.start()
        self.addCleanup(p.stop)
        self.agent = ChatAgent(token="test-token", remote_url="http://mock/chat")

    def statuses(self):
        return [l.split(ChatAgent.Record_splitter)[0] for l in self.stats.read_text().splitlines()]

    # ---- temperature / max_tokens
    def test_override_beats_caller_temperature_and_sets_max_tokens(self):
        with profile(), mock.patch.object(ca_mod.requests, "post", return_value=fake_response("ok", "stop")) as post:
            out = self.agent.remote_chat("hello", temperature=0.3)
        self.assertEqual(out, "ok")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["temperature"], 0.6)
        self.assertEqual(payload["max_tokens"], 8192)
        self.assertEqual(self.statuses(), ["1"])

    def test_unset_profile_keeps_original_behaviour(self):
        with profile(CHAT_TEMPERATURE_OVERRIDE=None, CHAT_MAX_TOKENS=None, CHAT_RETRY_TRUNCATED=False), \
                mock.patch.object(ca_mod.requests, "post", return_value=fake_response("ok", "stop")) as post:
            self.agent.remote_chat("hello", temperature=0.3)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["temperature"], 0.3)
        self.assertNotIn("max_tokens", payload)

    def test_batch_remote_chat_applies_override(self):
        with profile(), mock.patch.object(ca_mod.requests, "post", return_value=fake_response("ok", "stop")) as post:
            res = self.agent.batch_remote_chat(["a", "b"], workers=2)
        self.assertEqual(res, ["ok", "ok"])
        self.assertTrue(all(c.kwargs["json"]["temperature"] == 0.6 for c in post.call_args_list))

    # ---- truncation loop
    def test_truncated_discarded_until_normal_response(self):
        seq = [fake_response("x" * 10, "length"), fake_response("y" * 10, "length"), fake_response("fine", "stop")]
        with profile(), mock.patch.object(ca_mod.requests, "post", side_effect=seq) as post:
            out = self.agent.remote_chat("hello")
        self.assertEqual(out, "fine")
        self.assertEqual(post.call_count, 3)
        self.assertEqual(self.statuses(), ["2", "2", "1"])

    def test_retry_exhausted_accepts_last(self):
        seq = [fake_response(f"t{i}", "length") for i in range(3)]
        with profile(CHAT_MAX_TRUNCATED_RETRY=2), mock.patch.object(ca_mod.requests, "post", side_effect=seq) as post:
            out = self.agent.remote_chat("hello")
        self.assertEqual(out, "t2")
        self.assertEqual(post.call_count, 3)
        self.assertEqual(self.statuses(), ["2", "2", "3"])

    def test_retry_disabled_accepts_truncated_immediately(self):
        with profile(CHAT_RETRY_TRUNCATED=False), \
                mock.patch.object(ca_mod.requests, "post", return_value=fake_response("cut", "length")) as post:
            out = self.agent.remote_chat("hello")
        self.assertEqual(out, "cut")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(self.statuses(), ["3"])

    def test_token_monitor_counts_discarded_responses(self):
        monitor = mock.Mock()
        self.agent.token_monitor = monitor
        seq = [fake_response("x", "length", out_tokens=8192), fake_response("ok", "stop", out_tokens=100)]
        with profile(), mock.patch.object(ca_mod.requests, "post", side_effect=seq):
            self.agent.remote_chat("hello")
        self.assertEqual(monitor.add_token.call_count, 2)
        self.assertEqual([c.kwargs["output_tokens"] for c in monitor.add_token.call_args_list], [8192, 100])

    # ---- http error
    def test_http_error_recorded_and_raised(self):
        r = fake_response("", "stop", status=429)
        r.text = '{"error": "rate limited"}'
        r.raise_for_status = mock.Mock(side_effect=requests.HTTPError("429"))
        # tenacity 데코레이터를 우회해 원 함수만 호출 (재시도 대기 없이 검증)
        raw = ChatAgent.remote_chat.__wrapped__
        with profile(), mock.patch.object(ca_mod.requests, "post", return_value=r):
            with self.assertRaises(requests.HTTPError):
                raw(self.agent, "hello")
        self.assertEqual(self.statuses(), ["0"])
        self.assertIn("429", self.stats.read_text().splitlines()[0].split(ChatAgent.Record_splitter)[1])

    # ---- record file
    def test_update_record_no_duplicate_first_line(self):
        ChatAgent.update_record(1, 200, "req-a", "resp-a")
        ChatAgent.update_record(1, 200, "req-b", "resp-b")
        lines = self.stats.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("1||200||req-a"))


if __name__ == "__main__":
    unittest.main()
