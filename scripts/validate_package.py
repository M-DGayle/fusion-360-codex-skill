"""Validate the portable skill's metadata, resources, and local links."""
import json
from pathlib import Path
import re
import yaml

ROOT = Path(__file__).resolve().parents[1]


def main():
    content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n", content, re.S)
    assert match, "Missing skill frontmatter"
    metadata = yaml.safe_load(match.group(1))
    assert metadata["name"] == "fusion-bridge"
    assert isinstance(metadata["description"], str) and metadata["description"].strip()
    interface = yaml.safe_load((ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8"))["interface"]
    assert "$fusion-bridge" in interface["default_prompt"]
    assert 25 <= len(interface["short_description"]) <= 64
    required = ["bridge_client.py", "server.py", "requirements.txt", "scripts/setup_bridge.py",
                "addin/FusionBridge/FusionBridge.py", "addin/FusionBridge/transport.py",
                "addin/FusionBridge/FusionBridge.manifest"]
    for relative in required:
        assert (ROOT / relative).is_file(), relative
    for document in [ROOT / "SKILL.md", ROOT / "README.md", *sorted((ROOT / "references").glob("*.md"))]:
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            resolved = (document.parent / target.split("#")[0]).resolve()
            assert resolved.is_relative_to(ROOT), f"Link escapes package: {target}"
            assert resolved.exists(), f"Broken link: {document.name}: {target}"
    manifest = json.loads((ROOT / "addin/FusionBridge/FusionBridge.manifest").read_text())
    assert manifest["type"] == "addin" and manifest["supportedOS"] == "windows"
    print("Skill metadata, runtime resources, and local documentation links passed.")


if __name__ == "__main__":
    main()
