import argparse
import json
import os
import pathlib
import sys
import time
import tomllib
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx
from dotenv import load_dotenv


FOLDER_PATH = "Shared/UiPath"
QUEUE_NAME = "Test_Queue"
ENTRY_POINT_PATH = "main"
STATE_PATH = pathlib.Path(".uipath/deploy-result.json")


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def odata_quote(value: str) -> str:
    return value.replace("'", "''")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_uipath_time(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_project() -> tuple[str, str]:
    with open("pyproject.toml", "rb") as handle:
        project = tomllib.load(handle)["project"]
    return project["name"], project["version"]


class Orchestrator:
    def __init__(self) -> None:
        load_dotenv(override=True)
        self.base_url = os.environ.get("UIPATH_URL", "").rstrip("/")
        token = os.environ.get("UIPATH_ACCESS_TOKEN")
        if not self.base_url or not token:
            fail("UIPATH_URL and UIPATH_ACCESS_TOKEN must be present in .env")
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=120,
        )

    def close(self) -> None:
        self.client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        files: dict[str, Any] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> Any:
        response = self.client.request(
            method,
            path,
            params=params,
            json=json_body,
            headers=headers,
            files=files,
        )
        if allowed_statuses and response.status_code in allowed_statuses:
            return {"_status": response.status_code, "_body": response.text}
        if response.status_code >= 400:
            body = response.text[:1200]
            fail(f"{method} {path} returned HTTP {response.status_code}: {body}")
        if not response.content:
            return {}
        return response.json()

    def folder_headers(self, folder_id: int | None = None) -> dict[str, str]:
        if folder_id is not None:
            return {"X-UIPATH-OrganizationUnitId": str(folder_id)}
        return {"X-UIPATH-FolderPath": FOLDER_PATH}

    def resolve_folder(self) -> dict[str, Any]:
        folder = self.find_folder(FOLDER_PATH)
        if folder is None:
            fail(f"folder not found: {FOLDER_PATH}")
        print(
            f"OK: resolved folder {folder.get('FullyQualifiedName')} "
            f"(Id={folder.get('Id')}, Key={folder.get('Key')})"
        )
        return folder

    def find_folder(self, folder_path: str) -> dict[str, Any] | None:
        result = self.request(
            "GET",
            "/orchestrator_/odata/Folders",
            params={
                "$filter": f"FullyQualifiedName eq '{odata_quote(folder_path)}'",
                "$top": 1,
            },
        )
        folders = result.get("value", [])
        if not folders:
            return None
        return folders[0]

    def create_child_folder(
        self, parent_folder_path: str, child_folder_name: str
    ) -> dict[str, Any]:
        parent = self.find_folder(parent_folder_path)
        if parent is None:
            fail(f"parent folder not found: {parent_folder_path}")
        folder = self.request(
            "POST",
            "/orchestrator_/odata/Folders",
            json_body={
                "DisplayName": child_folder_name,
                "Description": "Created for bare minimum Python function deployment.",
                "FolderType": "Standard",
                "ProvisionType": "Automatic",
                "PermissionModel": parent.get("PermissionModel") or "FineGrained",
                "ParentId": parent["Id"],
                "FeedType": parent.get("FeedType") or "Processes",
            },
            headers={
                "Content-Type": "application/json;odata.metadata=minimal;odata.streaming=true",
            },
        )
        print(
            f"OK: created folder {folder.get('FullyQualifiedName')} "
            f"(Id={folder.get('Id')}, Key={folder.get('Key')})"
        )
        return folder

    def ensure_folder(
        self, folder_path: str, create_missing: bool, preflight_only: bool
    ) -> dict[str, Any] | None:
        folder = self.find_folder(folder_path)
        if folder is not None:
            print(
                f"OK: resolved folder {folder.get('FullyQualifiedName')} "
                f"(Id={folder.get('Id')}, Key={folder.get('Key')})"
            )
            return folder
        if not create_missing:
            fail(f"folder not found: {folder_path}")
        parent_path, _, child_name = folder_path.rpartition("/")
        if not parent_path or not child_name:
            fail(f"cannot auto-create folder path: {folder_path}")
        if preflight_only:
            parent = self.find_folder(parent_path)
            if parent is None:
                fail(f"parent folder not found: {parent_path}")
            print(f"OK: folder {folder_path} is missing and would be created")
            return None
        return self.create_child_folder(parent_path, child_name)

    def find_process_feed(self, folder: dict[str, Any]) -> tuple[str | None, str]:
        feeds = self.request("GET", "/orchestrator_/api/PackageFeeds/GetFeeds")
        process_feeds = [
            feed for feed in feeds if feed.get("purpose") == "Processes"
        ]
        folder_path = str(folder.get("FullyQualifiedName") or FOLDER_PATH)
        display_name = str(folder.get("DisplayName") or folder_path.split("/")[-1])

        def core(feed_name: str) -> str:
            lowered = feed_name.lower()
            if lowered.startswith("orchestrator "):
                lowered = lowered[len("orchestrator ") :]
            if lowered.endswith(" feed"):
                lowered = lowered[: -len(" feed")]
            return lowered

        candidates = []
        wanted = {folder_path.lower(), display_name.lower()}
        for feed in process_feeds:
            name = str(feed.get("name", ""))
            if name.lower() in wanted or core(name) in wanted:
                candidates.append(feed)

        if len(candidates) == 0:
            tenant_feeds = [
                feed
                for feed in process_feeds
                if str(feed.get("name", "")).lower() == "orchestrator tenant processes feed"
            ]
            if len(tenant_feeds) == 1:
                feed = tenant_feeds[0]
                print(
                    "OK: no folder-specific process feed found; using tenant "
                    f"process feed {feed.get('name')}"
                )
                return None, str(feed["name"])

        if len(candidates) != 1:
            names = ", ".join(feed.get("name", "") for feed in process_feeds)
            fail(
                "could not uniquely resolve the process package feed for "
                f"{folder_path}. Candidate count={len(candidates)}. Feeds: {names}"
            )

        feed = candidates[0]
        print(f"OK: resolved process feed {feed.get('name')} ({feed.get('id')})")
        return str(feed["id"]), str(feed["name"])

    def find_queue(self, folder_id: int) -> dict[str, Any] | None:
        result = self.request(
            "GET",
            "/orchestrator_/odata/QueueDefinitions/UiPath.Server.Configuration.OData.ListQueues",
            params={
                "$filter": f"QueueDefinitionName eq '{odata_quote(QUEUE_NAME)}'",
                "$top": 2,
            },
            headers=self.folder_headers(folder_id),
        )
        queues = result.get("value", [])
        if not queues:
            return None
        if len(queues) != 1:
            fail(f"expected at most one queue named {QUEUE_NAME}; found {len(queues)}")
        queue = queues[0]
        print(
            f"OK: found queue {queue.get('QueueDefinitionName')} "
            f"({queue.get('QueueDefinitionKey')})"
        )
        return queue

    def create_queue(self, folder_id: int) -> dict[str, Any]:
        queue = self.request(
            "POST",
            "/orchestrator_/odata/QueueDefinitions/UiPath.Server.Configuration.OData.CreateQueue",
            json_body={
                "Name": QUEUE_NAME,
                "Description": "Queue created for bare minimum Python function smoke test.",
                "MaxNumberOfRetries": 0,
                "AcceptAutomaticallyRetry": False,
                "RetryAbandonedItems": False,
                "EnforceUniqueReference": False,
                "Encrypted": False,
                "RetentionAction": "Delete",
                "RetentionPeriod": 30,
                "StaleRetentionAction": "Delete",
                "StaleRetentionPeriod": 180,
            },
            headers={
                **self.folder_headers(folder_id),
                "Content-Type": "application/json;odata.metadata=minimal;odata.streaming=true",
            },
        )
        print(f"OK: created queue {queue.get('Name')} ({queue.get('Key')})")
        return queue

    def assert_no_existing_package(
        self, package_name: str, package_version: str, feed_id: str | None
    ) -> None:
        versions = self.get_package_versions(package_name, feed_id)
        matching = [
            item
            for item in versions
            if item.get("Id") == package_name and item.get("Version") == package_version
        ]
        if matching:
            fail(f"package already exists in target feed: {package_name} {package_version}")
        print(f"OK: no existing package version {package_name} {package_version}")

    def get_package_versions(
        self, package_name: str, feed_id: str | None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"$top": 100}
        if feed_id:
            params["feedId"] = feed_id
        result = self.request(
            "GET",
            (
                "/orchestrator_/odata/Processes/"
                f"UiPath.Server.Configuration.OData.GetProcessVersions(processId='{package_name}')"
            ),
            params=params,
            allowed_statuses={404},
        )
        if result.get("_status") == 404:
            print(f"OK: package {package_name} does not exist in target feed")
            return []
        return result.get("value", [])

    def package_version_exists(
        self, package_name: str, package_version: str, feed_id: str | None
    ) -> bool:
        versions = self.get_package_versions(package_name, feed_id)
        return any(
            item.get("Id") == package_name and item.get("Version") == package_version
            for item in versions
        )

    def assert_no_existing_process(self, process_name: str, folder_id: int) -> None:
        result = self.list_processes(process_name, folder_id)
        if result:
            fail(f"process already exists in target folder: {process_name}")
        print(f"OK: no existing process named {process_name}")

    def list_processes(self, process_name: str, folder_id: int) -> list[dict[str, Any]]:
        result = self.request(
            "GET",
            "/orchestrator_/odata/Releases/UiPath.Server.Configuration.OData.ListReleases",
            params={
                "$filter": f"Name eq '{odata_quote(process_name)}'",
                "$top": 10,
            },
            headers=self.folder_headers(folder_id),
        )
        return result.get("value", [])

    def list_processes_by_package_key(
        self, package_name: str, folder_id: int
    ) -> list[dict[str, Any]]:
        result = self.request(
            "GET",
            "/orchestrator_/odata/Releases/UiPath.Server.Configuration.OData.ListReleases",
            params={
                "$filter": f"ProcessKey eq '{odata_quote(package_name)}'",
                "$top": 100,
            },
            headers=self.folder_headers(folder_id),
        )
        return result.get("value", [])

    def upload_package(self, package_path: pathlib.Path, feed_id: str | None) -> None:
        params = {"feedId": feed_id} if feed_id else None
        with package_path.open("rb") as handle:
            self.request(
                "POST",
                "/orchestrator_/odata/Processes/UiPath.Server.Configuration.OData.UploadPackage()",
                params=params,
                files={"file": (package_path.name, handle, "application/octet-stream")},
            )
        print(f"OK: uploaded package {package_path.name}")

    def create_process(
        self,
        package_name: str,
        package_version: str,
        feed_id: str | None,
        folder_id: int,
    ) -> dict[str, Any]:
        body = {
            "Name": package_name,
            "ProcessKey": package_name,
            "ProcessVersion": package_version,
            "Description": "Bare minimum Python function that adds TimeAdded to Test_Queue.",
            "EntryPointPath": ENTRY_POINT_PATH,
            "AutoUpdate": False,
            "RetentionPeriod": 30,
            "RetentionAction": "Delete",
        }
        if feed_id:
            body["FeedId"] = feed_id
        process = self.request(
            "POST",
            "/orchestrator_/odata/Releases/UiPath.Server.Configuration.OData.CreateRelease",
            json_body=body,
            headers={
                **self.folder_headers(folder_id),
                "Content-Type": "application/json;odata.metadata=minimal;odata.streaming=true",
            },
        )
        print(
            f"OK: created process {process.get('Name')} "
            f"(Key={process.get('Key')}, ProcessType={process.get('ProcessType')})"
        )
        return process

    def edit_process_package(
        self,
        release: dict[str, Any],
        process_name: str,
        package_name: str,
        package_version: str,
        folder_id: int,
    ) -> dict[str, Any]:
        feed_id = release.get("FeedId")
        body: dict[str, Any] = {
            "Id": release["Id"],
            "Key": release["Key"],
            "Name": process_name,
            "ProcessKey": package_name,
            "ProcessVersion": package_version,
            "Description": (
                release.get("Description")
                or "Bare minimum Python function that adds TimeAdded to Test_Queue."
            ),
            "EntryPointPath": ENTRY_POINT_PATH,
            "AutoUpdate": bool(release.get("AutoUpdate", False)),
            "HiddenForAttendedUser": bool(release.get("HiddenForAttendedUser", False)),
            "EnvironmentVariables": release.get("EnvironmentVariables") or "",
            "RetentionAction": release.get("RetentionAction") or "Delete",
            "RetentionPeriod": int(release.get("RetentionPeriod") or 30),
            "StaleRetentionAction": release.get("StaleRetentionAction") or "Delete",
            "StaleRetentionPeriod": int(release.get("StaleRetentionPeriod") or 180),
            "JobPriority": release.get("JobPriority") or "Normal",
            "AutoCreateConnectedTriggers": bool(
                release.get("AutoCreateConnectedTriggers", True)
            ),
            "RemoteControlAccess": release.get("RemoteControlAccess") or "None",
        }
        if feed_id:
            body["FeedId"] = feed_id
        if release.get("SpecificPriorityValue") is not None:
            body["SpecificPriorityValue"] = release["SpecificPriorityValue"]
        if release.get("RobotSize") is not None:
            body["RobotSize"] = release["RobotSize"]

        process = self.request(
            "POST",
            "/orchestrator_/odata/Releases/UiPath.Server.Configuration.OData.EditRelease",
            json_body=body,
            headers={
                **self.folder_headers(folder_id),
                "Content-Type": "application/json;odata.metadata=minimal;odata.streaming=true",
            },
        )
        print(
            f"OK: edited process {process.get('Name')} to package "
            f"{process.get('ProcessKey')} {process.get('ProcessVersion')}"
        )
        return process

    def delete_process(self, release: dict[str, Any], folder_id: int) -> None:
        self.request(
            "DELETE",
            f"/orchestrator_/odata/Releases({release['Id']})",
            headers=self.folder_headers(folder_id),
        )
        print(
            f"OK: deleted process binding {release.get('Name')} "
            f"(Id={release.get('Id')}, Key={release.get('Key')})"
        )

    def verify_process_type(
        self,
        process_name: str,
        package_version: str,
        folder_id: int,
        package_name: str | None = None,
    ) -> dict[str, Any]:
        matches = self.list_processes(process_name, folder_id)
        matches = [
            item
            for item in matches
            if item.get("Name") == process_name
            and item.get("ProcessVersion") == package_version
            and (package_name is None or item.get("ProcessKey") == package_name)
        ]
        if len(matches) != 1:
            fail(
                f"expected one process {process_name} {package_version}; "
                f"found {len(matches)}"
            )
        process = matches[0]
        if process.get("ProcessType") != "Function":
            fail(f"process type is {process.get('ProcessType')!r}, expected 'Function'")
        print("OK: Orchestrator ProcessType is Function")
        return process

    def delete_package_version(
        self, package_name: str, package_version: str, feed_id: str | None
    ) -> None:
        params = {"feedId": feed_id} if feed_id else None
        package_key = quote(f"{package_name}:{package_version}", safe="")
        self.request(
            "DELETE",
            f"/orchestrator_/odata/Processes('{package_key}')",
            params=params,
        )
        print(f"OK: deleted package {package_name} {package_version}")

    def assert_package_version_inactive(
        self, package_name: str, package_version: str, feed_id: str | None
    ) -> None:
        versions = self.get_package_versions(package_name, feed_id)
        matching = [
            item
            for item in versions
            if item.get("Id") == package_name and item.get("Version") == package_version
        ]
        if not matching:
            print(f"OK: package {package_name} {package_version} is already absent")
            return
        active = [item for item in matching if item.get("IsActive")]
        if active:
            fail(f"package {package_name} {package_version} is still active")
        print(f"OK: package {package_name} {package_version} is inactive")

    def start_job(self, release_key: str, folder_id: int) -> dict[str, Any]:
        result = self.request(
            "POST",
            "/orchestrator_/odata/Jobs/UiPath.Server.Configuration.OData.StartJobs",
            json_body={
                "startInfo": {
                    "ReleaseKey": release_key,
                    "Strategy": "ModernJobsCount",
                    "JobsCount": 1,
                    "InputArguments": "{}",
                    "Source": "Manual",
                }
            },
            headers={
                **self.folder_headers(folder_id),
                "Content-Type": "application/json;odata.metadata=minimal;odata.streaming=true",
            },
        )
        jobs = result.get("value", [])
        if not jobs:
            fail("StartJobs did not return a job")
        job = jobs[0]
        print(f"OK: started job {job.get('Key')} initial state={job.get('State')}")
        return job

    def get_job(self, job_key: str, folder_id: int) -> dict[str, Any]:
        return self.request(
            "GET",
            f"/orchestrator_/odata/Jobs/UiPath.Server.Configuration.OData.GetByKey(identifier={job_key})",
            headers=self.folder_headers(folder_id),
        )

    def wait_for_job(self, job_key: str, folder_id: int, timeout_seconds: int) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        last_job: dict[str, Any] = {}
        while time.time() < deadline:
            last_job = self.get_job(job_key, folder_id)
            state = last_job.get("State")
            if state in {"Successful", "Faulted", "Stopped"}:
                if state != "Successful":
                    fail(f"job ended with state {state}: {last_job.get('Info')}")
                print(f"OK: job completed successfully ({job_key})")
                return last_job
            time.sleep(5)
        fail(f"job did not complete within {timeout_seconds}s; last state={last_job.get('State')}")

    def recent_queue_item_ids(self, folder_id: int) -> set[int]:
        result = self.request(
            "GET",
            "/orchestrator_/odata/QueueItems",
            params={
                "$filter": f"QueueDefinition/Name eq '{odata_quote(QUEUE_NAME)}'",
                "$orderby": "Id desc",
                "$top": 100,
                "$expand": "QueueDefinition",
            },
            headers=self.folder_headers(folder_id),
        )
        return {
            int(item["Id"])
            for item in result.get("value", [])
            if item.get("Id") is not None
        }

    def verify_queue_item(
        self, started_at: datetime, folder_id: int, before_ids: set[int]
    ) -> dict[str, Any]:
        result = self.request(
            "GET",
            "/orchestrator_/odata/QueueItems",
            params={
                "$filter": f"QueueDefinition/Name eq '{odata_quote(QUEUE_NAME)}'",
                "$orderby": "Id desc",
                "$top": 25,
                "$expand": "QueueDefinition",
            },
            headers=self.folder_headers(folder_id),
        )
        inspected = []
        for item in result.get("value", []):
            specific_content = item.get("SpecificContent") or {}
            if isinstance(specific_content, str):
                try:
                    specific_content = json.loads(specific_content)
                except json.JSONDecodeError:
                    specific_content = {}
            time_added = specific_content.get("TimeAdded")
            item_id = item.get("Id")
            inspected.append((item_id, item.get("Status"), time_added))
            parsed = parse_uipath_time(time_added)
            if parsed and parsed >= started_at and item_id not in before_ids:
                if set(specific_content.keys()) != {"TimeAdded"}:
                    fail(
                        "new queue item custom content had unexpected fields: "
                        f"{sorted(specific_content.keys())}"
                    )
                print(
                    f"OK: verified queue item Id={item.get('Id')} "
                    f"Status={item.get('Status')} TimeAdded={time_added}"
                )
                return item
        fail(f"could not find a new queue item with TimeAdded after job start. Inspected: {inspected}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True, type=pathlib.Path)
    parser.add_argument("--create-missing-queue", action="store_true")
    parser.add_argument("--create-missing-folder", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--state-path", default=str(STATE_PATH), type=pathlib.Path)
    parser.add_argument("--update-existing-process", action="store_true")
    parser.add_argument("--delete-old-package", action="store_true")
    parser.add_argument("--replace-process-on-package-rename", action="store_true")
    parser.add_argument("--old-package-name")
    args = parser.parse_args()

    package_name, package_version = read_project()
    if not args.package.exists():
        fail(f"package not found: {args.package}")
    if args.delete_old_package and not args.old_package_name:
        fail("--old-package-name is required with --delete-old-package")

    orchestrator = Orchestrator()
    try:
        folder = orchestrator.ensure_folder(
            FOLDER_PATH, args.create_missing_folder, args.preflight_only
        )
        if folder is None:
            print("OK: deployment preflight stopped before folder creation")
            return
        folder_id = int(folder["Id"])
        feed_id, feed_name = orchestrator.find_process_feed(folder)
        queue = orchestrator.find_queue(folder_id)
        if queue is None:
            if not args.create_missing_queue:
                fail(
                    f"queue {QUEUE_NAME} does not exist in {FOLDER_PATH}; "
                    "rerun with --create-missing-queue to create it"
                )
            if args.preflight_only:
                print(f"OK: queue {QUEUE_NAME} is missing and would be created")
            else:
                orchestrator.create_queue(folder_id)
                orchestrator.find_queue(folder_id)
        process_name = package_name
        if args.update_existing_process:
            matches = orchestrator.list_processes(process_name, folder_id)
            if len(matches) != 1:
                fail(f"expected one existing process named {process_name}; found {len(matches)}")
            current_process = matches[0]
            if current_process.get("ProcessType") != "Function":
                fail(
                    f"existing process type is {current_process.get('ProcessType')!r}, "
                    "expected 'Function'"
                )
            expected_package_keys = {package_name}
            if args.old_package_name:
                expected_package_keys.add(args.old_package_name)
            if current_process.get("ProcessKey") not in expected_package_keys:
                fail(
                    "existing process is not attached to the expected package. "
                    f"ProcessKey={current_process.get('ProcessKey')!r}"
                )
            if not orchestrator.package_version_exists(package_name, package_version, feed_id):
                print(f"OK: new package version {package_name} {package_version} is not present yet")
            else:
                print(f"OK: new package version {package_name} {package_version} already exists")
        else:
            orchestrator.assert_no_existing_package(package_name, package_version, feed_id)
            orchestrator.assert_no_existing_process(process_name, folder_id)

        if args.preflight_only:
            print("OK: staging preflight passed; no package or process was created")
            return

        if args.update_existing_process:
            if not orchestrator.package_version_exists(package_name, package_version, feed_id):
                orchestrator.upload_package(args.package, feed_id)
            else:
                print("OK: upload skipped because package version already exists")

            process = orchestrator.verify_process_type(
                process_name,
                current_process["ProcessVersion"],
                folder_id,
                current_process["ProcessKey"],
            )
            if (
                process.get("ProcessKey") != package_name
                or process.get("ProcessVersion") != package_version
            ):
                if process.get("ProcessKey") != package_name:
                    if not args.replace_process_on_package_rename:
                        fail(
                            "Orchestrator does not allow editing ProcessKey in place; "
                            "rerun with --replace-process-on-package-rename to delete "
                            "and recreate this process binding against the clean package"
                        )
                    orchestrator.delete_process(process, folder_id)
                    orchestrator.create_process(
                        package_name, package_version, feed_id, folder_id
                    )
                else:
                    orchestrator.edit_process_package(
                        process,
                        process_name,
                        package_name,
                        package_version,
                        folder_id,
                    )
            else:
                print("OK: existing process already targets the clean package")
            process = orchestrator.verify_process_type(
                process_name, package_version, folder_id, package_name
            )
        else:
            orchestrator.upload_package(args.package, feed_id)
            orchestrator.create_process(package_name, package_version, feed_id, folder_id)
            process = orchestrator.verify_process_type(
                process_name, package_version, folder_id, package_name
            )

        before_ids = orchestrator.recent_queue_item_ids(folder_id)
        started_at = utc_now()
        job = orchestrator.start_job(process["Key"], folder_id)
        final_job = orchestrator.wait_for_job(job["Key"], folder_id, args.timeout)
        queue_item = orchestrator.verify_queue_item(started_at, folder_id, before_ids)

        old_package_deleted = False
        if args.delete_old_package:
            old_releases = orchestrator.list_processes_by_package_key(
                args.old_package_name, folder_id
            )
            if old_releases:
                details = [
                    f"{item.get('Name')} ({item.get('Key')})"
                    for item in old_releases
                ]
                fail(
                    f"old package is still referenced by process(es): {details}"
                )
            orchestrator.assert_package_version_inactive(
                args.old_package_name, package_version, feed_id
            )
            if orchestrator.package_version_exists(
                args.old_package_name, package_version, feed_id
            ):
                orchestrator.delete_package_version(
                    args.old_package_name, package_version, feed_id
                )
                old_package_deleted = True
            if orchestrator.package_version_exists(
                args.old_package_name, package_version, feed_id
            ):
                fail(f"old package still exists after delete: {args.old_package_name}")
            print(f"OK: old package {args.old_package_name} is absent")

        args.state_path.parent.mkdir(exist_ok=True)
        args.state_path.write_text(
            json.dumps(
                {
                    "targetUrl": orchestrator.base_url,
                    "packageName": package_name,
                    "packageVersion": package_version,
                    "folderPath": FOLDER_PATH,
                    "feedId": feed_id,
                    "feedName": feed_name,
                    "processName": process.get("Name"),
                    "processPackageKey": process.get("ProcessKey"),
                    "processKey": process.get("Key"),
                    "processType": process.get("ProcessType"),
                    "jobKey": final_job.get("Key"),
                    "jobState": final_job.get("State"),
                    "queueItemId": queue_item.get("Id"),
                    "timeAdded": (
                        (queue_item.get("SpecificContent") or {}).get("TimeAdded")
                        if isinstance(queue_item.get("SpecificContent"), dict)
                        else None
                    ),
                    "oldPackageName": args.old_package_name,
                    "oldPackageDeleted": old_package_deleted,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"OK: wrote deployment summary to {args.state_path}")
    finally:
        orchestrator.close()


if __name__ == "__main__":
    main()
