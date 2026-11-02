import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from todo.web import make_server


class WebTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.server = make_server(str(Path(self._tmp.name) / "t.json"), port=0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self._tmp.cleanup()

    def call(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port)
        h = {"Content-Type": "application/json", **(headers or {})}
        c.request(method, path, json.dumps(body) if body is not None else None, h)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, data

    def j(self, *a, **k):
        s, d = self.call(*a, **k)
        return s, json.loads(d)

    def test_index_page(self):
        s, d = self.call("GET", "/")
        self.assertEqual(s, 200)
        self.assertIn(b"<title>Todo</title>", d)

    def test_crud_flow(self):
        s, t = self.j("POST", "/api/tasks", {"title": "Buy milk", "priority": "high", "tags": ["home"]})
        self.assertEqual((s, t["id"]), (201, 1))
        s, sub = self.j("POST", "/api/tasks", {"title": "Oat", "parent": 1})
        self.assertEqual(sub["parent"], 1)
        s, t = self.j("PATCH", "/api/tasks/1", {"title": "Buy oat milk", "due": "2030-01-02"})
        self.assertEqual((t["title"], t["due"]), ("Buy oat milk", "2030-01-02"))
        s, t = self.j("PATCH", "/api/tasks/1", {"due": "", "done": True})
        self.assertTrue(t["done"])
        self.assertIsNone(t["due"])
        s, lst = self.j("GET", "/api/tasks?status=done")
        self.assertEqual([x["id"] for x in lst], [1])
        s, lst = self.j("GET", "/api/tasks?q=oat")
        self.assertEqual(len(lst), 2)
        self.assertEqual(self.j("DELETE", "/api/tasks/1")[0], 200)
        self.assertEqual(self.j("GET", "/api/tasks")[1], [])
        self.assertEqual(self.j("POST", "/api/restore", {})[0], 200)
        self.assertEqual(len(self.j("GET", "/api/tasks")[1]), 2)

    def test_errors(self):
        self.assertEqual(self.j("POST", "/api/tasks", {"title": "  "})[0], 400)
        self.assertEqual(self.j("POST", "/api/tasks", {"title": "x", "priority": "urgent"})[0], 400)
        self.assertEqual(self.j("PATCH", "/api/tasks/99", {"title": "x"})[0], 404)
        self.assertEqual(self.j("GET", "/api/tasks?status=bogus")[0], 400)
        self.assertEqual(self.j("GET", "/nope")[0], 404)
        self.assertEqual(self.j("POST", "/api/restore", {})[0], 400)

    def test_requires_json_and_local_host(self):
        s, _ = self.call("POST", "/api/tasks", {"title": "x"}, {"Content-Type": "text/plain"})
        self.assertEqual(s, 415)
        s, _ = self.call("GET", "/api/tasks", headers={"Host": "evil.example.com"})
        self.assertEqual(s, 403)


if __name__ == "__main__":
    unittest.main()
