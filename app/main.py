from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
import time
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.config import settings
import logging
from app.core.logging import setup_logging
from app.db.session import get_db
from app.api.v1 import auth, organizations, projects, tasks, reports, health

setup_logging()

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(organizations.router, prefix=f"{settings.API_V1_STR}/organizations", tags=["organizations"])
app.include_router(projects.router, prefix=f"{settings.API_V1_STR}/organizations/{{org_id}}/projects", tags=["projects"])
app.include_router(tasks.router, prefix=f"{settings.API_V1_STR}/organizations/{{org_id}}/projects/{{project_id}}/tasks", tags=["tasks"])
app.include_router(reports.router, prefix=f"{settings.API_V1_STR}/organizations/{{org_id}}/reports", tags=["reports"])
app.include_router(health.router, tags=["health"])

@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    start_time = time.time()
    
    logger = logging.getLogger("fastapi.request")
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Request-ID"] = request_id
        
        logger.info(
            "Request processed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "processing_time": process_time
            }
        )
        return response
    except Exception as exc:
        process_time = time.time() - start_time
        logger.error(
            "Request failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "processing_time": process_time
            },
            exc_info=True
        )
        raise exc

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log the exception using the existing logging infrastructure
    logger = logging.getLogger(__name__)
    logger.error(f"Unexpected error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


