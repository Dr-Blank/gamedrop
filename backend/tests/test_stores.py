from fastapi.testclient import TestClient


def _store_payload(**overrides):
    return {
        "id": "test-store",
        "name": "Test Store",
        "type": "shopify",
        "base_url": "https://example.com",
        "collection_path": "/collections/board-games",
        **overrides,
    }


def test_list_stores_empty(client: TestClient):
    r = client.get("/api/stores/")
    assert r.status_code == 200
    assert r.json() == []


def test_create_store(client: TestClient):
    r = client.post("/api/stores/", json=_store_payload())
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "test-store"
    assert data["name"] == "Test Store"
    assert data["enabled"] is True


def test_list_stores_after_create(client: TestClient):
    client.post("/api/stores/", json=_store_payload())
    r = client.get("/api/stores/")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_update_store(client: TestClient):
    client.post("/api/stores/", json=_store_payload())
    r = client.patch(
        "/api/stores/test-store", json={"name": "Updated", "enabled": False}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "Updated"
    assert data["enabled"] is False


def test_update_store_not_found(client: TestClient):
    r = client.patch("/api/stores/nonexistent", json={"name": "X"})
    assert r.status_code == 404


def test_delete_store(client: TestClient):
    client.post("/api/stores/", json=_store_payload())
    r = client.delete("/api/stores/test-store")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert client.get("/api/stores/").json() == []


def test_delete_store_not_found(client: TestClient):
    r = client.delete("/api/stores/nonexistent")
    assert r.status_code == 404


def test_list_products_for_store(client: TestClient):
    client.post("/api/stores/", json=_store_payload())
    r = client.get("/api/stores/test-store/products")
    assert r.status_code == 200
    assert r.json() == []
