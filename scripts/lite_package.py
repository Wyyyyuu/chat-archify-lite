#!/usr/bin/env python3
"""Build a single-conversation, title-search-only Chat Archify Lite page."""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import html
import json
import mimetypes
import os
import re
import shutil
import sys
from collections import Counter
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from check_routes import audit_file
from credential_guard import credential_reason, decode_text
from record_schema import validate as validate_record

MAX_BYTES = 25 * 1024 * 1024
MAX_ATTACHMENTS = 3
TASK_ID = re.compile(r"(?:任务\s*ID|task(?:\s*id)?)\s*[:：]\s*([0-9a-f-]{16,})", re.I)


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def local_path(uri: str, base: Path) -> Path | None:
    if not isinstance(uri, str) or not uri or uri.startswith("#"):
        return None
    if re.match(r"^[A-Za-z]:[\\/]", uri):
        return Path(uri).resolve()
    parsed = urlsplit(uri)
    if parsed.scheme.lower() == "file":
        raw = unquote(parsed.path)
        if re.match(r"^/[A-Za-z]:/", raw):
            raw = raw[1:]
        return Path(raw).resolve()
    if parsed.scheme or parsed.netloc:
        return None
    return (base / unquote(parsed.path)).resolve()


class ViewerTopologyParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.nodes: set[str] = set()
        self.edges: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "g" and a.get("data-node-id"):
            node_id = a["data-node-id"]
            if node_id in self.nodes:
                raise ValueError(f"Duplicate Archify node ID: {node_id}")
            self.nodes.add(node_id)
        if tag == "path" and "data-edge-from" in a:
            self.edges.append((a.get("data-edge-from", ""), a.get("data-edge-to", "")))


def validate_topology(record: dict, viewer_bytes: bytes, chapter_id: str) -> dict:
    parser = ViewerTopologyParser()
    parser.feed(viewer_bytes.decode("utf-8"))
    record_ids = {node["id"] for node in record.get("nodes", [])}
    if not record_ids or parser.nodes != record_ids:
        raise ValueError(
            f"Chapter {chapter_id}: viewer/record node IDs differ; "
            f"missing={sorted(record_ids-parser.nodes)}, extra={sorted(parser.nodes-record_ids)}"
        )
    for source, target in parser.edges:
        if source not in record_ids or target not in record_ids:
            raise ValueError(f"Chapter {chapter_id}: viewer edge has unknown endpoint ({source} -> {target})")
    expected = Counter((edge["from"], edge["to"]) for edge in record.get("edges", []))
    actual = Counter(parser.edges)
    if actual != expected:
        raise ValueError(
            f"Chapter {chapter_id}: viewer/record directed edge mismatch; "
            f"missing={dict(expected-actual)}, extra={dict(actual-expected)}"
        )
    return {"node_ids": len(record_ids), "edge_count": sum(expected.values())}


def conversation_task_ids(record: dict, base: Path) -> set[str]:
    found = set()
    for source in record.get("sources", []):
        if source.get("kind") != "conversation":
            continue
        explicit = source.get("task_id")
        if explicit:
            found.add(str(explicit).lower())
        path = local_path(source.get("uri", ""), base)
        if path and path.is_file() and path.stat().st_size <= MAX_BYTES:
            try:
                text = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError):
                continue
            found.update(value.lower() for value in TASK_ID.findall(text))
    return found


