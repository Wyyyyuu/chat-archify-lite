#!/usr/bin/env python3
"""Schema and URI validation shared by the Lite packager."""
import os
import re
from pathlib import Path, PureWindowsPath
from urllib.parse import quote, urlsplit

STATUS = {'proposed': '提议', 'in_progress': '进行中', 'completed': '已完成', 'verified': '已验证', 'failed': '失败', 'paused': '暂停', 'superseded': '被替代', 'unknown': '待确认'}
KIND = {'goal': '目标', 'milestone': '里程碑', 'module': '模块', 'experiment': '尝试', 'decision': '决策', 'issue': '问题'}
EDGE = {'continues': '延续', 'branches': '分叉', 'adds': '增加', 'pivots': '转向', 'merges': '合并', 'depends_on': '依赖', 'chronological': '仅先后'}
ID = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,63}$')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def fields(obj, names, context):
    need(isinstance(obj, dict), f'{context}: 必须是对象')
    for name in names:
        need(isinstance(obj.get(name), str) and obj[name].strip(), f'{context}.{name}: 必须是非空字符串')


def optional_strings(obj, names, context):
    for name in names:
        need(name not in obj or isinstance(obj[name], str), f'{context}.{name}: 必须是字符串')


def href_for(uri, base, out):
    """Resolve local targets without accessing them; reject executable/network URIs."""
    need(isinstance(uri, str), 'URI 必须是字符串')
    if not uri:
        return ''
    need(uri == uri.strip() and not any(ord(c) < 32 for c in uri), 'URI 含控制字符或首尾空白')
    need(not uri.startswith(('//', '\\\\')), '不支持网络共享路径')
    if re.match(r'^[A-Za-z]:[\\/]', uri):
        return PureWindowsPath(uri).as_uri()
    parts = urlsplit(uri)
    if parts.scheme:
        need(parts.scheme.lower() in {'https', 'http', 'file', 'codex', 'mailto'}, f'禁止的 URI 协议: {parts.scheme}')
        if parts.scheme.lower() in {'https', 'http'}:
            need(bool(parts.netloc) and not parts.username and not parts.password, 'HTTP URL 需要主机且不能含登录凭据')
        if parts.scheme.lower() == 'file':
            need(not parts.netloc or parts.netloc.lower() == 'localhost', '不支持远程 file URI')
            need(not parts.path.startswith('//'), '不支持网络共享 file URI')
        return uri
    if uri.startswith('#'):
        return uri
    path = Path(uri)
    if path.is_absolute():
        return path.as_uri()
    target = (base / path).resolve()
    try:
        return quote(Path(os.path.relpath(target, out)).as_posix(), safe='/')
    except ValueError:
        return target.as_uri()


def validate(data, base, out):
    need(isinstance(data, dict) and data.get('schema_version') == 1, 'schema_version 必须为 1')
    fields(data.get('project'), ['title', 'summary'], 'project')
    for key in ['updated_at', 'current_state']:
        need(isinstance(data['project'].get(key), str), f'project.{key}: 必须是字符串')
    for key in ['coverage', 'open_questions', 'revisions']:
        need(isinstance(data.get(key), list) and all(isinstance(v, str) and v.strip() for v in data[key]), f'{key}: 必须是字符串数组')
    need(bool(data['coverage']), 'coverage 不得为空')
    for key in ['sources', 'nodes', 'edges']:
        need(isinstance(data.get(key), list), f'{key}: 必须是数组')
    need(data['sources'] and data['nodes'], 'sources 和 nodes 不得为空')
    indexes = {}
    for group in ['sources', 'nodes']:
        ids = set()
        for item in data[group]:
            fields(item, ['id', 'title'], group)
            need(ID.fullmatch(item['id']) and item['id'] not in ids, f'{group}: 无效或重复 ID {item["id"]}')
            ids.add(item['id'])
        indexes[group] = ids
    for src in data['sources']:
        fields(src, ['kind', 'coverage', 'locator'], src['id'])
        need(src['coverage'] in {'full', 'excerpt', 'summary', 'unavailable'}, f'{src["id"]}: 未知 coverage')
        optional_strings(src, ['uri', 'note', 'original_url'], src['id'])
        need('original_url_verified' not in src or isinstance(src['original_url_verified'], bool), f'{src["id"]}.original_url_verified: 必须是布尔值')
        src['href'] = href_for(src.get('uri', ''), base, out)
        if src.get('original_url'):
            need(src['original_url'] == src['original_url'].strip(), f'{src["id"]}.original_url: 含首尾空白')
            original = urlsplit(src['original_url'])
            need(original.scheme.lower() == 'https' and original.netloc and not original.username and not original.password,
                 f'{src["id"]}.original_url: 仅接受无凭据的 HTTPS URL')

    def evidence(obj, label):
        refs = obj.get('evidence')
        need(isinstance(refs, list) and refs, f'{label}: 缺少 evidence')
        for ref in refs:
            fields(ref, ['source', 'locator'], label)
            optional_strings(ref, ['note'], label)
            need(ref['source'] in indexes['sources'], f'{label}: 未知来源 {ref["source"]}')

    for node in data['nodes']:
        nid = node['id']
        fields(node, ['kind', 'summary', 'branch', 'status'], nid)
        optional_strings(node, ['reason', 'date'], nid)
        need(node['kind'] in KIND and node['status'] in STATUS, f'{nid}: 未知 kind/status')
        evidence(node, nid)
        node.setdefault('artifacts', [])
        need(isinstance(node['artifacts'], list), f'{nid}.artifacts: 必须是数组')
        for art in node['artifacts']:
            fields(art, ['label', 'uri', 'role', 'verification'], nid)
            optional_strings(art, ['version', 'note'], nid)
            need(art['role'] in {'produced', 'modified', 'referenced'}, f'{nid}: 未知产物 role')
            need(art['verification'] in {'exists', 'missing', 'mentioned', 'unchecked'}, f'{nid}: 未知产物 verification')
            art['href'] = href_for(art['uri'], base, out)
    seen_edges = set()
    for edge in data['edges']:
        fields(edge, ['from', 'to', 'type', 'confidence', 'reason'], 'edge')
        need(edge['from'] in indexes['nodes'] and edge['to'] in indexes['nodes'], 'edge: 悬空节点引用')
        need(edge['type'] in EDGE and edge['confidence'] in {'explicit', 'inferred'}, 'edge: 未知 type/confidence')
        key = (edge['from'], edge['to'], edge['type'])
        need(key not in seen_edges, 'edge: 重复关系')
        seen_edges.add(key)
        evidence(edge, str(key))
    return data
