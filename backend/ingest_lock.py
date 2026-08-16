"""Distributed ingest lock (Redis primary, in-process fallback).

Two mechanisms live here:

1. **`IngestLock`** — serializes ingestion of the same repo commit so
   concurrent users never run duplicate pipelines. Redis ``SET NX EX`` is
   atomic across uvicorn workers and processes; when Redis is down the lock
   degrades to a process-global per-key ``threading.Lock`` (single-process only
   — same "degrade gracefully, never break" philosophy as chat memory). The
   owner holds a random token; only the owner can release or renew the lock.

2. **`GlobalIngestGate`** — caps how many pipelines run **concurrently across
   all users/commits** (a Redis counter with an atomic Lua acquire/release,
   bounded-semaphore fallback when Redis is down), so bursts of ingests don't
   saturate OpenRouter/DeepSeek.

Keys for the per-commit lock are the repo's **commit hash** (``repo_hash``) —
the commit is the unit of ingestion work, and the same commit is globally
unique. Env knobs (see ``.env.example``): ``INGEST_LOCK_TTL_SECONDS`` (default
900 — extended by a heartbeat while a pipeline runs), ``INGEST_WAIT_MAX_SECONDS``
(default 1800 — how long a second caller waits before giving up),
``INGEST_WAIT_POLL_SECONDS`` (default 2), ``INGEST_MAX_CONCURRENT`` (default 2 —
global concurrent-pipeline cap; 0 disables the gate).
"""

import logging
import os
import threading
import time
import uuid

from dotenv import load_dotenv


load_dotenv()

logger = logging.getLogger(__name__)

LOCK_PREFIX = "ingest_lock:"

LOCK_TTL_SECONDS = int(os.getenv("INGEST_LOCK_TTL_SECONDS", "900"))
LOCK_WAIT_MAX_SECONDS = int(os.getenv("INGEST_WAIT_MAX_SECONDS", "1800"))
LOCK_POLL_SECONDS = float(os.getenv("INGEST_WAIT_POLL_SECONDS", "2"))
INGEST_MAX_CONCURRENT = int(os.getenv("INGEST_MAX_CONCURRENT", "2"))

_COMPARE_AND_DEL = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('del', KEYS[1]) else return 0 end"
)
_RENEW_IF_OWNER = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end"
)
_GATE_ACQUIRE = (
    "local v = redis.call('incr', KEYS[1])\n"
    "if v <= tonumber(ARGV[1]) then\n"
    "  redis.call('expire', KEYS[1], ARGV[2])\n"
    "  return 1\n"
    "else\n"
    "  redis.call('decr', KEYS[1])\n"
    "  return 0\n"
    "end"
)
_GATE_RELEASE = (
    "local v = redis.call('get', KEYS[1]) or 0\n"
    "if tonumber(v) > 0 then return redis.call('decr', KEYS[1]) else return 0 end"
)


class _RedisHolder:
    """Lazy process-wide Redis client with short timeouts (fail fast when down)."""

    _client = None

    @classmethod
    def get(cls):
        if cls._client is None:
            import redis

            cls._client = redis.Redis.from_url(
                os.getenv("REDIS_URL", "redis://localhost:6379/0"),
                socket_connect_timeout=1,
                socket_timeout=1,
                decode_responses=True,
            )
        return cls._client


