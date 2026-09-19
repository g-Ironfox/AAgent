import unittest

from event_catalog import event_catalog


class EventCatalogTest(unittest.TestCase):
    def test_catalog_contains_all_runtime_and_display_event_types(self):
        catalog = event_catalog()
        items = {item["event_type"]: item for item in catalog["items"]}

        self.assertEqual(
            set(items),
            {"qq", "terminal", "workflow", "response", "async_result", "raw"},
        )
        self.assertEqual(catalog["count"], 6)
        self.assertEqual(
            {item["event_type"] for item in catalog["items"] if item["scope"] == "main_queue"},
            {"qq", "terminal", "workflow", "response"},
        )

    def test_each_schema_identifies_its_event_type_and_payload(self):
        for item in event_catalog()["items"]:
            with self.subTest(event_type=item["event_type"]):
                schema = item["schema"]
                self.assertEqual(schema["properties"]["event_type"]["const"], item["event_type"])
                self.assertIn("event_type", schema["required"])
                self.assertIn("payload", schema["required"])
                self.assertEqual(schema["properties"]["payload"]["type"], "object")


if __name__ == "__main__":
    unittest.main()