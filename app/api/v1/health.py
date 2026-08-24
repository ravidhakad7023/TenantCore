from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import get_db
from app.core.redis import redis_client

router = APIRouter()

@router.get("/health")
def health_check():
    """Liveness check"""
    return {"status": "ok"}

@router.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    """Readiness check: Verify dependencies are reachable"""
    dependencies_status = {
        "postgres": False,
        "redis": False
    }
    
    # Check PostgreSQL
    try:
        db.execute(text("SELECT 1"))
        dependencies_status["postgres"] = True
    except Exception:
        pass

    # Check Redis
    try:
        if redis_client.ping():
            dependencies_status["redis"] = True
    except Exception:
        pass

    if all(dependencies_status.values()):
        return {"status": "ok", "dependencies": dependencies_status}
    
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "error", "dependencies": dependencies_status}
    )
