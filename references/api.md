# Direct bridge API

The CLI operates on transport operation names (not always the MCP tool names). It prints a job envelope with `request_id`, `status`, and `result` or `error`. A pending job is not a result. Capture output omits the base64 image but retains its local PNG path.

```powershell
python "<skill-directory>/bridge_client.py" inspect --arguments-file "<task-directory>/inspect.json"
python "<skill-directory>/bridge_client.py" execute_python --arguments-file "<task-directory>/edit.json" --request-id "<new-UUID>"
python "<skill-directory>/bridge_client.py" job_status --request-id "<original-UUID>"
```

Use a task-local JSON arguments file to avoid shell quoting errors. Write it with the environment's approved file-editing tool. `--output` writes the returned JSON to a path the user placed in scope; do not overwrite existing files inadvertently.

| CLI operation | Arguments | MCP name if different |
|---|---|---|
| status | none | |
| documents | none | |
| inspect | document_id, optional offset=0 and limit=100 (1-250) | |
| health | document_id | feature_health |
| interference | document_id, body_tokens (2-40) | check_interference |
| capture | document_id, optional width and height | capture_viewport |
| export | document_id, format (f3d/step/stl), filename; body_token for STL | export_file |
| set_parameter | document_id, name, expression | |
| execute_python | document_id, code, acknowledge_full_access=true | |
| save | document_id, description | save_document |
| create_scratch | none; creates and activates an unsaved design | create_scratch_document |
| job_status | UUID via --request-id | |

For cancellation, use MCP `cancel_queued_job` or Python `Client().http('/cancel', {'request_id': key})`. The CLI does not expose a cancellation shortcut. A running operation cannot be interrupted by this method.

## General Python

`execute_python` compiles and executes the provided code on Fusion's main thread, with `app`, `design`, `root`, `adsk`, `core`, `fusion`, `math`, and `artifact_dir`. Assign JSON-serializable data to `result`. Return only the measurements/identifiers needed for verification. Example arguments for an authorized operation:

```json
{
  "document_id": "<fresh-active-document-id>",
  "acknowledge_full_access": true,
  "code": "result = {'body_count': root.bRepBodies.count}"
}
```

Even this read-like Python example creates a recovery archive because arbitrary code is classified as privileged. Prefer the dedicated inspection tools for routine reads. Code is limited to 100,000 characters and must not block the main thread with long loops, networking, or waits. API lengths are centimeters and angles radians. Inspect `server.py` for MCP tool schemas and `addin/FusionBridge/FusionBridge.py` for current dispatch behavior when more detail is required.

## Job invariants

The queue allows 32 pending jobs; unstarted jobs expire after 30 seconds. Up to 1,000 outcomes are retained per activation. Client polling is bounded (15 seconds by default), and results may arrive later. Identical ID/payload pairs return the same job; a changed payload under the same ID is rejected. Results are not durable across add-in restarts. An unknown ID requires state inspection before reissuing any write.

Recovery archives precede parameter/Python edits. Python exceptions can leave partial geometry changes; there is no automatic rollback. Dedicated exports use unique artifact folders and filenames with the requested extension. STL exports one identified body; F3D/STEP export the design. Cloud save only handles an already-saved document; an unsaved document needs a user-chosen destination outside this tool or a local archive.
