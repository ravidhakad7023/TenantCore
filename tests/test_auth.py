import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.models import user, organization, membership

SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

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
    yield
    Base.metadata.drop_all(bind=engine)

def test_register_user():
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "id" in data
    assert "password" not in data
    assert "hashed_password" not in data

def test_register_duplicate_user():
    client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "password123"},
    )
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]

def test_login_user():
    client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "password123"},
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_incorrect_password():
    client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "password123"},
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401

def test_get_current_user():
    client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "password123"},
    )
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    token = login_response.json()["access_token"]
    
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "password" not in data

def test_get_current_user_invalid_token():
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer invalidtoken"}
    )
    assert response.status_code == 403

def test_get_current_user_expired_token():
    import jwt
    from datetime import datetime, timedelta, timezone
    from app.core.config import settings

    # Create explicitly expired token
    expire = datetime.now(timezone.utc) - timedelta(minutes=10)
    to_encode = {"exp": expire, "sub": "testuser_id"}
    token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403

def test_get_current_user_invalid_uuid():
    import jwt
    from datetime import datetime, timedelta, timezone
    from app.core.config import settings

    expire = datetime.now(timezone.utc) + timedelta(minutes=10)
    to_encode = {"exp": expire, "sub": "invalid_uuid"}
    token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert "Could not validate" in response.json()["detail"]

def test_get_current_user_not_found():
    import jwt
    from datetime import datetime, timedelta, timezone
    from app.core.config import settings

    expire = datetime.now(timezone.utc) + timedelta(minutes=10)
    to_encode = {"exp": expire, "sub": str(uuid.uuid4())}
    token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404
    assert "User not found" in response.json()["detail"]

def test_missing_auth_header():
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401

def test_malformed_auth_header():
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Malformed"})
    assert response.status_code == 401

