import unittest
from unittest.mock import Mock, patch

import main


class MainTests(unittest.TestCase):
    def test_main_delegates_to_queue_item_creation(self):
        with patch.object(
            main, "add_time_added_queue_item", return_value={"Id": 123}
        ) as add_item:
            result = main.main()

        self.assertEqual(result, {"Id": 123})
        add_item.assert_called_once_with()

    def test_add_time_added_queue_item_uses_exact_queue_payload(self):
        sdk = Mock()
        sdk.queues.create_item.return_value = {"Id": 123, "Status": "New"}

        with patch.object(main, "utc_now_text", return_value="2026-05-24T20:06:23Z"):
            result = main.add_time_added_queue_item(sdk=sdk)

        self.assertEqual(result, {"Id": 123, "Status": "New"})
        sdk.queues.create_item.assert_called_once_with(
            {"SpecificContent": {"TimeAdded": "2026-05-24T20:06:23Z"}},
            queue_name="Test_Queue",
            folder_path="Shared/UiPath",
        )

    def test_utc_now_text_is_utc_iso_zulu(self):
        value = main.utc_now_text()

        self.assertTrue(value.endswith("Z"))
        self.assertNotIn("+00:00", value)


if __name__ == "__main__":
    unittest.main()
