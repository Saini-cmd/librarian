import base64
import json
import logging
import os
from functools import lru_cache

import jwt
import requests
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

load_dotenv()

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

CLERK_PUBLISHABLE_KEY = os.getenv("CLERK_PUBLISHABLE_KEY", "")

if CLERK_PUBLISHABLE_KEY:
    domain_part = CLERK_PUBLISHABLE_KEY.replace("pk_test_", "").replace("pk_live_", "")
    padding = 4 - len(domain_part) % 4
    if padding != 4:
        domain_part += "=" * padding
    try:
        raw = base64.b64decode(domain_part).decode("utf-8")
        decoded_domain = raw.rstrip(".$") if raw.endswith("$") else raw
        CLERK_ISSUER = f"https://{decoded_domain}"
    except Exception:
        CLERK_ISSUER = ""
else:
    CLERK_ISSUER = ""


@lru_cache(maxsize=1)
def _get_jwks():
    if not CLERK_ISSUER:
        raise RuntimeError("CLERK_PUBLISHABLE_KEY not set in environment")

    jwks_url = f"{CLERK_ISSUER}/.well-known/jwks.json"
    response = requests.get(jwks_url, timeout=10)
    response.raise_for_status()
    return response.json()


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = credentials.credentials
    jwks = _get_jwks()

    try:
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwks["keys"][0]))
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=CLERK_ISSUER,
            options={"verify_exp": True},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception as e:
        logger.warning("JWT verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Invalid token")

    clerk_id = payload.get("sub", "")
    if not clerk_id:
        raise HTTPException(status_code=401, detail="Token missing subject claim")

    return clerk_id


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str | None:
    if credentials is None:
        return None
    try:
        return get_current_user(credentials)
    except HTTPException:
        return None
