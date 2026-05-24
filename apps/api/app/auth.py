import httpx
from fastapi import Header

from app.config import get_settings


async def get_optional_user_id(authorization: str | None = Header(default=None)) -> str | None:
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None

    settings = get_settings()
    base_url = settings.supabase_url.rstrip("/")
    headers = {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {token}",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{base_url}/auth/v1/user", headers=headers)
    if response.status_code != 200:
        return None

    payload = response.json()
    user_id = payload.get("id")
    return str(user_id) if user_id else None
