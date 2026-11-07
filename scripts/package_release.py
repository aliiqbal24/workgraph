"""Build reviewable, channel-specific source bundles. No uploads or self-updates."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from workgraph.version import __version__


def build(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Enumerate a deliberate source allowlist, independent of untracked recordings,
    # environments, databases, caches, build products, and local access files.
    common = [
        "README.md",
        "LICENSE",
        "pyproject.toml",
        "workgraph",
        "skills",
        "adapters",
        "assets",
        "docs",
        "scripts",
        "CHANGELOG.md",
    ]
    variants = {
        "hermes": common + ["__init__.py", "plugin.yaml"],
        "codex": common + ["plugin.json", "mcp.json"],
        "claude": common + [".claude-plugin/plugin.json", ".mcp.json"],
    }
    report = {}
    for channel, roots in variants.items():
        path = output / f"workgraph-{__version__}-{channel}.zip"
        files = {}
        for name in roots:
            source = ROOT / name
            for file in source.rglob("*") if source.is_dir() else [source]:
                if (
                    not file.is_file()
                    or file.is_symlink()
                    or "__pycache__" in file.parts
                    or file.suffix in (".pyc", ".pyo")
                ):
                    continue
                key = file.relative_to(ROOT).as_posix()
                files[key] = file.read_bytes()
        # Public portable packages do not discover or declare lifecycle hooks.
        for name in ("plugin.json", ".claude-plugin/plugin.json"):
            if name in files:
                manifest = json.loads(files[name])
                if channel == "codex":
                    manifest.get("extensions", {}).get("com.openai", {}).pop(
                        "hooks", None
                    )
                else:
                    manifest.pop("hooks", None)
                files[name] = (json.dumps(manifest, indent=2) + "\n").encode()
        with zipfile.ZipFile(
            path, "w", zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for name, content in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.external_attr = 0o644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, content)
        report[channel] = {
            "file": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
            "files": len(files),
        }
    (output / "SHA256SUMS").write_text(
        "".join(f"{entry['sha256']}  {entry['file']}\n" for entry in report.values())
    )
    (output / "manifest.json").write_text(
        json.dumps({"version": __version__, "bundles": report}, indent=2) + "\n"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))
