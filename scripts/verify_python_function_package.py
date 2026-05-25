import glob
import json
import pathlib
import sys
import zipfile


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"{path} is missing")
    except json.JSONDecodeError as exc:
        fail(f"{path} is not valid JSON: {exc}")


def main() -> None:
    root = pathlib.Path(".")
    config = load_json(root / "uipath.json")

    if not config.get("functions"):
        fail("uipath.json has no functions")
    if config.get("agents"):
        fail("uipath.json contains agents")

    for path in ("agent.json", "langgraph.json", "llamaindex.json", "openai_agents.json"):
        if (root / path).exists():
            fail(f"{path} present")

    entry_points = load_json(root / "entry-points.json").get("entryPoints", [])
    if not entry_points:
        fail("entry-points.json has no entryPoints")

    non_function_entries = [
        (entry.get("filePath"), entry.get("type"))
        for entry in entry_points
        if entry.get("type") != "function"
    ]
    if non_function_entries:
        fail(f"non-function entrypoints: {non_function_entries}")

    uiproj = load_json(root / "project.uiproj")
    if uiproj.get("ProjectType") != "Function":
        fail(f"project.uiproj ProjectType={uiproj.get('ProjectType')!r}")

    packages = sorted(
        glob.glob(".uipath/*.nupkg"),
        key=lambda package: pathlib.Path(package).stat().st_mtime,
    )
    if not packages:
        fail("no .uipath/*.nupkg found; run uipath pack first")

    package = packages[-1]
    with zipfile.ZipFile(package) as archive:
        operate = json.loads(archive.read("content/operate.json"))
        if operate.get("targetRuntime") != "python":
            fail(f"operate.json targetRuntime={operate.get('targetRuntime')!r}")
        if operate.get("contentType") != "function":
            fail(f"operate.json contentType={operate.get('contentType')!r}")

        packed_entry_points = json.loads(
            archive.read("content/entry-points.json")
        ).get("entryPoints", [])
        if any(entry.get("type") != "function" for entry in packed_entry_points):
            fail("packed entry-points.json contains non-function entrypoints")

    print(f"OK: {package} is Python/function")


if __name__ == "__main__":
    main()
