"""集成测试:HTTP 服务、模型层、CLI 三条链路各跑一遍真实路径。

单测只测规则函数;这里关心的是「接上之后还能不能正常工作」——
HTTP 真的起服务、模型返回真的按本仓 schema 解析、CLI 真的走子进程。
"""

import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from dingyue import agent, llm, web
from dingyue import db as dbmod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BILL = """2026-11-20 iCloud+ 200G 连续包月 ¥6.00
2026年11月3日 爱奇艺 黄金VIP 首月 9.9 元，次月起 25 元/月
2026-11-09 Steam 钱包充值 30 元 一次性
"""


class TestHttpLayer(unittest.TestCase):
    """真起 ThreadingHTTPServer,随机端口,走真实 HTTP。"""

    @classmethod
    def setUpClass(cls):
        cls.dbpath = os.path.join(ROOT, "data", "_test_http.db")
        dbmod.use(cls.dbpath)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0),
                                        web._handler({"api_key": None}, True, cls.dbpath))
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _get(self, path):
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (self.port, path), timeout=10) as r:
            return r.status, r.read().decode("utf-8")

    def _post(self, path, payload):
        import urllib.error
        import urllib.request
        req = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, path),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_page_served(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("订阅", body)
        # 页面自己就要能说明一次性支出与退款窗口,不能只丢一行总数
        self.assertIn("一次性", body)
        self.assertIn("退款窗口", body)

    def test_status_mock(self):
        status, body = self._get("/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"mock": True, "model": None})

    def test_scan_numbers(self):
        status, r = self._post("/api/scan", {"text": BILL})
        self.assertEqual(status, 200)
        self.assertEqual(r["mode"], "offline")
        self.assertEqual(r["total"], 72 + 300)
        self.assertEqual(r["subscription_count"], 2)
        self.assertEqual(r["one_off_count"], 1)
        self.assertEqual(r["one_off_total"], 30)
        rows = {x["merchant"]: x for x in r["rows"]}
        self.assertEqual(rows["iCloud+"]["amount"], 6)
        self.assertEqual(rows["爱奇艺"]["amount"], 25)
        self.assertEqual(rows["Steam"]["cycle"], "一次性")
        self.assertIsNone(rows["Steam"]["next"])

    def test_scan_flags_promo(self):
        status, r = self._post("/api/scan", {"text": BILL})
        self.assertEqual(status, 200)
        notes = "".join(n for f in r["flags"] for n in f["notes"])
        self.assertIn("首月", notes)

    def test_scan_uses_zero(self):
        status, r = self._post("/api/scan", {"text": BILL, "uses": {"爱奇艺": "0"}})
        self.assertEqual(status, 200)
        top = r["cut"][0]
        self.assertEqual(top["merchant"], "爱奇艺")
        self.assertEqual(top["uses"], 0)

    def test_scan_saved_to_db(self):
        status, r = self._post("/api/scan", {"text": BILL})
        self.assertEqual(status, 200)
        self.assertIsInstance(r["saved_id"], int)
        self.assertTrue(any(row["id"] == r["saved_id"] for row in dbmod.ledgers(5)))

    def test_unknown_path_404(self):
        status, r = self._post("/api/nope", {})
        self.assertEqual(status, 404)
        self.assertIn("error", r)

    def test_unknown_post_path_drains_body(self):
        # 把请求体拆成两段发,中间留 50ms:服务端如果没把 body 读完就回 404 并关连接,
        # Windows 会给在途数据回 RST,客户端拿不到那个 404(实测 WinError 10054)。
        import socket
        import time
        body = ('{"text": "%s"}' % ("x" * 40000)).encode("utf-8")
        s = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        try:
            s.sendall(b"POST /api/nope HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                      b"Content-Type: application/json\r\n"
                      b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n")
            time.sleep(0.05)
            s.sendall(body)
            raw = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                raw += chunk
        except OSError as e:
            self.fail("服务端没读完请求体就关连接，客户端收到 %r" % (e,))
        finally:
            s.close()
        self.assertTrue(raw.startswith(b"HTTP/1."), raw[:60])
        self.assertIn(b"404", raw.split(b"\r\n")[0])
        self.assertIn(b"not found", raw)


class FakeLLM:
    """按本仓 schema 回:{"summary": "", "advice": [], "risks": []}。"""

    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    def __call__(self, messages, **kwargs):
        self.prompts.append(messages)
        return json.dumps(self.payload, ensure_ascii=False)


class TestModelLayer(unittest.TestCase):
    def setUp(self):
        self.cfg = {"api_key": "test-key", "base_url": "http://127.0.0.1:9", "model": "fake"}

    def _run(self, payload, text=BILL, uses=None, force_mock=False):
        fake = FakeLLM(payload)
        with mock.patch.object(llm, "chat", fake):
            r = agent.analyze(text, uses, force_mock=force_mock, config=self.cfg)
        return r, fake

    def test_schema_fields(self):
        r, fake = self._run({"summary": "视频占大头", "advice": ["先砍视频"],
                             "risks": ["拒绝站外支付"]})
        self.assertEqual(r["mode"], "model")
        self.assertEqual(r["summary"], "视频占大头")
        self.assertEqual(r["advice"], ["先砍视频"])
        self.assertEqual(r["risks"], ["拒绝站外支付"])
        self.assertTrue(fake.prompts)

    def test_prompt_carries_schema_numbers(self):
        r, fake = self._run({"summary": "x", "advice": ["y"], "risks": ["z"]})
        prompt = fake.prompts[0][0]["content"]
        self.assertIn("one_off_total", prompt)
        self.assertIn("Steam", prompt)

    def test_money_is_stripped(self):
        r, _ = self._run({"summary": "每年 300 元花在视频", "advice": ["先砍掉 30 元那项"],
                          "risks": []})
        self.assertNotIn("300", r["summary"])
        self.assertNotIn("30", r["advice"][0])

    def test_empty_model_answer_falls_back_local(self):
        r, _ = self._run({"summary": "", "advice": [], "risks": []})
        self.assertTrue(r["advice"])
        self.assertTrue(r["risks"])

    def test_force_mock_wins_over_key(self):
        r, fake = self._run({"summary": "x"}, force_mock=True)
        self.assertEqual(r["mode"], "offline")
        self.assertFalse(fake.prompts)


class TestCliLayer(unittest.TestCase):
    def _run(self, args, stdin=None):
        return subprocess.run(
            [sys.executable, "-m", "dingyue"] + args,
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", input=stdin,
        )

    def test_scan_file_end_to_end(self):
        r = self._run(["--mock", "scan", "--file", "examples/case-04.txt",
                       "--uses", "酷狗音乐:0"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("共 3 项订阅", r.stdout)
        self.assertIn("另有 1 笔一次性支出", r.stdout)
        self.assertIn("一次都没用,直接砍", r.stdout)
        self.assertIn("| Steam | 游戏 | 30.0 | 一次性 | 30.0 | — |", r.stdout)

    def test_scan_missing_file_exit_2(self):
        r = self._run(["--mock", "scan", "--file", "examples/_not_here.txt"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("读不到文件", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_scan_empty_text_exit_2(self):
        r = self._run(["--mock", "scan", "--text", "   "])
        self.assertEqual(r.returncode, 2)

    def test_next_skips_one_off(self):
        r = self._run(["next", "--file", "examples/case-04.txt"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("续费日历", r.stdout)
        self.assertNotIn("Steam", r.stdout)

    def test_json_is_machine_readable(self):
        r = self._run(["--mock", "--json", "scan", "--file", "examples/case-01.txt"])
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout)
        self.assertEqual(data["total"], 912.0)

    def test_merchant_command(self):
        r = self._run(["merchant", "--name", "山姆"])
        self.assertEqual(r.returncode, 0)
        self.assertIn("山姆会员", r.stdout)


if __name__ == "__main__":
    unittest.main()
