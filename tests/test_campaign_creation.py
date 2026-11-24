import unittest
from unittest.mock import AsyncMock

from app.services.campaign_service import CampaignService


class CampaignCreationTests(unittest.IsolatedAsyncioTestCase):
    async def test_creates_campaign_and_two_stand_compatible_flows(self):
        api = AsyncMock()
        api.post.side_effect = [
            {"id": 123, "name": "AU campaign"},
            {"id": 10, "name": "Flow 1"},
            {"id": 11, "name": "Flow 2"},
        ]
        api.get.return_value = [
            {"id": 10, "type": "regular"},
            {"id": 11, "type": "default"},
        ]

        service = CampaignService(api)
        result = await service.create_campaign({
            "name": "AU campaign",
            "country_code": "AU",
            "offer_id": 777,
            "domain_id": 1813,
            "group_id": 10332,
            "traffic_source_id": 836,
        })

        campaign_payload = api.post.call_args_list[0].args[1]
        google_payload = api.post.call_args_list[1].args[1]
        offer_payload = api.post.call_args_list[2].args[1]

        self.assertEqual(campaign_payload["domain_id"], 1813)
        self.assertEqual(campaign_payload["group_id"], "10332")
        self.assertEqual(campaign_payload["traffic_source_id"], 836)

        self.assertEqual(google_payload["campaign_id"], 123)
        self.assertEqual(google_payload["type"], "regular")
        self.assertEqual(google_payload["schema"], "redirect")
        self.assertEqual(google_payload["action_type"], "http")
        self.assertEqual(google_payload["action_payload"], "https://www.google.com")
        self.assertEqual(google_payload["filters"], [{
            "name": "country", "mode": "accept", "payload": ["AU"]
        }])

        self.assertEqual(offer_payload["campaign_id"], 123)
        self.assertEqual(offer_payload["type"], "default")
        self.assertEqual(offer_payload["schema"], "landings")
        self.assertEqual(offer_payload["offers"], [
            {"offer_id": 777, "share": 100, "state": "active"}
        ])

        # Only the final campaign-streams GET is needed; no unsupported
        # /stream_filters or /streams_actions requests are made.
        api.get.assert_awaited_once_with("campaigns/123/streams")
        self.assertEqual(result["campaign_id"], 123)
        self.assertEqual(result["google_flow_id"], 10)
        self.assertEqual(result["offer_flow_id"], 11)


if __name__ == "__main__":
    unittest.main()
