from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_readiness_check_success():
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "dependencies": {
            "postgres": True,
            "redis": True
        }
    }

def test_readiness_check_postgres_failure():
    from unittest.mock import patch
    with patch("app.api.v1.health.Session.execute", side_effect=Exception("DB Failure")):
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "error"
        assert response.json()["dependencies"]["postgres"] == False
        # Redis should still be True in test environment
        assert response.json()["dependencies"]["redis"] == True

def test_readiness_check_redis_failure():
    from unittest.mock import patch
    with patch("app.api.v1.health.redis_client.ping", side_effect=Exception("Redis Failure")):
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "error"
        assert response.json()["dependencies"]["postgres"] == True
        assert response.json()["dependencies"]["redis"] == False

def test_global_exception_handler():
    from app.main import global_exception_handler
    import asyncio
    import json
    
    # Directly invoke the handler to avoid TestClient raising the exception
    response = asyncio.run(global_exception_handler(None, Exception("Unexpected boom")))
    assert response.status_code == 500
    assert json.loads(response.body)["detail"] == "Internal server error"
