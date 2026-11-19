import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import httpx
import pytest

from yanji import db
from yanji.flask_app import create_app


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("YANJI_RUNTIME", str(tmp_path / "runtime"))
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "matplotlib"))
    monkeypatch.setenv("YANJI_API_KEY", "")
    db.initialize()


@pytest.fixture
def client():
    with httpx.Client(
        transport=httpx.WSGITransport(app=create_app()), base_url="http://testserver"
    ) as c:
        yield c


@pytest.fixture
def project(client):
    return client.post("/api/v1/projects", json={"name": "测试研究"}).json()


@pytest.fixture
def example(client):
    return client.post("/api/v1/examples").json()
