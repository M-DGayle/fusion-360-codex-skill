# Installation and activation

Supported/tested host: Windows, Autodesk Fusion desktop, Python 3.12 for the external client. The Fusion add-in uses Fusion's bundled Python and Autodesk modules. macOS has not been validated and the add-in manifest currently declares Windows only.

Install the entire repository root as the skill folder named `fusion-bridge`; installing only SKILL.md omits the working integration. For Codex's bundled GitHub skill installer, use repository `M-DGayle/fusion-360-codex-skill`, ref `dev`, path `.`, and name `fusion-bridge`. The installer defaults to `main`, so specify `dev`. Private repository access requires an authenticated GitHub account with access.

The standalone client requires no third-party packages. From the installed skill folder, preview the exact activation path:

```powershell
python scripts/setup_bridge.py --dry-run
```

In Fusion, open Utilities > Add-Ins > Scripts and Add-Ins (Shift+S). Link the folder printed by setup, ending in `addin/FusionBridge`. Start **FusionBridge**, and optionally enable **Run on Startup**. Initial activation needs no Fusion restart. If an older copy is already linked, stop it and choose the intended source; do not run multiple copies. Do not move the linked source while Fusion is using it.

```powershell
python bridge_client.py status
python bridge_client.py documents
```

If automatic Codex skill discovery requires a new session, start a new task after installation. A skill alone does not register MCP tools; CLI access works without them.

## Optional MCP facade

Only when MCP setup is requested, run:

```powershell
python scripts/setup_bridge.py --mcp
```

This creates/reuses the user's `.fusion-bridge/venv`, installs `requirements.txt`, and creates a machine-specific `.mcp.json` beside SKILL.md. It does not change Codex's global configuration or register/start the Fusion add-in. A differing existing `.mcp.json` is refused unless `--replace-config` is explicitly supplied. Review that file when registering the optional MCP server in the host; it is gitignored and must not be published. The source includes a Codex plugin descriptor for hosts supporting plugin installation, but skill installation and MCP/plugin registration are separate steps.

## Local data and stopping

Fusion creates `.fusion-bridge` in its user's home directory, containing the ephemeral connection credentials, audit log, and unique artifact/recovery folders. The external client must run as the same user. One running Fusion process per user is supported.

Stop FusionBridge in Scripts and Add-Ins to close the listener and invalidate its connection file. Disable Run on Startup if desired. Remove any separately configured MCP server/plugin through its host and remove the installed skill only after stopping the linked add-in. Backups and model exports are retained; delete them only with explicit user authorization.

If jobs remain queued, first inspect their status and whether a Fusion dialog or command is blocking execution. A timeout is not evidence that an edit failed. Do not restart Fusion or delete connection files as an automatic repair.
