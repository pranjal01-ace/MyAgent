import sys
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.main import app

class TestAPIEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_check(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertIn(res.json().get("status"), ["online", "ok"])

    def test_conversations_endpoint(self):
        res = self.client.get("/api/conversations")
        self.assertEqual(res.status_code, 200)
        self.assertIn("messages", res.json())

    def test_memories_endpoint(self):
        res = self.client.get("/api/memories/detailed")
        self.assertEqual(res.status_code, 200)
        self.assertIn("memories", res.json())

    def test_voice_status_and_stop(self):
        status_res = self.client.get("/api/voice/status")
        self.assertEqual(status_res.status_code, 200)
        self.assertIn("is_speaking", status_res.json())

        stop_res = self.client.post("/api/voice/stop")
        self.assertEqual(stop_res.status_code, 200)
        self.assertEqual(stop_res.json().get("status"), "interrupted")

    def test_session_id_boundary_validation(self):
        # 64 characters: accepted
        valid_id = "s" * 64
        res_64 = self.client.get(f"/api/conversations?session_id={valid_id}")
        self.assertEqual(res_64.status_code, 200)

        # 65 characters: HTTP 422 Unprocessable Entity
        invalid_65 = "s" * 65
        res_65 = self.client.get(f"/api/conversations?session_id={invalid_65}")
        self.assertEqual(res_65.status_code, 422)

        # 1000 characters: HTTP 422 Unprocessable Entity
        invalid_1000 = "s" * 1000
        res_1000 = self.client.get(f"/api/conversations?session_id={invalid_1000}")
        self.assertEqual(res_1000.status_code, 422)

        # POST /api/chat boundary validation
        chat_req_64 = {"message": "hello", "session_id": "c" * 64}
        chat_res_64 = self.client.post("/api/chat", json=chat_req_64)
        # Should not be 422 or 500
        self.assertNotEqual(chat_res_64.status_code, 422)
        self.assertNotEqual(chat_res_64.status_code, 500)

        chat_req_65 = {"message": "hello", "session_id": "c" * 65}
        chat_res_65 = self.client.post("/api/chat", json=chat_req_65)
        self.assertEqual(chat_res_65.status_code, 422)

if __name__ == "__main__":
    unittest.main()
