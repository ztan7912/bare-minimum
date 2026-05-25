# UiPath Python Function Build Notes

## Acceptance Criteria

- Build a pure Python UiPath coded process/function that adds one item to queue `Test_Queue`.
- The queue item must contain exactly one custom field, `TimeAdded`, with the current UTC time.
- The published Orchestrator process must show as `Python (function)`, not `python-agent` or coded agent.
- Target Orchestrator tenant/folder: `https://staging.uipath.com/zheng/Customers`, folder `Shared/UiPath`.

## Discovery Log

- The workspace started effectively empty, aside from hidden Codex/git metadata.
- Local tools found:
  - `uip` CLI at `/mnt/c/Users/Zheng.Tan/AppData/Roaming/npm/uip`, version `1.0.4`.
  - `uipath` shell wrapper at `/home/zheng/bin/uipath`, which delegates to `npx uipath`; this is not the Python SDK CLI we want for a function-only project.
  - Python `3.12.3`.
- The global Python environment did not have the `uipath` package installed.
- Created a project virtualenv at `.venv`.
- Installed `uipath` Python SDK CLI version `2.10.70` into `.venv`.
- First install attempt failed in the sandbox because network/DNS access was blocked; reran with approved network access and completed successfully.
- Auth was completed with the Python SDK CLI using staging:
  - Command shape: `UIPATH_URL=https://staging.uipath.com/zheng/Customers .venv/bin/uipath auth --staging --force --tenant Customers`
  - Result: authentication successful.
  - Token and secret material are intentionally not recorded here.

## Key References

- UiPath Python SDK Getting Started: https://uipath.github.io/uipath-python/core/getting_started/
  - Uses a function-only `uipath.json` shape: `{"functions": {"main": "main.py:main"}}`.
  - `uipath init` generates `entry-points.json` and `bindings.json`.
  - `uipath pack` creates the `.nupkg`.
  - `uipath publish` publishes the package.
- UiPath Python SDK CLI Reference: https://uipath.github.io/uipath-python/cli/
  - Confirms `init`, `run`, `pack`, `publish`, and generated files.
- UiPath Queues SDK Reference: https://uipath.github.io/uipath-python/core/queues/
  - `QueuesService.create_item(item, queue_name=None, *, folder_key=None, folder_path=None)` creates a new queue item.
- UiPath Add Queue Item Activity Reference: https://docs.uipath.com/activities/other/latest/workflow/add-queue-item
  - Confirms Add Queue Item creates a `New` queue item and supports an Orchestrator folder path.
- UiPath Orchestrator Packages API Reference: https://docs.uipath.com/orchestrator/automation-cloud/latest/api-Guide/packages-requests
  - Confirms package version lookup with `GetProcessVersions(processId='<package>')`.
  - Confirms packages are represented through the Orchestrator `Processes` package endpoints.
- UiPath Orchestrator Processes API Reference: https://docs.uipath.com/orchestrator/standalone/2023.4/api-guide/processes-requests
  - Confirms process lookup through `Releases` and process-level update behavior.

## Process-Type Decision

- Do not use `uip codedagent`, `uip agent`, LangGraph, LlamaIndex, or OpenAI-agent packaging for this request.
- Use only the Python SDK CLI in `.venv/bin/uipath`.
- Keep `uipath.json` function-only:

```json
{
  "functions": {
    "main": "main.py:main"
  }
}
```

- Fail closed before publishing if generated metadata or package contents suggest agent packaging.
- Fail closed after publishing if Orchestrator metadata does not identify the package/process as `Python (function)`.

## Function Metadata Gates

Subagent `Jason` inspected the installed SDK source and found these concrete function-only markers:

- `uipath.json` must contain `functions` and must not contain `agents`.
- `entry-points.json` must have only entries with `"type": "function"`.
- `project.uiproj` must have `"ProjectType": "Function"`.
- The packed `.nupkg` must include `content/operate.json` with:
  - `"targetRuntime": "python"`
  - `"contentType": "function"`
- The `.nuspec` alone is insufficient because it does not carry the function-vs-agent marker.

Installed SDK source locations supporting those checks:

- `.venv/lib/python3.12/site-packages/uipath/_cli/models/uipath_json_schema.py`
- `.venv/lib/python3.12/site-packages/uipath/functions/factory.py`
- `.venv/lib/python3.12/site-packages/uipath/_cli/cli_init.py`
- `.venv/lib/python3.12/site-packages/uipath/_cli/cli_pack.py`
- `.venv/lib/python3.12/site-packages/uipath/_cli/_templates/package.nuspec.template`

Planned pre-publish gate:

```bash
.venv/bin/python scripts/verify_python_function_package.py
```

This will fail closed if the local project or latest `.uipath/*.nupkg` is missing function-only metadata.

Planned post-publish gate:

- Query the created/updated process in folder `Shared/UiPath`.
- Require Orchestrator `ProcessType` to equal `Function`.
- Treat a missing process binding as not done, because publishing may only upload the package to the tenant feed.

## Subagent Usage

- Spawned explorer subagent `Jason` to independently inspect installed SDK/package metadata and recommend concrete pre-publish/post-publish checks for the `Python (function)` acceptance criterion.
- Spawned explorer subagent `Poincare` to review the local project/package/deploy script before cloud deployment.
  - It confirmed function metadata and package contents were clean.
  - It recommended proving the queue item ID is new during smoke verification; `scripts/deploy_and_verify.py` now captures recent queue item IDs before the job and requires the verified item to be a new ID.
  - It raised a possible return-serialization concern based on the SDK reference. The installed SDK source for `QueuesService.create_item` returns `response.json()`, so the function returns a serializable object.

