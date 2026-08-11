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


def test_new_store_has_no_colour(client: TestClient):
    r = client.post("/api/stores/", json=_store_payload())
    assert r.json()["color"] is None


def test_set_store_colour(client: TestClient):
    client.post("/api/stores/", json=_store_payload())
    r = client.patch("/api/stores/test-store", json={"color": "#4F46E5"})
    assert r.status_code == 200
    assert r.json()["color"] == "#4f46e5"


def test_reject_a_colour_that_is_not_hex(client: TestClient):
    client.post("/api/stores/", json=_store_payload())
    r = client.patch("/api/stores/test-store", json={"color": "rebeccapurple"})
    assert r.status_code == 422


def test_clear_store_colour_back_to_default(client: TestClient):
    client.post("/api/stores/", json=_store_payload(color="#4f46e5"))
    r = client.patch("/api/stores/test-store", json={"color": None})
    assert r.json()["color"] is None


def test_patch_without_colour_keeps_it(client: TestClient):
    client.post("/api/stores/", json=_store_payload(color="#4f46e5"))
    r = client.patch("/api/stores/test-store", json={"name": "Renamed"})
    assert r.json()["color"] == "#4f46e5"
    assert r.json()["name"] == "Renamed"
