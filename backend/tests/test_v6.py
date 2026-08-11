"""V6 测试：系统通知。"""
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_notifications():
    # 上报
    r = client.post("/api/notifications", json={"message": "创建了待办", "category": "success", "target_type": "todo", "target_id": 1})
    assert r.status_code == 200, r.text
    r = client.post("/api/notifications", json={"message": "更新了文献"})
    assert r.status_code == 200

    # 列表 + 未读数
    r = client.get("/api/notifications")
    body = r.json()
    assert body["unread"] == 2
    assert len(body["items"]) == 2

    # 单条已读
    nid = body["items"][0]["id"]
    client.post(f"/api/notifications/{nid}/read")
    body = client.get("/api/notifications").json()
    assert body["unread"] == 1

    # 全部已读
    client.post("/api/notifications/read-all")
    body = client.get("/api/notifications").json()
    assert body["unread"] == 0

    # 空消息拒绝
    assert client.post("/api/notifications", json={"message": ""}).status_code == 400
