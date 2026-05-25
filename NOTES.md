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

## External App Access Model

- The GitHub Actions deployment should use a confidential UiPath External Application, with `UIPATH_SCOPE=OR.Default` requested at token time.
- Package upload is tenant-scoped in the UiPath CLI/Orchestrator model, so package publishing should be covered by a small tenant role.
- Process creation/update, queues, queue items, and jobs are folder-scoped for this project and should be covered by a folder role assigned only on `Shared/UiPath`.
- Suggested tenant role, for example `Python Function Package Publisher`:
  - `Packages.View`
  - `Packages.Create`
  - `Folders.View`
- Suggested folder role, for example `Python Function Deployer`, assigned on `Shared/UiPath`:
  - `Processes.View`
  - `Processes.Create`
  - `Processes.Edit`
  - `Queues.View`
  - `Queues.Create`
  - `Transactions.View`
  - `Transactions.Create`
  - `Jobs.View`
  - `Jobs.Create`
- If the deployment helper should create missing folders, add the relevant folder administration permissions at the tenant level. The GitHub Actions workflow currently assumes `Shared/UiPath` already exists.
- The `uip or roles` CLI can create/edit roles. Assignment to the external app can always be done in Orchestrator UI; CLI assignment is possible if the external app appears as an assignable user/principal key in the tenant.

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

## Git Workspace Notes

- This workspace lives under the Windows filesystem at `/mnt/c/Users/Zheng.Tan/Documents/Product/Python functions/bare-minimum`.
- The Codex/WSL session initially exposed `.git` as a read-only sandbox mount, so Linux Git could not initialize or write repository metadata in place.
- A sanitized temporary repo was used first to push the initial GitHub history to `https://github.com/ztan7912/bare-minimum.git`.
- The underlying Windows folder was then initialized with Windows Git:
  - Windows Git executable: `C:\Program Files\Git\cmd\git.exe`
  - Remote: `https://github.com/ztan7912/bare-minimum.git`
  - Branch: `main`
- Current practical guidance:
  - For this template and expected customer environments, keep the repo on Windows and use Windows Git/Windows VS Code.
  - If WSL-native Git ownership is needed, clone the repo into the WSL filesystem, such as `~/projects/bare-minimum`.
  - Avoid relying on WSL Git write operations against this exact `/mnt/c` worktree if the environment remounts `.git` read-only.

## Project Review - 2026-05-25

Review scope:
- Runtime function, package metadata, GitHub Actions workflow, deployment helper, tests, and documentation.
- Local verification passed:
  - `.venv/bin/python -m unittest discover -s tests`
  - `.venv/bin/python scripts/verify_python_function_package.py`
  - `.venv/bin/python -m py_compile main.py scripts/deploy_and_verify.py scripts/verify_python_function_package.py tests/test_main.py`

### Findings To Fix

1. **High - CI can pass without deploying changed code**
   - `pyproject.toml` is fixed at version `0.1.0`.
   - `.github/workflows/deploy-uipath.yml` deploys `.uipath/BareMinimumQueueTimeAdded.0.1.0.nupkg`.
   - `scripts/deploy_and_verify.py` skips upload when that package version already exists.
   - Risk: a future code change without a version bump can build in Actions, skip upload, smoke-test the old deployed artifact, and still show a successful workflow.
   - Suggested fixes:
     - Enforce a version bump before deploy.
     - Or derive a unique CI package version from run number/commit.
     - Or fail if the target package version already exists unless an explicit `--allow-existing-package` flag is used.

2. **Medium - README badge represents a manual deploy, not latest commit CI**
   - The workflow only has `workflow_dispatch`.
   - The badge can show the last successful manual deployment even when newer commits have not been tested or deployed.
   - Suggested fix: add a separate `ci.yml` for `push` and `pull_request` that runs package verification and unit tests. Keep deployment manual.

3. **Medium - Smoke verification lacks a unique run correlation**
   - The deploy helper finds a queue item by checking recent IDs plus `TimeAdded >= started_at`.
   - Concurrent workflow runs, clock skew, or unrelated use of `Test_Queue` could make this flaky or falsely pass.
   - Suggested fixes:
     - Add workflow `concurrency` to serialize deployments.
     - Use a dedicated CI queue.
     - If the function interface can evolve, include a run id/reference in the queue item and verify that exact value.

4. **Medium - CI dependencies are not pinned**
   - The workflow installs `uipath>=2.10.70`, `python-dotenv`, and `httpx` without upper bounds or a lock/constraints file.
   - Risk: future package changes can alter build/deploy behavior.
   - Suggested fix: pin versions or use a constraints file for CI.

5. **Medium - Script-only dependencies are not declared in project metadata**
   - `scripts/deploy_and_verify.py` imports `httpx` and `python-dotenv`.
   - CI and README install them manually, but `pyproject.toml` only declares the runtime dependency.
   - Suggested fix: add an optional dependency group such as:
     - `[project.optional-dependencies]`
     - `scripts = ["httpx", "python-dotenv"]`

6. **Low - Workflow token permissions are implicit**
   - The deploy workflow only needs repository checkout/read access.
   - Suggested fix: add `permissions: contents: read` to `.github/workflows/deploy-uipath.yml`.

