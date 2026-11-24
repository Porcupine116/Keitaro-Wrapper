import asyncio
import re
import secrets
from typing import Any

from app.core.config import settings
from app.services.keitaro_client import KeitaroClient, KeitaroError


class CampaignService:
    def __init__(self, api: KeitaroClient):
        self.api = api

    @staticmethod
    def _extract_id(data: Any, entity_name: str) -> int:
        if isinstance(data, list) and data:
            data = data[0]
        if not isinstance(data, dict) or data.get("id") is None:
            raise KeitaroError(
                f"Keitaro создал {entity_name}, но не вернул его ID",
                details=data,
            )
        return int(data["id"])

    @staticmethod
    def _alias(name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        slug = slug[:35].strip("-") or "campaign"
        return f"{slug}-{secrets.token_hex(3)}"

    @staticmethod
    def _equal_shares(count: int) -> list[int]:
        if count <= 0:
            return []
        base, remainder = divmod(100, count)
        shares = [base] * count
        if remainder:
            for index in range(count - remainder, count):
                shares[index] += 1
        return shares

    async def references(self) -> dict[str, Any]:
        domains, groups, sources, offers, campaigns = await asyncio.gather(
            self.api.get("domains"),
            self.api.get("groups", params={"type": "campaigns"}),
            self.api.get("traffic_sources"),
            self.api.get("offers"),
            self.api.get("campaigns", params={"limit": 100, "offset": 0}),
        )
        return {
            "domains": self._as_list(domains),
            "groups": self._as_list(groups),
            "traffic_sources": self._as_list(sources),
            "offers": self._as_list(offers),
            "campaigns": self._as_list(campaigns),
        }

    @staticmethod
    def _as_list(value: Any) -> list[dict]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        # На случай обёртки ответа в некоторых сборках/проксирующих слоях.
        if isinstance(value, dict):
            for key in ("data", "items", "results"):
                if isinstance(value.get(key), list):
                    return [item for item in value[key] if isinstance(item, dict)]
        return []

    async def get_campaign_streams(self, campaign_id: int) -> list[dict]:
        data = await self.api.get(f"campaigns/{campaign_id}/streams")
        return self._as_list(data)

    async def create_campaign(self, data: dict) -> dict:
        name = data["name"].strip()
        country_code = data["country_code"].strip().upper()
        alias = self._alias(name)

        campaign = await self.api.post(
            "campaigns",
            {
                "name": name,
                "alias": alias,
                "type": "position",
                "state": "active",
                "domain_id": data["domain_id"],
                "group_id": str(data["group_id"]),
                "traffic_source_id": data["traffic_source_id"],
            },
        )
        campaign_id = self._extract_id(campaign, "кампанию")
        created = {
            "campaign_id": campaign_id,
            "alias": alias,
            "google_flow_id": None,
            "offer_flow_id": None,
        }

        try:
            google_flow = await self.api.post(
                "streams",
                {
                    "campaign_id": campaign_id,
                    "name": f"Flow 1 — {country_code} → Google",
                    "type": "regular",
                    "schema": "redirect",
                    "position": 1,
                    "action_type": "http",
                    "action_payload": settings.google_redirect_url,
                    "filters": [
                        {
                            "name": "country",
                            "mode": "accept",
                            "payload": [country_code],
                        }
                    ],
                },
            )
            google_flow_id = self._extract_id(google_flow, "поток Google")
            created["google_flow_id"] = google_flow_id

            offer_flow = await self.api.post(
                "streams",
                {
                    "campaign_id": campaign_id,
                    "name": "Flow 2 — Default → Offer",
                    "type": "default",
                    "schema": "landings",
                    "position": 2,
                    "offers": [
                        {"offer_id": data["offer_id"], "share": 100, "state": "active"}
                    ],
                },
            )
            offer_flow_id = self._extract_id(offer_flow, "поток оффера")
            created["offer_flow_id"] = offer_flow_id

            streams = await self.get_campaign_streams(campaign_id)
            return {
                "campaign_id": campaign_id,
                "alias": alias,
                "name": name,
                "domain_id": data["domain_id"],
                "group_id": data["group_id"],
                "traffic_source_id": data["traffic_source_id"],
                "google_flow_id": google_flow_id,
                "offer_flow_id": offer_flow_id,
                "streams": streams,
            }
        except KeitaroError as exc:
            exc.details = {**created, "cause": exc.details}
            raise

    async def get_stream(self, stream_id: int) -> dict:
        data = await self.api.get(f"streams/{stream_id}")
        if not isinstance(data, dict):
            raise KeitaroError("Неожиданный ответ Keitaro при чтении потока", details=data)
        return data

    async def add_offer(self, campaign_id: int, stream_id: int, offer_id: int) -> dict:
        await self._assert_stream_belongs_to_campaign(campaign_id, stream_id)
        await self.api.get(f"offers/{offer_id}")
        stream = await self.get_stream(stream_id)
        current_offers = stream.get("offers") or []
        existing_ids = [
            int(item["offer_id"])
            for item in current_offers
            if isinstance(item, dict) and item.get("offer_id") is not None
        ]
        if offer_id in existing_ids:
            raise ValueError("Этот оффер уже добавлен в поток")

        new_ids = [*existing_ids, offer_id]
        shares = self._equal_shares(len(new_ids))
        updated_offers = [
            {"offer_id": item_id, "share": shares[index], "state": "active"}
            for index, item_id in enumerate(new_ids)
        ]
        await self.api.put(f"streams/{stream_id}", {"offers": updated_offers})
        return await self.get_stream(stream_id)

    async def remove_offer(self, campaign_id: int, stream_id: int, offer_id: int) -> dict:
        await self._assert_stream_belongs_to_campaign(campaign_id, stream_id)
        stream = await self.get_stream(stream_id)
        current_offers = stream.get("offers") or []
        existing_ids = [
            int(item["offer_id"])
            for item in current_offers
            if isinstance(item, dict) and item.get("offer_id") is not None
        ]
        remaining_ids = [item_id for item_id in existing_ids if item_id != offer_id]
        if len(remaining_ids) == len(existing_ids):
            raise ValueError("Оффер не найден в выбранном потоке")

        shares = self._equal_shares(len(remaining_ids))
        updated_offers = [
            {"offer_id": item_id, "share": shares[index], "state": "active"}
            for index, item_id in enumerate(remaining_ids)
        ]
        await self.api.put(f"streams/{stream_id}", {"offers": updated_offers})
        return await self.get_stream(stream_id)

    async def _assert_stream_belongs_to_campaign(self, campaign_id: int, stream_id: int) -> None:
        streams = await self.get_campaign_streams(campaign_id)
        if not any(int(stream.get("id", -1)) == stream_id for stream in streams):
            raise ValueError("Выбранный поток не принадлежит этой кампании")
