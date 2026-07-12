import re

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root():
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Blidx WorkDesk" in response.text

    asset_versions = re.findall(
        r'/assets/(?:styles\.css|app\.js)\?v=([^"\']+)',
        response.text,
    )
    assert len(asset_versions) == 2
    assert len(set(asset_versions)) == 1