## Deployment Result

- Preflight against staging resolved folder `Shared/UiPath`:
  - Folder Id: `1088798`
  - Folder Key: `293debe4-40d3-4015-afbf-0fd1f39a4d50`
- No folder-specific process package feed existed for `Shared/UiPath`; package upload used the tenant process feed:
  - `Orchestrator Tenant Processes Feed`
- `Test_Queue` did not exist in `Shared/UiPath`, so a new queue was created in that folder without editing/sharing/overwriting the existing `Test_Queue` found elsewhere in the tenant:
  - Queue Key: `f4d63ea1-6e9e-44d4-b921-604c11b5ec25`
- Initial deployment used the timestamped package name `BareMinimumQueueTimeAdded20260524T200623Z`.
- The package/project name was later simplified to `BareMinimumQueueTimeAdded` in:
  - `pyproject.toml`
  - `project.uiproj`
- Repacked package:
  - Package name: `BareMinimumQueueTimeAdded`
  - Version: `0.1.0`
  - Package file: `.uipath/BareMinimumQueueTimeAdded.0.1.0.nupkg`
- Local package gate passed:
  - `content/operate.json` has `"targetRuntime": "python"`
  - `content/operate.json` has `"contentType": "function"`
- Deployment helper discovery:
  - `EditRelease` exists but Orchestrator rejects changing a release's package identity with HTTP 400: `'ProcessKey' is not editable.`
  - To truly change the package key from the long name to the clean name, the old process binding had to be deleted and recreated against the new package.
  - Package deletion uses the package-version endpoint shape `DELETE /odata/Processes('<package>:<version>')`, after verifying the old package is inactive.
- Final deployed process in `Shared/UiPath`:
  - Process name: `BareMinimumQueueTimeAdded`
  - Process package key: `BareMinimumQueueTimeAdded`
  - Process key: `f9eb0217-32b3-426a-a5c9-a188111dc0b7`
  - Verified Orchestrator `ProcessType`: `Function`
- Old package cleanup:
  - Deleted old process binding: `fff965de-2fa0-43a8-8b77-641f71828714`
  - Verified old package `BareMinimumQueueTimeAdded20260524T200623Z` version `0.1.0` was inactive.
  - Deleted old package `BareMinimumQueueTimeAdded20260524T200623Z` version `0.1.0`.
- Final smoke test:
  - Started job: `0870c412-063b-4bd2-99a1-5354c87197c4`
  - Final job state: `Successful`
  - Verified new queue item: `19927118`
  - Verified `SpecificContent` had exactly one key, `TimeAdded`
  - `TimeAdded`: `2026-05-24T20:51:21.572453Z`
- Deployment summary written to `.uipath/deploy-result.json`.

## Production Cloud Training Deployment

- Target tenant URL: `https://cloud.uipath.com/ZhengTanTraining/ZhengTanTraining`
- Auth was switched from staging to the production Cloud tenant with the Python SDK CLI.
- Target folder `Shared/UiPath` did not exist, so it was created under existing folder `Shared`:
  - Folder Id: `554641`
  - Folder Key: `be0ecdbb-c189-4355-8fa4-9a74b73eef01`
- Created queue `Test_Queue` in `Shared/UiPath`:
  - Queue Key: `eb3a6d76-cd5f-4c96-9731-249227107126`
- No existing package version `BareMinimumQueueTimeAdded` `0.1.0` was found before upload.
- No existing process named `BareMinimumQueueTimeAdded` was found before creation.
- Uploaded package:
  - Package name: `BareMinimumQueueTimeAdded`
  - Version: `0.1.0`
  - Package file: `.uipath/BareMinimumQueueTimeAdded.0.1.0.nupkg`
- Created process:
  - Process name: `BareMinimumQueueTimeAdded`
  - Process key: `653194d6-95a2-4965-b540-aa461f1378f5`
  - Verified Orchestrator `ProcessType`: `Function`
- Smoke test:
  - Started job: `f2599d3a-d25c-4839-aa39-77429bcf0aca`
  - Final job state: `Successful`
  - Verified new queue item: `67007139`
  - Verified `SpecificContent` had exactly one key, `TimeAdded`
  - `TimeAdded`: `2026-05-24T21:50:27.779032Z`
- Deployment summary written to `.uipath/deploy-result-training.json`.

## Studio Web Sync

- Added `UIPATH_PROJECT_ID=5e1e4253-8495-4d9b-ac47-41b773a0e886` to `.env`.
- Confirmed the SDK push file set before syncing:
  - `bindings.json`
  - `entry-points.json`
  - `main.py`
  - `pyproject.toml`
  - `uipath.json`
- Ran `.venv/bin/uipath push --nolock` without `--overwrite`.
- Push result:
  - Uploaded `bindings.json`
  - Uploaded `entry-points.json`
  - Uploaded `main.py`
  - Updated `pyproject.toml`
  - Uploaded `uipath.json`
  - Uploaded `.uipath/studio_metadata.json`
- Resource import summary was `0 total resources`, because `bindings.json` contains no referenced resources.
- After simplifying the package name, ran `.venv/bin/uipath push --nolock` again.
  - Updated `entry-points.json`.
  - Updated `pyproject.toml`.
  - Updated `.uipath/studio_metadata.json`.
  - Resource import summary remained `0 total resources`.
