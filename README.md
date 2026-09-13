# Fusion 360 Codex Skill

A self-contained **`$fusion-bridge` Codex skill**, Windows Fusion add-in, standard-library Python client, and optional MCP server. Inspect and edit an open Autodesk Fusion design through its API instead of mouse/keyboard automation.

This is an independent integration, not an Autodesk product. Fusion must be installed and running. API coverage and licensing still apply: this does **not** promise every UI operation or a headless CAD engine.

## Install as a Codex skill

Ask Codex:

> Install the skill from M-DGayle/fusion-360-codex-skill, branch dev, repository path `.`, using the skill name `fusion-bridge`.

Install the whole repository root, not just SKILL.md. With Codex's bundled skill installer, the arguments are:

```text
--repo M-DGayle/fusion-360-codex-skill --ref dev --path . --name fusion-bridge
```

This repository is public and available under the MIT license. Start a new Codex task after installation if the skill is not discovered in the current session. This repository's root is the portable skill directory; no additional repository is needed for its runtime resources.

### One-time Fusion activation

From the installed skill directory, using Python 3.12:

```powershell
python scripts/setup_bridge.py --dry-run
```

In Fusion's **Utilities > Add-Ins > Scripts and Add-Ins** (Shift+S), link the printed folder ending in `addin/FusionBridge`, start **FusionBridge**, and optionally enable **Run on Startup**. Then:

```powershell
python bridge_client.py status
python bridge_client.py documents
```

The CLI requires only Python's standard library. The skill can use it immediately after activation; MCP is optional. For the optional 13-tool MCP facade, `python scripts/setup_bridge.py --mcp` installs the pinned SDK into a user-local virtual environment and generates a gitignored, machine-specific `.mcp.json`. It does not register the server in Codex or activate Fusion. See [setup and stopping](references/setup.md).

Example request:

> Use $fusion-bridge to inspect the active design, report its dimensions, and capture the viewport without changing geometry.

## Capabilities

- Inspect open documents, body bounds/volumes, assembly occurrences, entity tokens, parameters, feature health, and joint validity.
- Capture an actual Fusion viewport PNG and export F3D, STEP, or a selected body's STL.
- Change user parameters, with a mandatory pre-edit recovery archive.
- Execute Python using the Fusion API for sketches, solids, assemblies, joints, and other supported operations.
- Track jobs by UUID, deduplicate identical submissions within an activation, and cancel queued jobs.
- Save a new version of an already-saved document when explicitly authorized; editing does not automatically cloud-save.

See [SKILL.md](SKILL.md) for agent behavior and [API reference](references/api.md) for operation names and arguments. MCP tools are defined in [server.py](server.py).

## Security and failure boundaries

The add-in listens only on `127.0.0.1`, using an ephemeral port and fresh bearer token. It checks Host, rejects browser Origin headers, and does not enable CORS. All Autodesk API work runs on Fusion's main thread through a custom event.

**Python execution is privileged and not sandboxed.** It has Fusion's filesystem, network, and process permissions. The acknowledgement flag and document check prevent some accidents; they are not security isolation. Only run reviewed code within the user's request. The connection file inherits the user's filesystem permissions, so this does not protect against other processes running as the same user or administrators.

The bridge refuses mismatched active-document IDs and busy interactive commands. Parameter/Python edits require a successful F3D backup first. Failures may leave partial changes: there is no automatic rollback. A client timeout does not prove an edit failed, and running CAD/Python jobs cannot safely be force-interrupted. Inspect the original request ID before any retry.

Private state lives under the Fusion user's `.fusion-bridge` directory: connection credentials, audit log, recovery archives, and exports. Never commit or share that directory. Artifacts accumulate without automatic deletion. The single connection file supports one running Fusion process per user.

## Validation

From the repository root:

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python scripts/validate_package.py
# Requires the optional MCP dependency:
python tests/mcp_smoke.py
# Optional: running Fusion/add-in; reads and captures the active model:
python tests/mcp_smoke.py --live
# Optional: creates/edits/archives/closes its own scratch design:
python tests/live_modeling.py "<outside-repository>/live-modeling-output"
```

Use the Python interpreter containing `mcp` for MCP tests (the generated `.mcp.json` identifies it). Live tests create private artifacts: keep their outputs outside this repository. The scratch test must be deliberately selected; CI does not run it.

On Windows with Fusion **2704.1.15**, local integration testing on 2026-09-13 established actual 13-tool MCP discovery, live inspection/capture, rejection guards, scratch extrusion (20 x 10 x 5 mm), parameter editing to 6 mm thickness, write deduplication, F3D/STEP/STL export, and expected 600 mm3 overlap detection. The user's original document was restored active with unchanged measured geometry and its pre-existing modified flag. Add-in hot reload/reconnection worked.

A full Fusion quit/relaunch, cloud saving, macOS, multiple simultaneous Fusion processes, exhaustive API/workspace coverage, and physical print fit/strength have **not** been validated. Run on Startup being enabled is not cold-start proof. CI validates transport/guards/setup and MCP protocol discovery, not licensed Fusion modeling.

## Sources

- [Autodesk scripts and add-ins](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/WritingDebugging_UM.htm)
- [Autodesk main-thread custom events](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Threading_UM.htm)
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

## License

This integration is open source under the [MIT License](LICENSE). Autodesk Fusion and third-party dependencies remain subject to their own licenses; this license does not grant rights to Autodesk software, branding, or user CAD models.
