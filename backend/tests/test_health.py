from fastapi.testclient import TestClient


def test_live(client: TestClient) -> None:
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "commit" in r.json()
    assert r.headers["X-Request-ID"]


def test_ready_checks_database(client: TestClient) -> None:
    r = client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"


def test_request_id_is_propagated(client: TestClient) -> None:
    r = client.get("/health/live", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
