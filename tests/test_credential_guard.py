#!/usr/bin/env python3
"""Focused credential-filter regressions for the standalone Lite package."""
from __future__ import annotations

import base64
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "interactive-demo"
if not EXAMPLE.is_dir():
    EXAMPLE = ROOT.parent / "examples" / "interactive-demo"
sys.path.insert(0, str(ROOT / "scripts"))
from credential_guard import CREDENTIAL_NOTE, credential_reason
from lite_package import package


def read_payload(path: Path) -> dict:
    page = path.read_text(encoding="utf-8")
    match = re.search(r'<script type="application/json" id="lite-data">([\s\S]*?)</script>', page)
    if not match:
        raise AssertionError("packaged HTML has no lite-data payload")
    return json.loads(match.group(1))


def write_viewer(path: Path) -> None:
    path.write_text(
        """<svg>
<path data-edge-from="combined-plan" data-edge-to="review-later" data-edge-key="0" d="M 534 246 L 590.4 246" />
<path data-edge-from="daily-option" data-edge-to="combined-plan" data-edge-key="1" d="M 260 246 L 374 246" />
<path data-edge-from="question" data-edge-to="daily-option" data-edge-key="2" d="M 140 120 L 214 120 L 214 220" />
<path data-edge-from="question" data-edge-to="weekend-option" data-edge-key="3" d="M 48 120 L 32 120 L 32 426 L 214 426 L 214 398" />
<path data-edge-from="weekend-option" data-edge-to="combined-plan" data-edge-key="4" d="M 260 372 L 454 372 L 454 280" />
<g data-node-id="question"><rect x="48" y="94" width="92" height="52" /></g>
<g data-node-id="daily-option"><rect x="168" y="220" width="92" height="52" /></g>
<g data-node-id="combined-plan"><rect x="374" y="212" width="160" height="68" /></g>
<g data-node-id="review-later"><rect x="590.4" y="220" width="92" height="52" /></g>
<g data-node-id="weekend-option"><rect x="168" y="346" width="92" height="52" /></g>
</svg>""",
        encoding="utf-8",
    )


class LiteCredentialGuardTests(unittest.TestCase):
    def test_common_names_and_provider_content_are_blocked(self):
        self.assertEqual(credential_reason(".env.local"), CREDENTIAL_NOTE)
        self.assertEqual(
            credential_reason("config.txt", b"OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz0123456789"),
            CREDENTIAL_NOTE,
        )
        self.assertEqual(
            credential_reason("notes.md", b"ghp_123456789012345678901234567890123456"),
            CREDENTIAL_NOTE,
        )

    def test_safe_document_placeholders_are_allowed(self):
        text = "OPENAI_API_KEY=YOUR_API_KEY\nGITHUB_TOKEN=${GITHUB_TOKEN}\nos.getenv(\"OPENAI_API_KEY\")\n"
        self.assertIsNone(credential_reason("setup.md", text.encode("utf-8")))

    def test_packaging_excludes_utf16_secrets_without_embedding_them(self):
        with tempfile.TemporaryDirectory(prefix="chat-archify-lite-credentials-") as directory:
            root = Path(directory)
            source = root / "source"
            shutil.copytree(EXAMPLE, source)
            write_viewer(source / "archify-overview.html")
            record_path = source / "evolution.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["nodes"][0]["artifacts"][0:0] = [
                {"label": "OpenAI settings", "uri": "config.txt", "role": "referenced", "verification": "exists"},
                {"label": "GitHub notes", "uri": "token-notes.md", "role": "referenced", "verification": "exists"},
                {"label": "Safe setup guide", "uri": "safe-notes.md", "role": "referenced", "verification": "exists"},
            ]
            record_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            openai_secret = "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789"
            github_secret = "ghp_123456789012345678901234567890123456"
            (source / "config.txt").write_text(
                f"OPENAI_API_KEY={openai_secret}\n"
                "AWS_ACCESS_KEY_ID=AKIA1234567890ABCDEF\n"
                "AWS_SECRET_ACCESS_KEY=AbCdEf0123456789/AbCdEf0123456789\n",
                encoding="utf-16",
            )
            (source / "token-notes.md").write_text(f"# Example token\n{github_secret}\n", encoding="utf-8")
            safe_text = "# Setup\nOPENAI_API_KEY=YOUR_API_KEY\nGITHUB_TOKEN=${GITHUB_TOKEN}\nos.getenv(\"OPENAI_API_KEY\")\n"
            safe_path = source / "safe-notes.md"
            safe_path.write_text(safe_text, encoding="utf-8")
            safe_bytes = safe_path.read_bytes()
            output = root / "lite.html"
            package(source / "manifest.json", output)
            payload = read_payload(output)
            files = {item["name"]: item for item in payload["files"].values()}
            output_text = output.read_text(encoding="utf-8")
            for name, secret in (("config.txt", openai_secret), ("token-notes.md", github_secret)):
                self.assertEqual(files[name]["status"], "excluded")
                self.assertNotIn("data", files[name])
                self.assertNotIn(secret, output_text)
                self.assertNotIn(base64.b64encode(secret.encode()).decode(), output_text)
            safe = files["safe-notes.md"]
            self.assertEqual(safe["status"], "embedded")
            self.assertEqual(base64.b64decode(safe["data"], validate=True), safe_bytes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
