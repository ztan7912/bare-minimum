# Bare Minimum UiPath Python Function

Pure Python UiPath function that adds one item to Orchestrator queue `Test_Queue`.
The queue item contains one custom field, `TimeAdded`, with the current UTC time.

## Project Shape

- `main.py` contains the function implementation.
- `uipath.json` declares a function entry point, not an agent.
- `entry-points.json`, `bindings.json`, and `project.uiproj` are generated UiPath metadata.
- `scripts/verify_python_function_package.py` fails closed if the package is not Python/function.
- `scripts/deploy_and_verify.py` can upload the package, create the process, run a smoke job, and verify the queue item.

## Local Setup

```bash
python -m venv .venv
.venv/bin/pip install "uipath>=2.10.70" python-dotenv httpx
cp .env.example .env
```

Authenticate locally:

```bash
UIPATH_URL=https://cloud.uipath.com/<organization>/<tenant> .venv/bin/uipath auth --cloud --force --tenant <tenant>
```

The CLI writes local auth values to `.env`. That file is intentionally ignored by git.

## Build And Verify

```bash
.venv/bin/uipath init --no-agents-md-override
.venv/bin/uipath pack --nolock
.venv/bin/python scripts/verify_python_function_package.py
.venv/bin/python -m unittest discover -s tests
```

Expected package identity:

- Package name: `BareMinimumQueueTimeAdded`
- Process type after deployment: `Function`

## Deploy

Example deployment to a target folder:

```bash
.venv/bin/python scripts/deploy_and_verify.py \
  --package .uipath/BareMinimumQueueTimeAdded.0.1.0.nupkg \
  --create-missing-folder \
  --create-missing-queue \
  --state-path .uipath/deploy-result.json
```

The helper is intentionally conservative: it checks package/process collisions, verifies Orchestrator `ProcessType == Function`, starts a smoke job, and verifies a new queue item with exactly `TimeAdded`.

## Credential Handling

Do not commit `.env`, `.uipath/`, virtualenvs, generated packages, or auth artifacts.

For CI/CD, use a UiPath External Application and store values in GitHub Actions secrets:

- `UIPATH_URL`
- `UIPATH_CLIENT_ID`
- `UIPATH_CLIENT_SECRET`
- `UIPATH_SCOPE`

Recommended token request scope for a fine-grained confidential app is `OR.Default`; assign the app itself to the target tenant/folder with the minimum role needed. For this deployment helper, the app needs permissions to upload packages, create/update processes, create/read queues and queue items, and start/read jobs. If the helper should create folders, the app also needs folder administration permission at the tenant level; otherwise create `Shared/UiPath` once manually and omit `--create-missing-folder`.

Example non-interactive auth:

```bash
.venv/bin/uipath auth \
  --cloud \
  --base-url "$UIPATH_URL" \
  --client-id "$UIPATH_CLIENT_ID" \
  --client-secret "$UIPATH_CLIENT_SECRET" \
  --scope "$UIPATH_SCOPE"
```

