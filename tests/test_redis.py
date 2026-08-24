import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.core.redis import redis_client, get_cache, set_cache, delete_cache
import uuid

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(autouse=True)
def run_around_tests():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    redis_client.flushall()
    yield
    Base.metadata.drop_all(bind=engine)
    redis_client.flushall()

def test_redis_connectivity():
    assert redis_client.ping() == True

def test_cache_set_get_delete():
    key = "test_key"
    val = {"hello": "world"}
    assert set_cache(key, val, ttl=10) == True
    
    cached = get_cache(key)
    assert cached == val
    
    assert delete_cache(key) == True
    assert get_cache(key) is None

def test_rate_limiting():
    # Make multiple requests to a rate-limited endpoint
    # The RateLimiter default could be 5000 per 60s
    # We will mock redis to pretend we are at the limit
    from unittest.mock import patch
    
    login_data = {"email": "invalid@example.com", "password": "abc"}
    
    # Normal request
    resp1 = client.post("/api/v1/auth/login", json=login_data)
    assert resp1.status_code == 401 # Unauthorized (not rate limited)
    
    # Rate limited request
    with patch("app.core.redis.redis_client.get", return_value="5000"):
        resp2 = client.post("/api/v1/auth/login", json=login_data)
        assert resp2.status_code == 429

def test_cache_aside_behavior():
    # Setup Org, User, Project
    # We'll just use the REST API
    
    # 1. Register User & Login
    email = f"cache_user_{uuid.uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    login_resp = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Create Org
    org_resp = client.post("/api/v1/organizations", json={"name": "Cache Org"}, headers=headers)
    org_id = org_resp.json()["id"]
    
    # 3. Create Project
    proj_resp = client.post(f"/api/v1/organizations/{org_id}/projects", json={"name": "Cache Project"}, headers=headers)
    proj_id = proj_resp.json()["id"]
    
    # 4. Get Project (should hit DB, then cache it)
    cache_key = f"tenant:{org_id}:project:{proj_id}"
    delete_cache(cache_key) # Ensure clean state
    
    get_resp = client.get(f"/api/v1/organizations/{org_id}/projects/{proj_id}", headers=headers)
    assert get_resp.status_code == 200
    
    # Verify it is in cache now
    cached = get_cache(cache_key)
    assert cached is not None
    assert cached["name"] == "Cache Project"
    
    # 5. Update Project (should invalidate cache)
    client.patch(f"/api/v1/organizations/{org_id}/projects/{proj_id}", json={"name": "Updated Project"}, headers=headers)
    
    assert get_cache(cache_key) is None
    
    # 6. Delete Project (should invalidate cache)
    get_resp2 = client.get(f"/api/v1/organizations/{org_id}/projects/{proj_id}", headers=headers)
    assert get_cache(cache_key) is not None # Cached again
    
    client.delete(f"/api/v1/organizations/{org_id}/projects/{proj_id}", headers=headers)
    assert get_cache(cache_key) is None

def test_cross_tenant_cache_isolation():
    # User A in Org A creates Project A
    email_a = f"usera_{uuid.uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={"email": email_a, "password": "password123"})
    token_a = client.post("/api/v1/auth/login", json={"email": email_a, "password": "password123"}).json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}
    
    org_a = client.post("/api/v1/organizations", json={"name": "Org A"}, headers=headers_a).json()["id"]
    proj_a = client.post(f"/api/v1/organizations/{org_a}/projects", json={"name": "Proj A"}, headers=headers_a).json()["id"]
    
    # User B in Org B
    email_b = f"userb_{uuid.uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={"email": email_b, "password": "password123"})
    token_b = client.post("/api/v1/auth/login", json={"email": email_b, "password": "password123"}).json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}
    
    org_b = client.post("/api/v1/organizations", json={"name": "Org B"}, headers=headers_b).json()["id"]
    
    # Cache Proj A in Org A
    client.get(f"/api/v1/organizations/{org_a}/projects/{proj_a}", headers=headers_a)
    cache_key_a = f"tenant:{org_a}:project:{proj_a}"
    assert get_cache(cache_key_a) is not None
    
    # User B tries to fetch Proj A using Org B's context
    # The route will check cache_key_b = f"tenant:{org_b}:project:{proj_a}"
    resp_b = client.get(f"/api/v1/organizations/{org_b}/projects/{proj_a}", headers=headers_b)
    
    # Should be 404 (or 403) and completely isolated
    assert resp_b.status_code == 404
    
    cache_key_b = f"tenant:{org_b}:project:{proj_a}"
    assert get_cache(cache_key_b) is None

def test_redis_failure_handling():
    from unittest.mock import patch
    import redis

    with patch("app.core.redis.redis_client.get", side_effect=redis.RedisError("Connection failed")):
        # Should gracefully return None instead of crashing
        assert get_cache("some_key") is None
        
    with patch("app.core.redis.redis_client.set", side_effect=redis.RedisError("Connection failed")):
        # Should gracefully return False
        assert set_cache("some_key", {"data": "test"}, 10) is False

    with patch("app.core.redis.redis_client.delete", side_effect=redis.RedisError("Connection failed")):
        # Should gracefully return False
        assert delete_cache("some_key") is False

def test_rate_limiter_error_handling():
    from unittest.mock import patch
    import redis
    
    # User B in Org B
    email_b = f"userb_{uuid.uuid4()}@example.com"
    client.post("/api/v1/auth/register", json={"email": email_b, "password": "password123"})
    
    with patch("app.core.redis.redis_client.pipeline", side_effect=redis.RedisError("Connection failed")):
        # Should bypass rate limiter without crashing
        resp = client.post("/api/v1/auth/login", json={"email": email_b, "password": "password123"})
        assert resp.status_code == 200
