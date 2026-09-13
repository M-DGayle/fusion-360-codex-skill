"""Show activation instructions; optionally prepare a local MCP runtime/config."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def config_for(root, state):
    return {"mcpServers": {"fusion": {
        "command": str(state / "venv" / "Scripts" / "python.exe"),
        "args": [str(root / "server.py")],
    }}}


def write_config(path, config, replace=False):
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing == config:
            return
        if not replace:
            raise RuntimeError("Existing MCP config differs; review it before using --replace-config.")
    with path.open("w" if replace else "x", encoding="utf-8") as stream:
        json.dump(config, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcp", action="store_true", help="Install the optional MCP dependency and generate local launch config")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without changing files or installing packages")
    parser.add_argument("--replace-config", action="store_true", help="Explicitly replace a differing local .mcp.json")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("This release supports Windows Fusion only.")
    if sys.version_info < (3, 12):
        parser.error("Use Python 3.12 or newer for setup.")
    state = Path.home() / ".fusion-bridge"
    config_path = ROOT / ".mcp.json"
    config = config_for(ROOT, state)
    plan = {
        "addin_folder": str(ROOT / "addin" / "FusionBridge"),
        "cli": [sys.executable, str(ROOT / "bridge_client.py"), "status"],
        "mcp_requested": args.mcp,
        "mcp_config_path": str(config_path) if args.mcp else None,
        "dry_run": args.dry_run,
    }
    if args.mcp and not args.dry_run:
        if config_path.exists() and not args.replace_config:
            if json.loads(config_path.read_text(encoding="utf-8")) != config:
                parser.error("Existing MCP config differs; review it before using --replace-config.")
        runtime = Path(config["mcpServers"]["fusion"]["command"])
        if not runtime.exists():
            venv.EnvBuilder(with_pip=True).create(state / "venv")
        subprocess.run([str(runtime), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=True)
        write_config(config_path, config, args.replace_config)
    print(json.dumps(plan, indent=2))
    print("Link the add-in folder in Fusion's Scripts and Add-Ins, then start FusionBridge.")
    print("No Fusion activation or Codex global configuration change was performed.")


if __name__ == "__main__":
    main()
