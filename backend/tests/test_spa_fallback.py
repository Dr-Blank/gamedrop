"""The built SPA answers page routes without swallowing API paths."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(name="spa")
def spa_fixture(client: TestClient, tmp_path: Path):
    (tmp_path / "index.html").write_text("<!doctype html>spa")
    (tmp_path / "robots.txt").write_text("User-agent: *")
    with patch("main.STATIC_DIR", tmp_path):
        yield client


def test_a_page_route_serves_the_spa(spa: TestClient):
    r = spa.get("/stores/shop-a")
    assert r.status_code == 200
    assert "spa" in r.text


def test_a_built_file_is_served_as_is(spa: TestClient):
    assert spa.get("/robots.txt").text == "User-agent: *"


def test_an_unknown_api_path_is_a_json_404(spa: TestClient):
    r = spa.get("/api/no-such-thing")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}


def test_an_api_path_without_its_slash_still_redirects(spa: TestClient):
    r = spa.get("/api/settings")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_a_path_outside_the_build_is_not_served(spa: TestClient):
    r = spa.get("/..%2F..%2Fetc%2Fpasswd")
    assert "spa" in r.text
