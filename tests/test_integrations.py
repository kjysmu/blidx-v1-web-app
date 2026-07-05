from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_integration_status_never_exposes_secret_values():
    response = client.get("/api/integrations/status")

    assert response.status_code == 200
    data = response.json()
    assert "anthropic" in data
    assert "database" in data
    assert "linkedin" in data
    assert "payloadcms" in data
    assert "api_key" not in str(data).lower()
    assert "secret" not in str(data).lower()
    assert "postgresql://" not in str(data).lower()
    assert "database_url" not in str(data).lower()


def test_admin_requires_configured_credentials():
    response = client.get("/admin")

    assert response.status_code in {401, 503}
