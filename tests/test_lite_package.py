#!/usr/bin/env python3
"""Portable Lite limits, schema, graph topology, and embedded-byte checks."""
from __future__ import annotations

import base64
import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT.parent / "examples" / "interactive-demo"
sys.path.insert(0, str(ROOT / "scripts"))
from check_routes import audit_file
from lite_package import package, validate_topology
from record_schema import validate


def read_payload(path: Path) -> dict:
    page = path.read_text(encoding="utf-8")
    match = re.search(r'<script type="application/json" id="lite-data">([\s\S]*?)</script>', page)
    if not match:
        raise AssertionError("Lite page has no lite-data payload")
    return json.loads(match.group(1))


class LitePackageTests(unittest.TestCase):
    example_dir = EXAMPLE

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="chat-archify-lite-")
        self.root = Path(self.temp.name)
        self.example = self.root / "demo"
        shutil.copytree(self.example_dir, self.example)
        self.manifest = self.example / "manifest.json"
        self.viewer = self.example / "archify-overview.html"
        self.out = self.root / "lite.html"

    def tearDown(self):
        self.temp.cleanup()

    def json_file(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, path: Path, value: dict) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    def build(self) -> dict:
        package(self.manifest, self.out)
        return read_payload(self.out)

    def test_demo_keeps_topology_and_embeds_only_three_distinct_artifacts(self):
        payload = self.build()
        record = payload["chapter"]["record"]
        self.assertEqual((len(record["nodes"]), len(record["edges"])), (5, 5))
        viewer = base64.b64decode(payload["chapter"]["viewer"], validate=True)
        self.assertEqual(hashlib.sha256(viewer).hexdigest(), payload["chapter"]["viewer_sha256"])
        self.assertEqual(viewer, self.viewer.read_bytes())
        topology = validate_topology(record, viewer, "overview")
        self.assertEqual(topology["edge_count"], 5)
        routes = audit_file(self.viewer)
        self.assertEqual((routes["conflicting_pair_count"], routes["node_crossing_count"]), (0, 0))

        files = {item["name"]: item for item in payload["files"].values()}
        for name in ("reading-plan.md", "daily-guide.md", "review-checklist.md", "conversation.md"):
            packed = files[name]
            self.assertEqual(packed["status"], "embedded")
            raw = base64.b64decode(packed["data"], validate=True)
            expected = self.example / "conversation.md" if name == "conversation.md" else self.example / "resources" / name
            self.assertEqual(raw, expected.read_bytes())
            self.assertEqual(hashlib.sha256(raw).hexdigest(), packed["sha256"])
        over_limit = files["source-brief.md"]
        self.assertEqual(over_limit["status"], "excluded")
        self.assertIn("正文未读取", over_limit["note"])
        self.assertNotIn("data", over_limit)
        self.assertNotIn("text", over_limit)
        self.assertNotIn("蓝鲸书签", self.out.read_text(encoding="utf-8"))
        source = next(item for item in record["sources"] if item["id"] == "source-brief")
        artifact = next(item for node in record["nodes"] for item in node["artifacts"] if item["uri"].endswith("source-brief.md"))
        self.assertEqual(source["file_id"], artifact["file_id"], "document-source reference cannot bypass the three-file quota")
        self.assertNotIn("search_text", json.dumps(payload, ensure_ascii=False))

    def test_valid_node_only_graph_is_accepted(self):
        record_path = self.example / "evolution.json"
        record = self.json_file(record_path)
        record["edges"] = []
        self.write_json(record_path, record)
        nodes = record["nodes"]
        paths = [f'<g data-node-id="{node["id"]}"><rect x="{i*120}" y="0" width="80" height="40"/></g>' for i, node in enumerate(nodes)]
        self.viewer.write_text('<svg>' + "".join(paths) + '</svg>', encoding="utf-8")
        payload = self.build()
        self.assertEqual(payload["chapter"]["record"]["edges"], [])
        self.assertEqual(audit_file(self.viewer)["edge_count"], 0)

    def test_multiple_chapters_are_rejected(self):
        manifest = self.json_file(self.manifest)
        manifest["chapters"].append(dict(manifest["chapters"][0], id="second"))
        self.write_json(self.manifest, manifest)
        with self.assertRaisesRegex(ValueError, "exactly one chapter"):
            self.build()

    def test_multiple_conversation_sources_are_rejected(self):
        path = self.example / "evolution.json"
        record = self.json_file(path)
        record["sources"].append({"id": "second-chat", "title": "Another", "kind": "conversation", "coverage": "excerpt", "locator": "source", "uri": "conversation.md"})
        self.write_json(path, record)
        with self.assertRaisesRegex(ValueError, "one conversation source"):
            self.build()

    def test_multiple_task_ids_inside_conversation_are_rejected(self):
        conversation = self.example / "conversation.md"
        conversation.write_text(conversation.read_text(encoding="utf-8") + "\n任务 ID：22222222-2222-4222-8222-222222222222\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "multiple task IDs"):
            self.build()

    def test_missing_and_credentials_do_not_consume_attachment_slots(self):
        path = self.example / "evolution.json"
        record = self.json_file(path)
        record["nodes"][1]["artifacts"][1]["uri"] = "missing-guide.md"
        record["nodes"][1]["artifacts"][1]["label"] = "Missing guide"
        record["nodes"][3]["artifacts"].append({"label": "Credential", "uri": ".env-demo", "role": "referenced", "verification": "exists"})
        (self.example / ".env-demo").write_text("TOKEN=not-a-real-token", encoding="utf-8")
        self.write_json(path, record)
        payload = self.build()
        files = {item["name"]: item for item in payload["files"].values()}
        self.assertEqual(files["missing-guide.md"]["status"], "missing")
        self.assertEqual(files[".env-demo"]["status"], "excluded")
        self.assertEqual(files["source-brief.md"]["status"], "embedded")
        embedded_nonconversation = [file for file in files.values() if file["status"] == "embedded" and file["name"] != "conversation.md"]
        self.assertEqual(len(embedded_nonconversation), 3)

    def test_oversized_file_does_not_consume_slot(self):
        path = self.example / "evolution.json"
        record = self.json_file(path)
        record["nodes"][1]["artifacts"][1]["uri"] = "oversized.bin"
        with (self.example / "oversized.bin").open("wb") as stream:
            stream.truncate(25 * 1024 * 1024 + 1)
        self.write_json(path, record)
        payload = self.build()
        files = {item["name"]: item for item in payload["files"].values()}
        self.assertEqual(files["oversized.bin"]["status"], "excluded")
        self.assertEqual(files["source-brief.md"]["status"], "embedded")

    def test_schema_rejects_executable_and_credentialed_urls(self):
        path = self.example / "evolution.json"
        record = self.json_file(path)
        record["sources"][1]["uri"] = "javascript:alert(1)"
        with self.assertRaisesRegex(ValueError, "禁止的 URI 协议"):
            validate(record, self.example, self.root)
        record["sources"][1]["uri"] = "https://user:pass@example.invalid/source"
        with self.assertRaisesRegex(ValueError, "不能含登录凭据"):
            validate(record, self.example, self.root)

    def test_viewer_must_match_record_topology(self):
        path = self.example / "evolution.json"
        record = self.json_file(path)
        with self.assertRaisesRegex(ValueError, "edge mismatch"):
            validate_topology(record, b'<svg>' + b''.join(f'<g data-node-id="{node["id"]}"></g>'.encode() for node in record["nodes"]) + b'</svg>', "missing-edge")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--example-dir", type=Path, default=EXAMPLE)
    args = parser.parse_args()
    LitePackageTests.example_dir = args.example_dir.resolve()
    sys.argv = [sys.argv[0]]
    unittest.main(verbosity=2)
