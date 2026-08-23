"""24h per-user usage caps.

Counts cost-bearing actions per user inside a rolling window (default 24h) and
rejects actions that would exceed the configured limit with HTTP 429. Events
are appended to the ``usage_events`` table (one row per action) and counted
with a ``COUNT`` over rows newer than ``now() - USAGE_WINDOW_SECONDS``.

Scalability / concurrency:
- Postgres is shared across uvicorn workers and processes (per D27 / SCALE.md),
  so the counts are globally correct at any concurrency — no in-process or
  Redis state, and the cap keeps working with Redis down (unlike the ingest
  lock, whose in-process fallback is single-process-only).
- ``check_usage`` is the gate (a cheap COUNT) run *before* the costly work. The
  boundary is intentionally soft under a race: two requests that both pass the
  check at exactly the limit can both proceed. For a spend cap this is
  acceptable (overshoot is bounded by concurrency and negligible), and it
  avoids the UX of failing a request that has already spent budget.
- ``record_usage`` runs on its own short-lived session (one INSERT + a per-user
  purge of expired rows), so it never couples to — or holds — a caller's
  transaction.

Actions are grouped so one limit covers several recorded actions:
  - ``ingest``  (USAGE_INGEST_MAX):  repo_ingest (process pipeline) + repo_sync (sync re-ingest)
  - ``message`` (USAGE_MESSAGE_MAX): chat_message (chat / chat/stream) + explain

A limit of 0 disables the cap for that group (matches the ``INGEST_*``
convention); uncapped groups are not recorded at all, so the table stays small.
"""

import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.db import SessionLocal
from core.models import UsageEvent

# Action → group. Add new cost-bearing actions here and (if needed) a group
# limit below; consumers only call check_usage/record_usage with an action name.
ACTION_GROUPS: dict[str, str] = {
    "repo_ingest": "ingest",
    "repo_sync": "ingest",
    "chat_message": "message",
    "explain": "message",
}

GROUP_ACTIONS: dict[str, list[str]] = {}
for _action, _group in ACTION_GROUPS.items():
    GROUP_ACTIONS.setdefault(_group, []).append(_action)


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


USAGE_WINDOW_SECONDS = _env_int("USAGE_WINDOW_SECONDS", 86400)
LIMITS: dict[str, int] = {
    "ingest": _env_int("USAGE_INGEST_MAX", 2),
    "message": _env_int("USAGE_MESSAGE_MAX", 20),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _cutoff() -> datetime:
    return _utcnow() - timedelta(seconds=USAGE_WINDOW_SECONDS)


def _capped() -> bool:
    """Caps are active only when a non-zero window and at least one limit are set."""
    return USAGE_WINDOW_SECONDS > 0 and any(limit > 0 for limit in LIMITS.values())


def group_for(action: str) -> str:
    return ACTION_GROUPS.get(action, action)


def limit_for_group(group: str) -> int:
    return LIMITS.get(group, 0)


def limit_for(action: str) -> int:
    return LIMITS.get(group_for(action), 0)


def _count(db: Session, clerk_id: str, group: str, cutoff: datetime) -> int:
    return (
        db.query(func.count(UsageEvent.id))
        .filter(
            UsageEvent.clerk_id == clerk_id,
            UsageEvent.action.in_(GROUP_ACTIONS[group]),
            UsageEvent.created_at >= cutoff,
        )
        .scalar()
        or 0
    )


def _quota_error(
    db: Session, clerk_id: str, group: str, used: int, limit: int
) -> HTTPException:
    """429 with the group, usage, limit, and the time the oldest counted event
    ages out (when a slot frees up)."""
    resets_at = None
    if used > 0:
        earliest = (
            db.query(func.min(UsageEvent.created_at))
            .filter(
                UsageEvent.clerk_id == clerk_id,
                UsageEvent.action.in_(GROUP_ACTIONS[group]),
                UsageEvent.created_at >= _cutoff(),
            )
            .scalar()
        )
        if earliest is not None:
            resets_at = (earliest + timedelta(seconds=USAGE_WINDOW_SECONDS)).isoformat()
    return HTTPException(
        status_code=429,
        detail={
            "detail": "Daily usage limit reached",
            "group": group,
            "used": used,
            "limit": limit,
            "resets_at": resets_at,
        },
    )


def check_usage(clerk_id: str, action: str) -> None:
    """Fast pre-spend gate: raise 429 if the action's group is already at/over
    its limit. Call before doing any costly work."""
    if not _capped():
        return
    group = group_for(action)
    limit = limit_for(action)
    if limit <= 0:
        return
    db = SessionLocal()
    try:
        used = _count(db, clerk_id, group, _cutoff())
        if used >= limit:
            raise _quota_error(db, clerk_id, group, used, limit)
    finally:
        db.close()


def record_usage(clerk_id: str, action: str) -> None:
    """Append a usage event for an action that actually spent API budget.

    Runs on its own short-lived session; never raises (a request that already
    spent budget must not fail). Expired rows for this user are purged
    opportunistically so the table doesn't grow unboundedly.
    """
    if not _capped():
        return
    if limit_for(action) <= 0:
        return
    db = SessionLocal()
    try:
        db.query(UsageEvent).filter(
            UsageEvent.clerk_id == clerk_id,
            UsageEvent.created_at < _cutoff(),
        ).delete(synchronize_session=False)
        db.add(UsageEvent(clerk_id=clerk_id, action=action))
        db.commit()
    finally:
        db.close()


def usage_status(clerk_id: str) -> dict[str, dict]:
    """Per-group ``{used, limit, resets_at}`` for the caller (for a future
    ``GET /api/usage``). ``limit == 0`` means the group is uncapped."""
    if not _capped():
        return {group: {"used": 0, "limit": 0, "resets_at": None} for group in GROUP_ACTIONS}
    cutoff = _cutoff()
    out: dict[str, dict] = {}
    db = SessionLocal()
    try:
        for group in GROUP_ACTIONS:
            limit = limit_for_group(group)
            used = _count(db, clerk_id, group, cutoff) if limit > 0 else 0
            resets_at = None
            if used > 0:
                earliest = (
                    db.query(func.min(UsageEvent.created_at))
                    .filter(
                        UsageEvent.clerk_id == clerk_id,
                        UsageEvent.action.in_(GROUP_ACTIONS[group]),
                        UsageEvent.created_at >= cutoff,
                    )
                    .scalar()
                )
                if earliest is not None:
                    resets_at = (earliest + timedelta(seconds=USAGE_WINDOW_SECONDS)).isoformat()
            out[group] = {"used": used, "limit": limit, "resets_at": resets_at}
        return out
    finally:
        db.close()
