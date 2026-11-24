import unittest

from app.services.campaign_service import CampaignService


class ShareDistributionTests(unittest.TestCase):
    def test_one_offer_gets_all_traffic(self):
        self.assertEqual(CampaignService._equal_shares(1), [100])

    def test_two_offers_split_evenly(self):
        self.assertEqual(CampaignService._equal_shares(2), [50, 50])

    def test_three_offers_match_assignment_example(self):
        self.assertEqual(CampaignService._equal_shares(3), [33, 33, 34])

    def test_shares_always_sum_to_100(self):
        for count in range(1, 101):
            shares = CampaignService._equal_shares(count)
            self.assertEqual(len(shares), count)
            self.assertEqual(sum(shares), 100)

    def test_non_positive_count_returns_empty_list(self):
        self.assertEqual(CampaignService._equal_shares(0), [])
        self.assertEqual(CampaignService._equal_shares(-2), [])


if __name__ == "__main__":
    unittest.main()
