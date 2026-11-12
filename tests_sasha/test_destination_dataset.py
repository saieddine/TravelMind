import unittest
from pathlib import Path


from data.dataset import load_demo_attractions, normalize_city, search_demo


class OfflineDatasetTests(unittest.TestCase):
    def test_city_alias(self):
        self.assertEqual(normalize_city("Xi'an"), "西安市")

    def test_seed_has_unique_ids(self):
        records = load_demo_attractions()
        self.assertEqual(len(records), len({x["attraction_id"] for x in records}))

    def test_history_ranking(self):
        places = search_demo("Xi'an", interests=["history"], limit=3)
        self.assertEqual(len(places), 3)
        self.assertTrue(all("history" in p["tags"] for p in places))

    def test_city_without_seed(self):
        self.assertEqual(search_demo("北京市"), [])

    def test_category_filter(self):
        places = search_demo("西安", category="museum")
        self.assertEqual(len(places), 2)
        self.assertTrue(all(p["category"] == "museum" for p in places))

    def test_unverified_fields_are_null(self):
        for item in load_demo_attractions():
            self.assertIsNone(item["opening_hours"])
            self.assertIsNone(item["ticket_price_cny"])
            self.assertEqual(item["verification_status"], "demo_unverified")


if __name__ == "__main__":
    unittest.main()
