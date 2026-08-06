from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.state import upsert_user


router = APIRouter(prefix="/api/users", tags=["users"])


class UserProfile(BaseModel):
    id: str
    clerk_id: str
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None


class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None


def _to_profile(user) -> UserProfile:
    return UserProfile(
        id=str(user.id),
        clerk_id=user.clerk_id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        avatar_url=user.avatar_url,
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
    user = upsert_user(db, clerk_id, first_name=payload.first_name, last_name=payload.last_name)
    return _to_profile(user)