7. **Low - README local setup is Bash-first despite Windows guidance**
   - README uses `.venv/bin/...`.
   - The project guidance says customer workspaces should use Windows Git/Windows VS Code.
   - Suggested fix: add PowerShell examples using `.venv\Scripts\...`.

8. **Low - Real tenant and deployment identifiers are documented**
   - `README.md` contains the real training tenant URL.
   - `NOTES.md` contains tenant URL, folder key, queue key, process key, job IDs, and queue item IDs.
   - These are not secrets, but they are operational metadata.
   - Suggested fix: keep as-is for a private repo; sanitize before making the repo public.

9. **Low - Constants are duplicated**
   - `QUEUE_NAME` and `FOLDER_PATH` exist in both `main.py` and `scripts/deploy_and_verify.py`.
   - Suggested fix: extract shared constants to a tiny module, or import them carefully from `main.py` if script/runtime coupling is acceptable.

10. **Low - No direct test for the registered `main()` entry point**
    - Existing tests cover `add_time_added_queue_item()` and timestamp format.
    - Suggested fix: mock `add_time_added_queue_item()` and assert `main()` delegates to it.

### Claude Code Cross-Check

Claude Code saved a project memory note under the local Claude memory directory. Useful items from that note:
- Accepted: script-only dependencies should be represented in `pyproject.toml`.
- Accepted: duplicated `QUEUE_NAME` and `FOLDER_PATH` are a maintainability issue.
- Accepted: README exposes a real tenant URL.
- Accepted: CI dependency pinning should be tightened.
- Accepted: add a test for `main()`.

Items that do not match the current repository state:
- `main.py` return type: the installed SDK source annotates `queues.create_item()` as returning `Response`, but the implementation returns `response.json()`. The current `dict[str, Any]` annotation is consistent with runtime behavior. This is not a current project bug, though the SDK annotation is misleading.
- Orchestrator client closing: `scripts/deploy_and_verify.py` already has `finally: orchestrator.close()`.
- `.gitignore` vs tracked AI-context files: `.agent/`, `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.codex/`, and `*.mermaid` are ignored and are not tracked in this repo.
- `.env.example` and `README.md` in the NuGet package: the current `.uipath/BareMinimumQueueTimeAdded.0.1.0.nupkg` does not include them.

### Remediation Implemented

Implemented on 2026-05-25:
- Added `.github/workflows/ci.yml` for push and pull request build/test/package verification.
- Added explicit `contents: read` workflow permissions.
- Added deployment workflow concurrency so manual deploys on the same ref do not overlap.
- Added a manual `allow_existing_package` workflow input for deliberate smoke tests of an already deployed package.
- Changed `scripts/deploy_and_verify.py` so package reuse fails by default during update deployments.
- Made `--package` optional in `scripts/deploy_and_verify.py`; the default path is derived from `pyproject.toml`.
- Declared script-only dependencies in `pyproject.toml` under `[project.optional-dependencies]`.
- Bounded package versions for `uipath`, `httpx`, and `python-dotenv`.
- Added a direct unit test for the registered `main()` entry point.
- Removed duplicated queue/folder constants from `scripts/deploy_and_verify.py` by importing them from `main.py`.
- Added `.env.example` and `README.md` to explicit UiPath package exclusions.
- Added a CI badge and clarified that the deploy badge is a manual deployment workflow.
- Replaced the real tenant URL in `README.md` with a placeholder.
- Added Windows PowerShell setup/auth examples.
- Bumped package version to `0.1.1` for the next deployment.

Remaining considerations:
- Smoke verification is safer because deployments are serialized, but it still relies on queue item timing rather than a unique run id. A unique reference/run id would require changing the function contract or queue payload.
- Release automation roadmap:
  - Current posture is `push to main -> CI`, then manual workflow dispatch for deployment.
  - A good next step is tag/release-gated CD: `push to main -> CI`, then `create GitHub release/tag vX.Y.Z -> deploy`.
  - Another option is environment promotion: `push to main -> deploy to dev`, then manual approval before prod.
  - Manual deployment remains the conservative default because the deploy workflow updates a real UiPath process and runs a smoke job with side effects.
- `NOTES.md` intentionally keeps historical tenant/folder/process/job IDs for private project traceability. Sanitize before making the repo public.

### Follow-Up Review Remediation

Implemented after Claude Code follow-up:
- Added `main.as_queue_item_data()` so `main.py` handles both the current SDK behavior (`create_item()` returns parsed JSON) and a response-like object with `.json()`.
- Added tests for response-like SDK results and unexpected SDK return types.
- Added `Orchestrator.__enter__()` and `Orchestrator.__exit__()` so deployment helper usage can be safely wrapped in `with`.
- Added `--old-package-version` for the old-package cleanup path. It defaults to the new package version for the package-rename case, but can now target a different old version explicitly.
- Added `.gitignore` comments explaining that local AI assistant context is ignored to prevent accidental staging.

Follow-up items intentionally not accepted as stated:
- The installed SDK source currently returns `response.json()` from `queues.create_item()`, despite its `Response` annotation. The production behavior seen in this environment is parsed JSON, not a raw `httpx.Response`; the code is now defensive either way.
- The ignored AI context files are not tracked in this repo. The `.gitignore` concern was handled with comments rather than removing the ignore rules.
