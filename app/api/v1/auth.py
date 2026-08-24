from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.core.security import get_password_hash, verify_password, create_access_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserResponse
from sqlalchemy import select
from app.api.rate_limit import RateLimiter

router = APIRouter()

@router.post("/register", response_model=UserResponse)
def register(
    user_in: UserCreate,
    db: Session = Depends(get_db),
):
    """
    Register a new user.
    """
    user = db.execute(select(User).where(User.email == user_in.email)).scalar_one_or_none()
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )
    user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.post("/login", response_model=Token)
def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db),
    _=Depends(RateLimiter())
):
    """
    Login user.
    """
    user = db.execute(select(User).where(User.email == login_data.email)).scalar_one_or_none()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
    }

@router.get("/me", response_model=UserResponse)
def read_user_me(
    current_user: User = Depends(get_current_user),
):
    """
    Get current user.
    """
    return current_user
