# Chat Archify Lite

**English** | [简体中文](README.zh-CN.md)

Turn long conversations into an interactive map of branches, decisions and changes. Start with the diagram; click a node to read evidence, formatted Markdown and downloadable files. No repository is required. **Runs only when explicitly requested.**

## Release status and comparison

Current version: **0.1.1 · local preview (2026-10-11)**. Implementation and program-level checks are complete. Real-browser visual, focus, touch, download and storage acceptance remains pending. This is a prerelease, not a claim of complete browser acceptance.

Download `chat-archify-lite.zip` from [GitHub Releases](https://github.com/Wyyyyuu/chat-archify-lite/releases/tag/v0.1.1). Lite is public; the Pro repository and release assets require authorized GitHub access. One-time purchase checkout is not connected, and a commercial update-entitlement duration has not been fixed.

| Capability | Lite (free) | Pro |
| --- | --- | --- |
| Scope | One conversation, one overview | Related conversations and multiple chapters |
| Diagram and evidence | Complete nodes, branches and evidence | Complete nodes, branches and evidence |
| Embedded attachments | Up to 3 distinct eligible files; other references remain visible | All eligible files, subject to per-file limits |
| Search | Node titles | Nodes, file contents and saved excerpts |
| Reading workspace | Diagram and node/file reading | Adjustable three-panel workspace and in-page conversation reader |
| Conversation/module links | Source evidence on nodes | Bidirectional manual links, export/import and stale-link recovery |
| Continuing in another AI | No dedicated handoff export | Project/chapter/node continuation packs |
| Updating an existing map | Regenerate | Stable identities, snapshot reuse, review and approved application |
| Skill update access | Public repository and release downloads | Manually issued authorization and verified ZIP download; checkout is not connected |

Both editions run only when explicitly requested and retain rendered/raw Markdown, eligible attachment downloads, offline HTML and structured JSON. Lite limits scope and embedded files, not the number of graph nodes. Each embedded file has a 25 MiB limit and remains subject to credential exclusions.

## Edition capabilities

One conversation and one overview; up to 3 distinct embedded non-conversation files; node-title search only.

Both editions retain complete nodes and relationships, crossing checks, node evidence, formatted/raw Markdown, downloads, offline HTML and structured JSON. The free quota does not truncate the conversation map.

Over-quota resources retain their names, original references, node associations and explanations, without embedding their bodies. Conversation-only evidence is exempt; a file also used as an artifact counts toward the quota. Missing/excluded files do not consume successful slots, and duplicate paths count once. Regeneration is supported; incremental merging is not.

## Install and invoke

Extract the ZIP and copy the complete `chat-archify-lite` folder into your host's skills directory, for example `~/.codex/skills/`. Keep all assets, scripts, references, tests and agent metadata. The entry point is `~/.codex/skills/chat-archify-lite/SKILL.md`.

```text
Use $chat-archify-lite to map the conversation I specify. Preserve branches, decisions, changes, source evidence and resource links.
```

The bundled agent metadata sets `allow_implicit_invocation: false`. Other hosts may not recognize this setting. Unavailable history requires a user-provided export; summaries must not be presented as verbatim messages.

## Reproduce the demo

Generation requires Python 3.9+, Node.js 18+, and a separately installed [Archify](https://github.com/tt-a1i/archify). Integration is verified against 2.17.0-dev.1. Archify is neither bundled nor automatically installed. Reading a generated HTML requires a browser supporting JavaScript, SVG and Blob.

From this skill directory (quote paths containing spaces):

```sh
python scripts/build_lite_demo.py --archify-dir "<directory containing bin/archify.mjs>" --out-dir "demo-output"
```

Open `demo-output/chat-archify-lite-demo.html`. The fictional example contains 5 nodes, 5 edges and 4 Markdown resources. On the node “合并为弹性阅读计划”, inspect “补充阅读资料”, or search the body-only phrase “蓝鲸书签”. Lite retains the fourth resource as a reference and searches titles only; Pro embeds and searches its body.

The helper runs showcase validation, all-route geometry/topology checks, file-byte assertions and Node fake-DOM tests. These do not constitute real-browser or visual acceptance. No network access, dependency installation or server is required by the helper.

## Files and boundaries

- [SKILL.md](SKILL.md) contains the AI workflow; [record format](references/graph-format.md) describes the portable evidence record.
- Eligible files remain subject to a 25 MiB per-file limit and credential exclusions.
- Sharing an HTML also shares its embedded messages and file snapshots. Blob links are session-local, not permanent sharing URLs.
- Markdown uses bundled [Marked under MIT](assets/vendor/marked-LICENSE.md) and controlled DOM rendering. Raw HTML is not executed; remote images are not automatically fetched.
- READMEs are bilingual; the current viewer and example text are primarily Chinese.
- Payment, online licensing, update notifications and automatic updates are not implemented. User content is not automatically published.
