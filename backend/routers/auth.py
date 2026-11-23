from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models.models import Business, User
from services.auth import create_access_token, get_current_user, hash_password, verify_password
from services.validation import validate_gstin


router = APIRouter(prefix="/auth", tags=["Authentication"])

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., pattern=EMAIL_PATTERN)
    password: str = Field(..., min_length=6, max_length=100)
    business_name: str = Field(..., min_length=2, max_length=150)
    gstin: str = Field(..., min_length=15, max_length=15)


class LoginRequest(BaseModel):
    email: str = Field(..., pattern=EMAIL_PATTERN)
    password: str = Field(..., min_length=1)


class BusinessCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    gstin: str = Field(..., min_length=15, max_length=15)


class BusinessOut(BaseModel):
    id: int
    name: str
    gstin: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    businesses: List[BusinessOut]


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    # 1. Validate GSTIN
    is_valid_gstin, gstin_err = validate_gstin(req.gstin)
    if not is_valid_gstin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=gstin_err)

    # 2. Check if email already registered
    existing_user = db.scalar(select(User).where(User.email == req.email.lower().strip()))
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists.",
        )

    # 3. Check if GSTIN already registered to an existing business
    gstin_clean = req.gstin.strip().upper()
    existing_biz = db.scalar(select(Business).where(Business.gstin == gstin_clean))
    if existing_biz is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"GSTIN '{gstin_clean}' is already registered to another enterprise account.",
        )

    try:
        # 4. Hash password using PBKDF2-SHA256
        hashed_pwd = hash_password(req.password)

        # 5. Create User
        user = User(
            name=req.name.strip(),
            email=req.email.lower().strip(),
            password=hashed_pwd,
        )
        db.add(user)
        db.flush()

        # 6. Create initial Business for user
        business = Business(
            name=req.business_name.strip(),
            gstin=gstin_clean,
            user_id=user.id,
        )
        db.add(business)
        db.flush()

        db.commit()
    except Exception:
        db.rollback()
        raise

    # 7. Issue Token
    token = create_access_token(user_id=user.id, email=user.email)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "name": user.name, "email": user.email},
        "businesses": [{"id": business.id, "name": business.name, "gstin": business.gstin}],
    }


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == req.email.lower().strip()))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password. Please verify your credentials and try again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    is_valid, needs_rehash = verify_password(req.password, user.password)

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password. Please verify your credentials and try again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Progressive upgrade: if legacy plaintext, replace with PBKDF2 hash on successful login
    if needs_rehash:
        user.password = hash_password(req.password)
        db.commit()

    token = create_access_token(user_id=user.id, email=user.email)
    businesses = db.scalars(select(Business).where(Business.user_id == user.id)).all()

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "name": user.name, "email": user.email},
        "businesses": [
            {"id": b.id, "name": b.name, "gstin": b.gstin} for b in businesses
        ],
    }


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    businesses = db.scalars(select(Business).where(Business.user_id == current_user.id)).all()
    return {
        "user": {
            "id": current_user.id,
            "name": current_user.name,
            "email": current_user.email,
        },
        "businesses": [
            {"id": b.id, "name": b.name, "gstin": b.gstin} for b in businesses
        ],
    }


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user)):
    """Stateless logout acknowledging token discarding by client."""
    return {"message": "Successfully logged out."}


@router.post("/businesses", response_model=BusinessOut, status_code=status.HTTP_201_CREATED)
def add_business(
    req: BusinessCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    is_valid_gstin, gstin_err = validate_gstin(req.gstin)
    if not is_valid_gstin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=gstin_err)

    gstin_clean = req.gstin.strip().upper()
    existing_biz = db.scalar(select(Business).where(Business.gstin == gstin_clean))
    if existing_biz:
        if existing_biz.user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Business with GSTIN '{gstin_clean}' is already linked to your account.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"GSTIN '{gstin_clean}' is already registered to another enterprise account.",
            )

    try:
        business = Business(name=req.name.strip(), gstin=gstin_clean, user_id=current_user.id)
        db.add(business)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"id": business.id, "name": business.name, "gstin": business.gstin}
