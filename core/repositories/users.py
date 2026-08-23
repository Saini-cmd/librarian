"""User data access (lazy Clerk upsert + profile reads)."""

from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.models import User


def get_user_by_clerk_id(db: Session, clerk_id: str) -> User | None:
    return db.query(User).filter(User.clerk_id == clerk_id).first()


def upsert_user(db: Session, clerk_id: str, **fields: Any) -> User:
    user = get_user_by_clerk_id(db, clerk_id)
    if user is None:
        user = User(clerk_id=clerk_id, **fields)
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            # Concurrent first-upsert for the same clerk_id: the other request
            # won the INSERT. Roll back and adopt its row instead of 500ing.
            db.rollback()
            user = get_user_by_clerk_id(db, clerk_id)
            if user is None:
                raise
            for key, value in fields.items():
                setattr(user, key, value)
            db.commit()
    else:
        for key, value in fields.items():
            setattr(user, key, value)
        db.commit()
    db.refresh(user)
    return user
