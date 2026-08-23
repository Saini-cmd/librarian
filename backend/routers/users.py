from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from core.db import get_db
from core.repositories.users import upsert_user


router = APIRouter(prefix="/api/users", tags=["users"])


class UserProfile(BaseModel):
    id: str
    clerk_id: str
    email: str | None = None
    name: str | None = None


class UserUpdate(BaseModel):
    name: str | None = None


def _to_profile(user) -> UserProfile:
    return UserProfile(
        id=str(user.id),
        clerk_id=user.clerk_id,
        email=user.email,
        name=user.name,
    )


@router.get("/me", response_model=UserProfile)
def get_me(
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserProfile:
    user = upsert_user(db, clerk_id)
    return _to_profile(user)


@router.patch("/me", response_model=UserProfile)
def update_me(
    payload: UserUpdate,
    clerk_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserProfile:
    user = upsert_user(db, clerk_id, name=payload.name)
    return _to_profile(user)
