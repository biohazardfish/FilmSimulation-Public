from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_curated_snapshot_has_no_history_or_private_disclosures(tmp_path):
    audit = load_script("audit_public_snapshot")
    if (ROOT / "PUBLIC_SNAPSHOT_MANIFEST.json").is_file():
        # A pristine snapshot is audited before bootstrap. After bootstrap, the
        # ignored RAW, cache, upstream checkout, virtual environment, and smoke
        # outputs are expected local state, so the test verifies the immutable
        # package contract rather than misclassifying runtime files as release
        # contents.
        manifest = json.loads(
            (ROOT / "PUBLIC_SNAPSHOT_MANIFEST.json").read_text(encoding="utf-8")
        )
        assert manifest["source_tree_dirty"] is False
        assert manifest["git_history_included"] is False
        assert manifest["raw_input_included"] is False
        assert manifest["kodak_pdfs_included"] is False
        assert manifest["identifiable_scene_assets_included"] is False
        assert manifest["stale_rendered_roadmap_included"] is False
        assert manifest["decision_0006_statuses"]["FS-P5-02"] == "blocked"
        return

    builder = load_script("build_public_snapshot")
    snapshot = tmp_path / "snapshot"
    manifest = builder.build_snapshot(ROOT, snapshot)
    # Test builds occur before the candidate commit is created; the final
    # release audit separately requires source_tree_dirty=false.
    manifest["source_tree_dirty"] = False
    (snapshot / "PUBLIC_SNAPSHOT_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    result = audit.audit_snapshot(snapshot)
    assert result == {"status": "pass", "failures": []}

    readme = snapshot / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\n[broken](missing-public-target.md)\n",
        encoding="utf-8",
    )
    broken = audit.audit_snapshot(snapshot)
    assert any(
        "missing local Markdown target in README.md" in failure
        for failure in broken["failures"]
    )
