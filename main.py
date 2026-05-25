from datetime import datetime, timezone
from typing import Any

from uipath.platform import UiPath


QUEUE_NAME = "Test_Queue"
FOLDER_PATH = "Shared/UiPath"


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def as_queue_item_data(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    json_method = getattr(value, "json", None)
    if callable(json_method):
        data = json_method()
        if isinstance(data, dict):
            return data
    raise TypeError(f"queue create_item returned unsupported value: {type(value).__name__}")


def add_time_added_queue_item(sdk: UiPath | None = None) -> dict[str, Any]:
    client = sdk or UiPath()
    time_added = utc_now_text()
    return as_queue_item_data(
        client.queues.create_item(
            {"SpecificContent": {"TimeAdded": time_added}},
            queue_name=QUEUE_NAME,
            folder_path=FOLDER_PATH,
        )
    )


def main() -> dict[str, Any]:
    return add_time_added_queue_item()