def package(manifest_path: Path, output: Path) -> dict:
    manifest_path, output = manifest_path.resolve(), output.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    chapters = manifest.get("chapters")
    if not isinstance(chapters, list) or len(chapters) != 1:
        raise ValueError("Lite accepts exactly one chapter/overview. Choose one conversation or use Chat Archify Pro.")
    chapter = chapters[0]
    base = manifest_path.parent
    record_path = (base / chapter["record"]).resolve()
    viewer_path = (base / chapter["viewer"]).resolve()
    record = json.loads(record_path.read_text(encoding="utf-8-sig"))
    record = validate_record(copy.deepcopy(record), record_path.parent, output.parent)
    conversation_sources = [source for source in record["sources"] if source.get("kind") == "conversation"]
    if len(conversation_sources) > 1:
        raise ValueError("Lite accepts one conversation source. Choose one conversation or use Chat Archify Pro.")
    task_ids = conversation_task_ids(record, record_path.parent)
    if len(task_ids) > 1:
        raise ValueError("This conversation source contains multiple task IDs. Choose one task or use Chat Archify Pro.")

    viewer_bytes = viewer_path.read_bytes()
    geometry = audit_file(viewer_path)
    if geometry["conflicting_pair_count"] or geometry["node_crossing_count"]:
        raise ValueError(f"Chapter {chapter['id']}: route geometry has conflicts; no edges were removed")
    topology = validate_topology(record, viewer_bytes, chapter["id"])

    pool: dict[str, dict] = {}
    embedded_nonconversation: set[str] = set()
    resolved_file_ids: dict[str, str] = {}

    def attach(item: dict, record_base: Path, is_conversation_source: bool = False) -> None:
        uri = item.get("uri", "")
        path = local_path(uri, record_base)
        if path is None:
            parsed = urlsplit(str(uri))
            if parsed.scheme and parsed.scheme.lower() not in {"http", "https", "mailto"}:
                item["attachment_note"] = "不支持此类资源协议；保留原始引用。"
            return
        key_path = os.path.normcase(str(path))
        file_id = resolved_file_ids.get(key_path)
        if file_id:
            item["file_id"] = file_id
            return
        file_id = "file_" + hashlib.sha256(key_path.encode("utf-8")).hexdigest()[:20]
        resolved_file_ids[key_path] = file_id
        item["file_id"] = file_id
        name = path.name or str(path)
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        file = {"id": file_id, "path": str(path), "name": name, "mime": mime, "status": "missing"}
        pool[file_id] = file

        try:
            if not path.exists() or not path.is_file():
                return
            reason = credential_reason(path.name)
            if reason:
                file.update(status="excluded", note=reason)
                return
            size = path.stat().st_size
            if size > MAX_BYTES:
                file.update(status="excluded", note="超过单文件 25 MiB 限制，仅保留原始引用与位置。")
                return

            # Conversation-only evidence is exempt. If the same path is also an
            # artifact or document source, that non-conversation reference makes
            # it quota-bound before embedding.
            nonconversation = not is_conversation_source
            quota_full = nonconversation and len(embedded_nonconversation) >= MAX_ATTACHMENTS
            if quota_full:
                file.update(status="excluded", note="Lite 最多内嵌 3 个不同的非对话文件；已保留来源、关联和路径，正文未读取。请用 Pro 内嵌更多文件。")
                return

            raw = path.read_bytes()
            reason = credential_reason(path.name, raw)
            if reason:
                file.update(status="excluded", note=reason)
                return
            if not mime.startswith("image/"):
                text = decode_text(raw)
                if text is not None:
                    file["text"] = text
            file.update(status="embedded", data=b64(raw), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            if nonconversation:
                embedded_nonconversation.add(key_path)
        except OSError as error:
            file.update(status="excluded", note=f"无法读取文件，仅保留原始引用与位置：{error.strerror or 'I/O 错误'}")

    # Artifact references establish quota priority; document-only references
    # follow, and conversation-only sources are attached last and exempt.
    for node in record["nodes"]:
        for artifact in node.get("artifacts", []):
            attach(artifact, record_path.parent)
    for source in record["sources"]:
        if source.get("kind") != "conversation":
            attach(source, record_path.parent)
    for source in conversation_sources:
        attach(source, record_path.parent, is_conversation_source=True)

    # Ensure a dual-purpose path is quota-bound even when its conversation
    # source was attached first by upstream data ordering.
    for source in conversation_sources:
        path = local_path(source.get("uri", ""), record_path.parent)
        if path is None or os.path.normcase(str(path)) not in resolved_file_ids:
            continue
        file = pool[resolved_file_ids[os.path.normcase(str(path))]]
        also_nonconversation = any(
            item.get("file_id") == file["id"]
            for node in record["nodes"] for item in node.get("artifacts", [])
        ) or any(
            item.get("file_id") == file["id"]
            for item in record["sources"] if item.get("kind") != "conversation"
        )
        key_path = os.path.normcase(str(path))
        if also_nonconversation and file.get("status") == "embedded" and key_path not in embedded_nonconversation:
            if len(embedded_nonconversation) >= MAX_ATTACHMENTS:
                file.update(status="excluded", data=None, bytes=None, sha256=None, text=None,
                            note="Lite 最多内嵌 3 个不同的非对话文件；已保留来源、关联和路径，正文未读取。请用 Pro 内嵌更多文件。")
            else:
                embedded_nonconversation.add(key_path)

    payload = {
        "title": manifest.get("title", "Chat Archify Lite"),
        "edition": "lite",
        "chapter": {"id": chapter["id"], "label": chapter.get("label", chapter["id"]),
                    "record": record, "viewer": b64(viewer_bytes),
                    "viewer_sha256": hashlib.sha256(viewer_bytes).hexdigest()},
        "files": pool,
        "recordExport": json.loads(record_path.read_text(encoding="utf-8-sig")),
    }
    source_root = Path(__file__).resolve().parents[1]
    template = (source_root / "assets" / "lite.html").read_text(encoding="utf-8")
    shared_assets = [source_root / "assets" / "vendor" / "marked.umd.js",
                     source_root / "assets" / "markdown.js",
                     source_root / "assets" / "lite.js"]
    script = "\n;\n".join(path.read_text(encoding="utf-8") for path in shared_assets)
    if re.search(r"</script", script, re.I):
        raise ValueError("Inline script contains a closing script tag")
    serialized = json.dumps(payload, ensure_ascii=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    replacements = {"@@TITLE@@": html.escape(payload["title"]), "@@PAYLOAD@@": serialized, "@@SCRIPT@@": script}
    page = re.sub(r"@@(?:TITLE|PAYLOAD|SCRIPT)@@", lambda match: replacements[match[0]], template)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        backup = output.parent / "history" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output, backup / output.name)
    output.write_text(page, encoding="utf-8")
    report = {
        "output": str(output), "bytes": output.stat().st_size,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "chapter": {"id": chapter["id"], "nodes": len(record["nodes"]), "edges": len(record["edges"]),
                    "topology": topology, "route_audit": geometry},
        "files": [{"id": item["id"], "name": item["name"], "path": item["path"],
                   "status": item["status"], "bytes": item.get("bytes"), "sha256": item.get("sha256"),
                   "note": item.get("note")} for item in pool.values()],
    }
    (output.parent / "lite-package-receipt.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "edition": "lite", "nodes": len(record["nodes"]),
                      "edges": len(record["edges"]), "files": len(pool),
                      "embedded": sum(file["status"] == "embedded" for file in pool.values())}, ensure_ascii=False))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        package(args.manifest, args.output)
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
