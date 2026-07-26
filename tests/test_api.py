from fastapi.testclient import TestClient

from app.main import app


def test_health_and_question_api(isolated_data):
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["schema_version"] == 1

        response = client.post(
            "/api/questions",
            data={
                "block_code": "LX",
                "type_code": "JC",
                "difficulty": "2",
                "year": "2026",
                "source": "接口测试",
                "question_text": "测试题目",
                "answer_text": "A",
                "analysis_text": "测试解析",
                "knowledge_points": "速度",
            },
        )
        assert response.status_code == 200
        assert response.json()["id"] == "LXJC0001"

        search = client.get("/api/questions", params={"block": "力学", "knowledge": "速度"})
        assert search.status_code == 200
        assert search.json()["items"][0]["id"] == "LXJC0001"

        detail = client.get("/api/questions/LXJC0001")
        assert detail.status_code == 200
        assert detail.json()["metadata"]["难度系数"] == "2"

        updated = client.put(
            "/api/questions/LXJC0001",
            json={
                "metadata": {"知识点": ["速度", "加速度"]},
                "sections": {"题目": "修改后的测试题目"},
            },
        )
        assert updated.status_code == 200

        integrity = client.get("/api/integrity")
        assert integrity.status_code == 200
        assert integrity.json()["ok"] is True

        deleted = client.delete("/api/questions/LXJC0001")
        assert deleted.status_code == 200
        trash_id = deleted.json()["trash_id"]
        assert client.get("/api/questions/LXJC0001").status_code == 404

        restored = client.post(f"/api/trash/{trash_id}/restore")
        assert restored.status_code == 200
        assert client.get("/api/questions/LXJC0001").status_code == 200

        unsafe = client.get("/api/questions/../../secrets")
        assert unsafe.status_code in {400, 404}
