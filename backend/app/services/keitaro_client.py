from typing import Any
import httpx

from app.core.config import settings


class KeitaroError(Exception):
    def __init__(self, message: str, status_code: int | None = None, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class KeitaroClient:
    def __init__(self) -> None:
        if not settings.keitaro_base_url or not settings.keitaro_api_key:
            raise KeitaroError("Не настроены KEITARO_BASE_URL и KEITARO_API_KEY")

        base = settings.keitaro_base_url.rstrip("/")
        prefix = "/" + settings.keitaro_api_prefix.strip("/")
        if base.lower().endswith(prefix.lower()):
            self.base_url = base + "/"
        else:
            self.base_url = base + prefix + "/"
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Api-Key": settings.keitaro_api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=settings.keitaro_timeout_seconds,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self.client.request(method, path.lstrip("/"), **kwargs)
        except httpx.TimeoutException as exc:
            raise KeitaroError("Keitaro API не ответил вовремя") from exc
        except httpx.RequestError as exc:
            raise KeitaroError(f"Не удалось подключиться к Keitaro: {exc}") from exc

        try:
            data = response.json() if response.content else None
        except ValueError:
            data = {"raw": response.text}

        if not response.is_success:
            detail = data if isinstance(data, (dict, list)) else {"body": str(data)}
            message = detail.get("message") or detail.get("error") if isinstance(detail, dict) else None
            raise KeitaroError(
                message or f"Keitaro API вернул HTTP {response.status_code}",
                status_code=response.status_code,
                details=detail,
            )
        return data

    async def get(self, path: str, **kwargs: Any) -> Any:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, payload: dict) -> Any:
        return await self.request("POST", path, json=payload)

    async def put(self, path: str, payload: dict) -> Any:
        return await self.request("PUT", path, json=payload)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)
