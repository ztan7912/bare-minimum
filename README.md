# Bare Minimum UiPath Python Function

[![CI](https://github.com/ztan7912/bare-minimum/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ztan7912/bare-minimum/actions/workflows/ci.yml)
[![Deploy UiPath Python Function](https://github.com/ztan7912/bare-minimum/actions/workflows/deploy-uipath.yml/badge.svg?branch=main)](https://github.com/ztan7912/bare-minimum/actions/workflows/deploy-uipath.yml)

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
.venv/bin/pip install ".[scripts]"
cp .env.example .env
```

PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install ".[scripts]"
Copy-Item .env.example .env
```

Authenticate locally:

```bash
UIPATH_URL=https://cloud.uipath.com/<organization>/<tenant> .venv/bin/uipath auth --cloud --force --tenant <tenant>
```

PowerShell:

```powershell
$env:UIPATH_URL = "https://cloud.uipath.com/<organization>/<tenant>"
.\.venv\Scripts\uipath.exe auth --cloud --force --tenant <tenant>
```

The CLI writes local auth values to `.env`. That file is intentionally ignored by git.

## Windows Git Workspace

This template is intended to work well from a normal Windows checkout, which is the likely shape in customer environments. Open the project with regular Windows VS Code and let it use Windows Git.

If you open the same Windows path from WSL, for example under `/mnt/c/Users/...`, Git may be able to read repository status but can run into write or locking issues around `.git` in sandboxed/WSL-mounted environments. For WSL-native development, clone the repository into the Linux filesystem instead:

```bash
mkdir -p ~/projects
cd ~/projects
git clone https://github.com/ztan7912/bare-minimum.git
```

Rule of thumb:

- Windows/customer workstation: keep the repo on Windows and use Windows Git.
- WSL/Codex-owned commits: use a fresh clone under `~/projects` or another WSL-native path.
- Avoid mixing Windows Git and WSL Git heavily on one `/mnt/c` worktree.

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
  --create-missing-folder \
  --create-missing-queue \
  --state-path .uipath/deploy-result.json
```

The helper derives the package path from `pyproject.toml` when `--package` is omitted. It is intentionally conservative: it checks package/process collisions, verifies Orchestrator `ProcessType == Function`, starts a smoke job, and verifies a new queue item with exactly `TimeAdded`. When updating an existing process, it fails if the target package version already exists unless `--allow-existing-package` is passed.

## Credential Handling

Do not commit `.env`, `.uipath/`, virtualenvs, generated packages, or auth artifacts.

For CI/CD, use a UiPath External Application and store values in GitHub Actions secrets:

- `UIPATH_URL`
- `UIPATH_CLIENT_ID`
- `UIPATH_CLIENT_SECRET`
- `UIPATH_SCOPE` (optional; defaults to `OR.Default` in the workflow)

In the External Apps UI, add Orchestrator API Access application scopes such as `OR.Execution`, `OR.Jobs`, `OR.Queues`, and `OR.Folders` if folder creation is needed. The CI token request uses `OR.Default`, which is requested at token time and resolved through Orchestrator role assignments.

Assign the external app itself with least-privilege Orchestrator roles:

- Tenant role, for package publishing and folder lookup: `Packages.View`, `Packages.Create`, and `Folders.View`.
- Folder role on `Shared/UiPath`, for process and runtime work: `Processes.View`, `Processes.Create`, `Processes.Edit`, `Queues.View`, `Queues.Create`, `Transactions.View`, `Transactions.Create`, `Jobs.View`, and `Jobs.Create`.

If the helper should create folders, the app also needs folder administration permission at the tenant level; otherwise create `Shared/UiPath` once manually and omit `--create-missing-folder`.

Example non-interactive auth:

```bash
.venv/bin/uipath auth \
  --cloud \
  --base-url "$UIPATH_URL" \
  --client-id "$UIPATH_CLIENT_ID" \
  --client-secret "$UIPATH_CLIENT_SECRET" \
  --scope "$UIPATH_SCOPE"
```

## GitHub Actions

The repository includes two workflows:

- `.github/workflows/ci.yml`: runs on `push` and `pull_request` to build, verify, and test the package.
- `.github/workflows/deploy-uipath.yml`: manual deployment and smoke test via `workflow_dispatch`.

Add these repository secrets:

- `UIPATH_URL`: `https://cloud.uipath.com/<organization>/<tenant>`
- `UIPATH_CLIENT_ID`: external app application/client ID
- `UIPATH_CLIENT_SECRET`: external app secret
- `UIPATH_SCOPE`: optional, use `OR.Default`

Before a deployment, bump `pyproject.toml` version so the package version is new. Then run **Actions > Deploy UiPath Python Function > Run workflow**. Use the `allow_existing_package` checkbox only when you intentionally want to smoke-test the currently deployed artifact without uploading a new package.

Current release posture:

```text
push to main -> CI
manual workflow dispatch -> deploy
```

This keeps every push tested without automatically changing the UiPath Cloud tenant. A good future evolution is semi-automatic CD, where a deliberate release signal triggers deployment:

```text
push to main -> CI
create GitHub release/tag vX.Y.Z -> deploy
```

Another future option is environment promotion:

```text
push to main -> deploy to dev
manual approval -> deploy to prod
```

For now, manual deployment is the conservative default because it updates a real UiPath process and runs a smoke job with side effects.