class IngestLock:
    """Owner-token lock. One instance per acquire→release lifecycle.

    The in-process fallback state is class-level so a second request in the
    same process observes the same lock even though it holds its own instance.
    """

    _inproc_locks: dict[str, threading.Lock] = {}
    _inproc_meta = threading.Lock()

    def __init__(self):
        self._token = uuid.uuid4().hex
        self._redis = _RedisHolder.get()
        self._key_used: str | None = None
        self._mode: str | None = None  # "redis" | "inproc"

    def _rkey(self, key: str) -> str:
        return f"{LOCK_PREFIX}{key}"

    @classmethod
    def _inproc(cls, key: str) -> threading.Lock:
        with cls._inproc_meta:
            if key not in cls._inproc_locks:
                cls._inproc_locks[key] = threading.Lock()
            return cls._inproc_locks[key]

    def acquire(self, key: str) -> bool:
        self._key_used = key
        try:
            ok = self._redis.set(self._rkey(key), self._token, nx=True, ex=LOCK_TTL_SECONDS)
        except Exception:
            # Redis unreachable — fall back to the process-local lock.
            logger.warning("ingest_lock acquire fell back to in-process (Redis down)")
            self._mode = "inproc"
            return self._inproc(key).acquire(blocking=False)
        if ok:
            self._mode = "redis"
            return True
        # `set nx` returned None: another owner holds the lock. NOT a fallback.
        self._mode = None
        self._key_used = None
        return False

    def release(self) -> None:
        """Release the lock if we still own it (compare-and-del on Redis)."""
        if self._key_used is None:
            return
        key = self._key_used
        if self._mode == "redis":
            try:
                self._redis.eval(_COMPARE_AND_DEL, 1, self._rkey(key), self._token)
            except Exception:
                logger.warning("ingest_lock release (redis) failed for %s", key, exc_info=True)
        else:
            self._inproc(key).release()
        self._key_used = None

    def renew(self) -> None:
        """Extend the lock TTL (heartbeat) if we still own it."""
        if self._key_used is None or self._mode != "redis":
            return
        try:
            self._redis.eval(
                _RENEW_IF_OWNER, 1, self._rkey(self._key_used), self._token, LOCK_TTL_SECONDS
            )
        except Exception:
            logger.warning("ingest_lock renew failed for %s", self._key_used, exc_info=True)

    def is_locked(self, key: str) -> bool:
        try:
            return bool(self._redis.exists(self._rkey(key)))
        except Exception:
            return self._inproc(key).locked()

    def wait_for_index(self, key, is_ready, gate: "GlobalIngestGate | None" = None):
        """Wait until a commit is indexed or we take over its ingest.

        Yields ``"waiting"`` between polls; finishes (``return``) with one of:
          - ``"ready"`` — ``is_ready()`` became True (someone indexed it) — reuse.
          - ``"owned"`` — the lock **and** a global gate slot were acquired — the
            caller must run the pipeline.
          - ``"timeout"`` — gave up after ``INGEST_WAIT_MAX_SECONDS``.

        If ``gate`` is given and the global cap is full, the per-commit lock is
        released again and the loop keeps waiting for a slot (a slot is only
        held for the "owned" pipeline run).
        """
        started = time.monotonic()
        while True:
            if is_ready():
                return "ready"
            if not self.is_locked(key) and self.acquire(key):
                if gate is not None and not gate.try_acquire():
                    self.release()  # global cap full — release the commit lock, keep waiting
                else:
                    return "owned"
            if time.monotonic() - started >= LOCK_WAIT_MAX_SECONDS:
                return "timeout"
            yield "waiting"
            time.sleep(LOCK_POLL_SECONDS)


class GlobalIngestGate:
    """Caps concurrent pipelines across all users/commits.

    Redis counter with an atomic Lua acquire (incr → ≤ max → set TTL; else decr
    back) and a floor-0 Lua release. The TTL slides on every acquire and is
    renewed by the pipeline heartbeat, so a crashed pipeline's slot expires
    instead of leaking. When Redis is down it falls back to a process-global
    ``BoundedSemaphore`` (single-process only).
    """

    _KEY = "ingest_global_active"
    _shared_sem: "threading.BoundedSemaphore | None" = None
    _sem_meta = threading.Lock()

    def __init__(self):
        self._redis = _RedisHolder.get()
        self._mode: str | None = None  # "redis" | "inproc"

    @classmethod
    def maybe(cls) -> "GlobalIngestGate | None":
        """Return a gate unless the cap is disabled (INGEST_MAX_CONCURRENT <= 0)."""
        return cls() if INGEST_MAX_CONCURRENT > 0 else None

    @classmethod
    def _semaphore(cls) -> threading.BoundedSemaphore:
        with cls._sem_meta:
            if cls._shared_sem is None:
                cls._shared_sem = threading.BoundedSemaphore(INGEST_MAX_CONCURRENT)
            return cls._shared_sem

    def try_acquire(self) -> bool:
        try:
            ok = self._redis.eval(
                _GATE_ACQUIRE, 1, self._KEY, INGEST_MAX_CONCURRENT, LOCK_TTL_SECONDS
            )
            if ok:
                self._mode = "redis"
                return True
            return False
        except Exception:
            logger.warning("ingest gate fell back to in-process semaphore (Redis down)")
            self._mode = "inproc"
            return self._semaphore().acquire(blocking=False)

    def release(self) -> None:
        if self._mode == "redis":
            try:
                self._redis.eval(_GATE_RELEASE, 1, self._KEY)
            except Exception:
                logger.warning("ingest gate release (redis) failed", exc_info=True)
                # The sliding TTL clears the slot; do not touch the semaphore.
        elif self._mode == "inproc":
            try:
                self._semaphore().release()
            except ValueError:
                pass
        self._mode = None

    def renew(self) -> None:
        """Extend the gate counter's TTL while a pipeline runs (like the lock)."""
        if self._mode != "redis":
            return
        try:
            self._redis.expire(self._KEY, LOCK_TTL_SECONDS)
        except Exception:
            logger.warning("ingest gate renew failed", exc_info=True)


def start_lock_heartbeat(
    lock: IngestLock, gate: GlobalIngestGate | None = None
) -> threading.Event:
    """Renew the lock (+ gate slot) TTL while a pipeline runs.

    Returns a stop ``threading.Event``; the pipeline's ``finally`` sets it.
    """
    stop = threading.Event()

    def _beat():
        interval = max(5.0, LOCK_TTL_SECONDS / 3)
        while not stop.wait(interval):
            lock.renew()
            if gate is not None:
                gate.renew()

    threading.Thread(target=_beat, daemon=True, name="ingest-lock-heartbeat").start()
    return stop
