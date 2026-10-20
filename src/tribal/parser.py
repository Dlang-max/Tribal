"""Source-preserving Tribal Markdown v1 validation (no I/O or code execution)."""
from __future__ import annotations

import hashlib
import math
import posixpath
import re
from datetime import datetime
from importlib.resources import files
from urllib.parse import unquote, urlsplit

import unicodedata2 as unicode
from markdown_it import MarkdownIt
from ruamel.yaml import YAML
from ruamel.yaml.nodes import MappingNode, ScalarNode, SequenceNode
from ruamel.yaml.tokens import AliasToken, AnchorToken, TagToken

MAX_FILE = 8_388_608
KEY = re.compile(r'[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*\Z')
UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z')
GIT = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')
NIL = '00000000-0000-0000-0000-000000000000'
KNOWN = set('schema_version id title knowledge_base domain kind summary status tags aliases contexts scope verification_state verified_at verified_by sources cssclasses tribal_base_revision'.split())
OBSOLETE = set('repository scope_branch scope_commit scope_environments'.split())
DEFAULTS = dict(status='active', tags=[], aliases=[], contexts=[], scope={}, verification_state='unverified', sources=[])
SOURCE_TYPES = set('file observation experiment dataset publication interview code test issue document web other'.split())
# Frozen full default folding table; NFC comes from the pinned Unicode 15.1 library.
FOLD = {}
for _line in files('tribal').joinpath('CaseFolding-15.1.0.txt').read_text().splitlines():
    _parts = _line.split('#')[0].split(';')
    if len(_parts) >= 3 and _parts[1].strip() in ('C', 'F'):
        FOLD[int(_parts[0], 16)] = ''.join(chr(int(c, 16)) for c in _parts[2].split())


def _lines(text):
    # Markdown and transport physical lines are separated only by normalized LF.
    parts = text.split('\n')
    return [part+'\n' for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def _portable(path):
    return unicode.normalize('NFC', unicode.normalize('NFC', path).translate(FOLD))


def _uuid(v):
    return isinstance(v, str) and UUID.fullmatch(v) is not None and v != NIL


def _nonblank(v):
    return isinstance(v, str) and bool(v.strip())


def _preview(v):
    if isinstance(v, (str, list, dict)):
        v = repr(v)
        return v if len(v) <= 180 else v[:177] + '...'
    return v


class _Validation:
    def __init__(self, path, content):
        self.path, self.content = path, content
        self.lines = content.split('\n')
        self.diagnostics = []
        self.positions = {'frontmatter': (1, 1)}
        self.nodes = {}

    def add(self, code, message, *, field=None, actual=None, expected=None, hint=None, line=None, column=None):
        if line is None and field is not None and field != 'path':
            key = field
            while key not in self.positions and key:
                previous = key
                key = re.sub(r'(?:\.[^.\[]+|\[\d+\])$', '', key)
                if key == previous: break
            line, column = self.positions.get(key, (1, 1))
        if line is not None and column is None: column = 1
        excerpt = self.lines[line - 1][:240] if line and 0 < line <= len(self.lines) else None
        self.diagnostics.append(dict(code=code, severity='error' if code.startswith('E_') else 'warning',
            message=message, path=self.path, line=line, column=column, field=field,
            expected=expected, actual=_preview(actual), hint=hint or 'Correct the indicated value and validate again.', excerpt=excerpt))

    def invalid(self, field, value, expected, code='E_FIELD_TYPE'):
        self.add(code, f'{field} must be {expected}.', field=field, actual=value,
                 expected=expected, hint=f'Set {field} to {expected}.')

    def limit(self, field, value, maximum, unit='Unicode code points', **location):
        length = len(value.encode('utf-8')) if unit == 'UTF-8 bytes' else len(value)
        if length > maximum:
            self.add('E_LIMIT', f'{field} exceeds {maximum:,} {unit}.', field=field,
                     expected=f'at most {maximum:,} {unit}', actual=length,
                     hint='Shorten the value; accepted content is never truncated.', **location)


def _path(v):
    p = v.path
    if len(p) > 512: v.limit('path', p, 512)
    if (not p or p.startswith('/') or re.match(r'^[A-Za-z]:', p) or any(c in p for c in '\\\0#|[]')
        or any(s in ('', '.', '..') or s != s.strip() for s in p.split('/'))
        or p.startswith('.tribal-staging/') or not p.endswith('.md')):
        v.invalid('path', p, 'a vault-relative POSIX path ending in lowercase .md, without reserved characters, empty/dot segments, or surrounding segment whitespace', 'E_PATH')


def _frontmatter(v):
    lines = _lines(v.content)
    if not lines or lines[0] != '---\n':
        v.add('E_FRONTMATTER', 'The first line must be exactly ---.', line=1, column=1, field='frontmatter', expected='---', actual=lines[0] if lines else '', hint='Add opening YAML frontmatter on line 1.')
        return None
    close = next((i for i in range(1, len(lines)) if lines[i] == '---\n'), None)
    if close is None:
        v.add('E_FRONTMATTER', 'YAML frontmatter has no closing --- line.', field='frontmatter', expected='closing ---', hint='Close frontmatter before the Markdown body.')
        return None
    raw = ''.join(lines[1:close])
    y = YAML(typ='safe', pure=True)
    y.version = (1, 2)
    # ruamel's default schema additionally resolves timestamps; Tribal uses
    # YAML 1.2 core scalars, whose dates and UTC timestamps are plain strings.
    for initial, resolvers in y.resolver.versioned_resolver.items():
        y.resolver.versioned_resolver[initial] = [(tag, rx) for tag, rx in resolvers if tag != 'tag:yaml.org,2002:timestamp']
    try:
        prohibited = False
        for token in y.scan(raw):
            allowed_tag = isinstance(token, TagToken) and (token.value[0] == '!!' and token.value[1] in ('str','int','float','bool','null','seq','map') or token.value[0] is None and token.value[1] in {f'tag:yaml.org,2002:{t}' for t in ('str','int','float','bool','null','seq','map')})
            if isinstance(token, (AliasToken, AnchorToken)) or isinstance(token, TagToken) and not allowed_tag:
                v.add('E_FRONTMATTER', 'Custom/non-JSON YAML tags, anchors, and aliases are prohibited.', line=token.start_mark.line + 2, column=token.start_mark.column + 1, field='frontmatter', actual=type(token).__name__, expected='ordinary JSON-compatible YAML values', hint='Replace this construct with its literal value.')
                prohibited = True
        if prohibited: return None
        root = y.compose(raw)
        if y.version != (1, 2):
            v.invalid('frontmatter', y.version, 'YAML version 1.2', 'E_FRONTMATTER')
            return None
        if not isinstance(root, MappingNode) or root.flow_style:
            v.invalid('frontmatter', raw, 'a YAML 1.2 block mapping', 'E_FRONTMATTER')
            return None

        def convert(node, field):
            v.positions[field] = (node.start_mark.line + 2, node.start_mark.column + 1)
            v.nodes[field] = node
            if isinstance(node, MappingNode):
                result = {}
                for kn, vn in node.value:
                    if not isinstance(kn, ScalarNode) or kn.tag != 'tag:yaml.org,2002:str':
                        v.add('E_FRONTMATTER', 'All YAML mapping keys must be strings.', line=kn.start_mark.line+2, column=kn.start_mark.column+1, field=field, actual=kn.value, expected='string key', hint='Quote the mapping key.')
                        continue
                    k = kn.value
                    try: k.encode('utf-8')
                    except UnicodeEncodeError:
                        v.add('E_ENCODING', 'YAML key contains an invalid Unicode surrogate.', field=field or 'frontmatter', actual=k, expected='valid Unicode scalar text', hint='Replace the surrogate escape with a Unicode character.')
                        continue
                    sub = f'{field}.{k}' if field else k
                    if k == '<<':
                        v.add('E_FRONTMATTER', 'YAML merge keys are prohibited.', line=kn.start_mark.line+2, column=kn.start_mark.column+1, field=sub, actual=k, expected='explicit ordinary keys', hint='Write the merged fields explicitly.')
                    if k in result:
                        v.add('E_TRANSPORT' if sub == 'tribal_base_revision' else 'E_FRONTMATTER', f'Duplicate YAML key {k!r}.', line=kn.start_mark.line+2, column=kn.start_mark.column+1, field=sub, actual=k, expected='unique key at this nesting level', hint='Remove or rename the duplicate key.')
                    result[k] = convert(vn, sub)
                    v.positions[sub] = (kn.start_mark.line+2, kn.start_mark.column+1)
                return result
            if isinstance(node, SequenceNode):
                return [convert(n, f'{field}[{i}]') for i, n in enumerate(node.value)]
            # YAML core schema dates are strings, including unquoted UTC timestamps.
            if node.tag == 'tag:yaml.org,2002:timestamp': return node.value
            if node.tag not in {f'tag:yaml.org,2002:{s}' for s in ('str', 'int', 'float', 'bool', 'null')}:
                v.invalid(field, node.value, 'a JSON-compatible scalar', 'E_FRONTMATTER')
                return None
            value = y.constructor.construct_object(node)
            if isinstance(value, str):
                try: value.encode('utf-8')
                except UnicodeEncodeError:
                    v.invalid(field, value, 'valid Unicode scalar text encodable as UTF-8', 'E_ENCODING')
                    return None
            if isinstance(value, float) and not math.isfinite(value):
                v.invalid(field, node.value, 'a finite JSON number', 'E_FRONTMATTER')
                return None
            return value
        meta = convert(root, '')
        return meta, close, lines
    except Exception as e:
        mark = getattr(e, 'problem_mark', None)
        v.add('E_FRONTMATTER', f'Invalid YAML: {str(e)[:200]}', field='frontmatter',
              line=mark.line+2 if mark else 2, column=mark.column+1 if mark else 1,
              actual=str(e)[:200], expected='YAML 1.2 block mapping', hint='Correct the YAML syntax at this location.')
        return None


def _metadata(v, m, knowledge_base, domains):
    for field in ('schema_version', 'id', 'title', 'knowledge_base', 'domain', 'kind', 'summary'):
        if field not in m:
            v.invalid(field, None, 'present (required field)', 'E_REQUIRED_FIELD')
        elif isinstance(m[field], str) and not m[field].strip():
            v.invalid(field, m[field], 'nonblank (required field)', 'E_REQUIRED_FIELD')
    for f, x in m.items():
        if f in OBSOLETE: v.invalid(f, x, 'removed; migrate to explicit contexts and scope', 'E_CONTEXT')
        elif f not in KNOWN:
            if f.startswith('tribal_'): v.invalid(f, x, 'a recognized reserved Tribal property', 'E_TRANSPORT')
            elif not f.startswith('x_'):
                v.add('W_UNKNOWN_PROPERTY', f'Unknown property {f!r} is preserved without Tribal interpretation.', field=f, actual=f, expected='known property or x_ extension', hint='Use an x_ prefix for an intentional extension.')
    if 'schema_version' in m:
        if type(m['schema_version']) is not int: v.invalid('schema_version', m['schema_version'], 'integer 1')
        elif m['schema_version'] != 1: v.invalid('schema_version', m['schema_version'], 'supported schema version 1', 'E_SCHEMA_VERSION')
    if 'id' in m and not _uuid(m['id']): v.invalid('id', m['id'], 'a canonical lowercase non-nil UUID')
    for f in ('knowledge_base', 'domain'):
        if f in m and (not isinstance(m[f], str) or len(m[f]) > 128 or not KEY.fullmatch(m[f])):
            v.invalid(f, m[f], 'a key matching [a-z][a-z0-9]*(?:[-_][a-z0-9]+)*, at most 128 characters')
    if knowledge_base is not None and m.get('knowledge_base') != knowledge_base:
        v.invalid('knowledge_base', m.get('knowledge_base'), f'the configured knowledge base {knowledge_base!r}', 'E_ASSIGNMENT')
    if domains is not None and isinstance(m.get('domain'), str) and m['domain'] not in domains:
        v.invalid('domain', m['domain'], 'a registered domain key', 'E_ASSIGNMENT')
    if 'title' in m and (not _nonblank(m['title']) or '\n' in m['title'] or '\r' in m['title'] or len(m['title']) > 255):
        v.invalid('title', m['title'], 'a nonblank single-line string of at most 255 code points')
    if 'summary' in m:
        if not _nonblank(m['summary']): v.invalid('summary', m['summary'], 'a nonblank plain-text string')
        else:
            v.limit('summary', m['summary'], 8192, 'UTF-8 bytes')
            if len(re.findall(r'[.!?](?:\s|$)', m['summary'])) > 3:
                v.add('W_STYLE', 'Summary should contain one to three concise sentences.', field='summary', expected='one to three sentences', actual=m['summary'], hint='Consider shortening the summary.')
    for f, allowed in [('kind', ('finding', 'overview', 'decision', 'procedure', 'reference')), ('status', ('active', 'superseded', 'archived')), ('verification_state', ('unverified', 'verified', 'disputed'))]:
        if f in m and m[f] not in allowed: v.invalid(f, m[f], 'one of ' + ', '.join(allowed))
    if 'verified_at' in m:
        good = isinstance(m['verified_at'], str) and bool(re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', m['verified_at']))
        if good:
            try: datetime.strptime(m['verified_at'], '%Y-%m-%dT%H:%M:%SZ')
            except ValueError: good = False
        if not good: v.invalid('verified_at', m['verified_at'], 'a real UTC timestamp YYYY-MM-DDTHH:MM:SSZ')
    if 'verified_by' in m and (not _nonblank(m['verified_by']) or len(m['verified_by']) > 255):
        v.invalid('verified_by', m['verified_by'], 'a nonblank string of at most 255 characters')
    if m.get('verification_state') == 'verified':
        for f in ('verified_at', 'verified_by', 'sources'):
            if not m.get(f): v.invalid(f, m.get(f), 'present and nonempty for verified documents', 'E_VERIFICATION')
    for f in ('tags', 'aliases', 'cssclasses'):
        if f not in m: continue
        if not isinstance(m[f], list): v.invalid(f, m[f], 'a list of strings'); continue
        seen = set()
        for i, x in enumerate(m[f]):
            sf = f'{f}[{i}]'
            if not _nonblank(x): v.invalid(sf, x, 'a nonblank string'); continue
            if f in ('tags', 'aliases') and x in seen: v.invalid(sf, x, 'a unique value within this list')
            seen.add(x)
            if f == 'tags':
                if (any(not (unicode.category(c)[0] == 'L' or unicode.category(c) == 'Nd' or c in '_-/') for c in x)
                    or not any(unicode.category(c) != 'Nd' for c in x)):
                    v.invalid(sf, x, 'an Obsidian tag containing letters, digits, _, -, / and at least one nondigit, without a leading #')
                elif x != x.lower(): v.add('W_STYLE', 'Lowercase tag names are recommended.', field=sf, actual=x, expected='lowercase tag', hint='Consider a lowercase tag name.')
    for f, typ in [('contexts', list), ('sources', list), ('scope', dict)]:
        if f in m and not isinstance(m[f], typ): v.invalid(f, m[f], 'a list of mappings' if typ is list else 'a mapping')


def _parts(locator):
    try: return urlsplit(locator)
    except (ValueError, TypeError): return None


def _uri(locator):
    u = _parts(locator)
    return bool(u and re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', locator) and (u.netloc or u.path))


def _local_root(locator):
    return isinstance(locator, str) and bool(locator.startswith('/') or re.match(r'^[A-Za-z]:[\\/]', locator) or locator.startswith('\\\\'))


def _shape(v, obj, field, allowed, code):
    if not isinstance(obj, dict): v.invalid(field, obj, 'a mapping', code); return False
    for k, x in obj.items():
        if k not in allowed and not k.startswith('x_'): v.invalid(f'{field}.{k}', x, 'a recognized entry field or x_ extension (put custom facts in details)', code)
    return True


def _text(v, obj, key, field, *, required=False, maximum=None, byte_limit=False, code='E_SOURCE', syntax=False):
    if key not in obj and not required: return
    value = obj.get(key)
    sf = f'{field}.{key}'
    if not _nonblank(value): v.invalid(sf, value, 'a nonblank string' + (' (required)' if required else ''), code); return
    if maximum is not None:
        if byte_limit: v.limit(sf, value, maximum, 'UTF-8 bytes')
        elif len(value) > maximum: v.invalid(sf, value, f'a string of at most {maximum} code points', code)
    if syntax and not KEY.fullmatch(value): v.invalid(sf, value, 'a key matching [a-z][a-z0-9]*(?:[-_][a-z0-9]+)*', code)


def _contexts_sources(v, m, headings):
    contexts = m.get('contexts', []) if isinstance(m.get('contexts', []), list) else []
    sources = m.get('sources', []) if isinstance(m.get('sources', []), list) else []
    index = {}
    for i, c in enumerate(contexts):
        f = f'contexts[{i}]'
        if not _shape(v, c, f, {'key', 'type', 'locator', 'label', 'details'}, 'E_CONTEXT'): continue
        for k, maximum in [('key', 128), ('type', 64)]: _text(v, c, k, f, required=True, maximum=maximum, code='E_CONTEXT', syntax=True)
        _text(v, c, 'locator', f, required=c.get('type') in ('git_repository', 'filesystem'), maximum=8192, byte_limit=True, code='E_CONTEXT')
        _text(v, c, 'label', f, code='E_CONTEXT')
        if isinstance(c.get('key'), str):
            if c['key'] in index: v.invalid(f+'.key', c['key'], 'unique context key within this document', 'E_CONTEXT')
            else: index[c['key']] = c
        if 'details' in c and not isinstance(c['details'], dict): v.invalid(f+'.details', c['details'], 'a mapping', 'E_CONTEXT')
        d = c.get('details', {}) if isinstance(c.get('details', {}), dict) else {}
        typ, loc = c.get('type'), c.get('locator')
        if typ == 'git_repository':
            if isinstance(loc, str) and not (_uri(loc) or _local_root(loc) or re.fullmatch(r'[^\s/@]+@[^\s/:]+:.+', loc)):
                v.invalid(f+'.locator', loc, 'an absolute URI/local root or explicit user@host:path Git locator', 'E_CONTEXT')
            if 'commit' in d and (not isinstance(d['commit'], str) or not GIT.fullmatch(d['commit'])):
                v.invalid(f+'.details.commit', d['commit'], 'a full lowercase 40- or 64-character hexadecimal Git object ID', 'E_CONTEXT')
            if 'branch' in d and not _nonblank(d['branch']): v.invalid(f+'.details.branch', d['branch'], 'a nonblank branch string', 'E_CONTEXT')
        elif typ == 'filesystem':
            u = _parts(loc) if isinstance(loc, str) else None
            if not (_local_root(loc) or (u and u.scheme and (u.netloc or u.scheme == 'file') and u.path.startswith('/') and not u.query and not u.fragment)):
                v.invalid(f+'.locator', loc, 'an absolute local directory or absolute hierarchical URI with a path and no query/fragment', 'E_CONTEXT')
        elif isinstance(typ, str) and KEY.fullmatch(typ):
            v.add('W_CONTEXT_UNCHECKED', f'Context profile {typ!r} is preserved; its type-specific semantics are unchecked.', field=f+'.type', actual=typ, expected='common shape only', hint='Review profile-specific details separately; no resource is accessed.')
    for i, s in enumerate(sources):
        f = f'sources[{i}]'
        if not _shape(v, s, f, {'type', 'locator', 'section', 'context', 'revision', 'details'}, 'E_SOURCE'): continue
        _text(v, s, 'type', f, required=True, maximum=64, syntax=True)
        _text(v, s, 'locator', f, required=True, maximum=8192, byte_limit=True)
        for k, maximum in [('section', 255), ('context', 128), ('revision', 255)]: _text(v, s, k, f, maximum=maximum)
        if isinstance(s.get('section'), str): v.limit(f+'.section', s['section'], 255)
        if 'details' in s and not isinstance(s['details'], dict): v.invalid(f+'.details', s['details'], 'a mapping', 'E_SOURCE')
        d = s.get('details', {}) if isinstance(s.get('details', {}), dict) else {}
        ctx = index.get(s.get('context')) if isinstance(s.get('context'), str) else None
        if 'context' in s and ctx is None: v.invalid(f+'.context', s['context'], 'the exact key of a context declared in this note', 'E_CONTEXT')
        typ, loc = s.get('type'), s.get('locator')
        if ctx and ctx.get('type') == 'git_repository' and 'revision' in s and (not isinstance(s['revision'], str) or not GIT.fullmatch(s['revision'])):
            v.invalid(f+'.revision', s['revision'], 'a full lowercase 40- or 64-character Git object ID because this source selects a Git context', 'E_SOURCE')
        if typ in ('file', 'code') and isinstance(loc, str) and not _uri(loc):
            if not ctx or ctx.get('type') not in ('git_repository', 'filesystem'):
                v.invalid(f+'.context', s.get('context'), 'an explicit Git/filesystem context supplying the root for a relative file/code locator', 'E_CONTEXT')
            if '\\' in loc or loc.startswith('/') or '?' in loc or '#' in loc or any(p in ('', '.', '..') for p in loc.split('/')) or re.match(r'^[A-Za-z]:', loc):
                v.invalid(f+'.locator', loc, 'a relative POSIX path without empty/dot segments, leading slash, backslashes, query, or fragment (or a self-contained absolute URI)', 'E_CONTEXT')
        if typ in ('web', 'issue') and isinstance(loc, str):
            u = _parts(loc)
            if not u or u.scheme not in ('http', 'https') or not u.netloc: v.invalid(f+'.locator', loc, 'an absolute HTTP(S) URL with a host', 'E_SOURCE')
        if typ == 'document':
            if not _uuid(loc): v.invalid(f+'.locator', loc, 'a canonical non-nil Tribal document UUID', 'E_SOURCE')
            if 'revision' in s and not _uuid(s['revision']): v.invalid(f+'.revision', s['revision'], 'a canonical non-nil Tribal revision UUID', 'E_SOURCE')
            if 'context' in s: v.invalid(f+'.context', s['context'], 'omitted for an internal Tribal document source', 'E_SOURCE')
        if typ == 'test':
            if not _nonblank(d.get('outcome')): v.invalid(f+'.details.outcome', d.get('outcome'), 'a required nonblank outcome string', 'E_SOURCE')
            if 'command' in d and not _nonblank(d['command']): v.invalid(f+'.details.command', d['command'], 'a nonblank command string', 'E_SOURCE')
        if typ == 'other' and not d: v.invalid(f+'.details', d, 'nonempty details explaining the other source locator', 'E_SOURCE')
        if 'line_start' in d or 'line_end' in d:
            for k in ('line_start', 'line_end'):
                if type(d.get(k)) is not int or d[k] <= 0: v.invalid(f+'.details.'+k, d.get(k), 'a positive integer; both line_start and line_end are required', 'E_SOURCE')
            if type(d.get('line_start')) is int and type(d.get('line_end')) is int and d['line_end'] < d['line_start']:
                v.invalid(f+'.details.line_end', d['line_end'], 'greater than or equal to line_start', 'E_SOURCE')
        if 'section' in s:
            matches = [h for h in headings if h['text'] == s['section']]
            if len(matches) != 1 or not matches[0]['_plain']:
                v.invalid(f+'.section', s['section'], 'exactly one heading containing plain inline text without markup', 'E_SOURCE')
        if isinstance(typ, str) and KEY.fullmatch(typ) and typ not in SOURCE_TYPES:
            v.add('W_CONTEXT_UNCHECKED', f'Source profile {typ!r} is preserved; its type-specific semantics are unchecked.', field=f+'.type', actual=typ, expected='common shape only', hint='Review the source profile separately; no external evidence was fetched.')


def _markdown(v, body, canonical, canonical_body_offset, submitted_body_line):
    """Recognize block structure, then scan original eligible inline spans."""
    from markdown_it.rules_inline import link as md_link, image as md_image, autolink
    from markdown_it.rules_inline.backticks import backtick as backticks
    from markdown_it.rules_inline.state_inline import StateInline
    from bisect import bisect_right
    from .structure import Heading, build_structure

    md = MarkdownIt('commonmark', {'html': True}).enable('table', 'strikethrough')
    from markdown_it.rules_block import fence as original_fence
    def tracked_fence(state, start_line, end_line, silent):
        accepted = original_fence(state, start_line, end_line, silent)
        if accepted and not silent:
            token = state.tokens[-1]
            # The engine includes the last mapped line in content only when it
            # auto-closes a fence. Compare using the still-active container
            # offsets, before list/quote rules restore those offsets.
            token.meta['tribal_explicit_close'] = (
                state.line > start_line+1
                and token.content == state.getLines(start_line+1, state.line-1,
                                                     state.sCount[start_line], True))
        return accepted
    md.block.ruler.at('fence', tracked_fence)
    line_starts = [0]
    for match in re.finditer('\n', body): line_starts.append(match.end())
    def where(offset):
        ln = bisect_right(line_starts, offset)-1
        return submitted_body_line+ln, offset-line_starts[ln]+1
    def warn_extension(offset, description):
        ln, col = where(offset)
        v.add('W_EXTENSION_UNSUPPORTED', f'{description} is preserved; semantic extraction inside it is unsupported.', line=ln, column=col, actual=description, expected='opaque preserved source', hint='Keep essential knowledge relationships in ordinary links outside this extension.')
    # Mask recognized opaque extensions before block parsing; masks retain positions.
    chars = list(body)
    opaque = []
    protected = []
    def mask(a, b, description):
        if any(a >= x and b <= y for x,y in opaque): return
        opaque.append((a,b))
        protected.append((a,b,description))
        for j in range(a,b):
            if chars[j] != '\n': chars[j] = ' '
        warn_extension(a, description)
    # Existing code/HTML blocks establish literal regions before extension handling.
    preliminary = md.parse(body)
    literal = [(line_starts[t.map[0]], line_starts[t.map[1]] if t.map[1]<len(line_starts) else len(body))
               for t in preliminary if t.type in ('fence', 'code_block', 'html_block') and t.map]
    # Inline code is literal before extension markers are interpreted, too.
    inline_ranges = sorted({tuple(t.map) for t in preliminary if t.type == 'inline' and t.map})
    for start_line, end_line in inline_ranges:
        start = line_starts[start_line]
        end = line_starts[end_line] if end_line < len(line_starts) else len(body)
        raw_inline = body[start:end]
        state = StateInline(raw_inline, md, {}, [])
        cursor = 0
        while cursor < len(raw_inline):
            if raw_inline[cursor] == '\\': cursor += 2; continue
            if raw_inline[cursor] == '`':
                state.pos = cursor
                state.tokens = []
                backticks(state, False)
                if any(t.type == 'code_inline' for t in state.tokens):
                    literal.append((start+cursor, start+state.pos))
                cursor = max(cursor+1, state.pos)
            else: cursor += 1
    def in_literal(a): return any(x <= a < y for x,y in literal)
    for pattern, description in [
        (r'%%[\s\S]*?(?:%%|\Z)', 'Obsidian comment'),
        (r'<!--(?:[\s\S]*?)(?:-->|\Z)', 'HTML comment'),
        (r'(?m)^ {0,3}\$\$[^\n]*(?:\n[\s\S]*?(?:^ {0,3}\$\$[^\n]*(?:\n|$)|\Z)|$)', 'math block'),
        (r'(?m)^ {0,3}\\\[[\s\S]*?^ {0,3}\\\][^\n]*(?:\n|$)', 'math block'),
        (r'(?m)^ {0,3}\[\^[^\]\n]+\]:[^\n]*(?:\n(?:[ \t]*\n)*(?: {4,}|\t)[^\n]*)*', 'footnote definition'),
    ]:
        expression = re.compile(pattern)
        search_from = 0
        while (match := expression.search(body, search_from)) is not None:
            start, end = match.span()
            if in_literal(start):
                search_from = start+1
            else:
                mask(start, end, description)
                search_from = max(start+1, end)
    masked = ''.join(chars)
    env = {}
    tokens = md.parse(masked, env)
    headings = []
    structural_headings = []
    blocks = []
    table_lines = set()
    eligible = set()
    root_sections = []
    byte_starts = [canonical_body_offset]
    for line in _lines(body): byte_starts.append(byte_starts[-1]+len(line.encode('utf-8')))
    body_lines = _lines(body)
    ancestry = []
    root_end = 0
    def heading_text(inline):
        def flatten(children):
            return ''.join(t.content if t.type in ('text', 'code_inline') else '\n' if t.type in ('softbreak','hardbreak') else flatten(t.children or []) if t.type == 'image' else '' for t in children)
        return flatten(inline.children or []).strip()
    for i, token in enumerate(tokens):
        if token.type == 'inline' and token.map:
            eligible.update(range(token.map[0], token.map[1]))
        if token.type == 'table_open': table_lines.update(range(*token.map))
        if token.type == 'heading_open':
            inline = tokens[i+1]
            text = heading_text(inline)
            ln = token.map[0]
            # Token content excludes container prefixes; locate it in its source line.
            source_line = body_lines[ln].rstrip('\n')
            if token.markup.startswith('#'):
                opening = re.search(r'#{1,6}(?:[ \t]|$)', source_line)
                col = opening.start()+1 if opening else 1
            else:
                col = source_line.find(inline.content)
                col = col+1 if col >= 0 else 1
            plain = all(t.type == 'text' for t in inline.children or []) and inline.content.strip() == text
            h = dict(level=int(token.tag[1:]), text=text, line=submitted_body_line+ln, column=col, _plain=plain)
            headings.append(h)
            structural_headings.append(Heading(byte_starts[token.map[0]], byte_starts[token.map[1]],
                                               'heading', h['level'], text, plain, token.level == 0))
            if token.level == 0:
                v.limit('heading', text, 255, line=h['line'], column=h['column'])
                if ancestry and h['level'] > ancestry[-1][0]+1:
                    v.add('W_STYLE', 'Heading levels skip a level.', line=h['line'], column=h['column'], actual=h['level'], expected='a continuous heading hierarchy', hint='Consider adding the missing parent heading level.')
                while ancestry and ancestry[-1][0] >= h['level']: ancestry.pop()
                ancestry.append((h['level'], text))
                root_sections.append((ln, text))
        if token.type in ('fence', 'code_block', 'html_block'):
            if token.map: eligible.difference_update(range(*token.map))
        if token.type == 'html_block' and token.map:
            warn_extension(line_starts[token.map[0]], 'raw HTML block')
        if token.type == 'fence':
            start, end = token.map
            # Closure is recorded while the parser's container offsets are active.
            closed = token.meta.get('tribal_explicit_close', False)
            if not closed:
                ln,col=where(line_starts[start])
                v.add('E_UNCLOSED_FENCE', 'Fenced block requires an explicit matching closing fence.', line=ln, column=col, actual=token.markup, expected='closing fence of the same character and at least the opening length', hint='Add a closing fence on its own line.')
            if token.info.split()[:1] == ['mermaid']:
                ln,col=where(line_starts[start])
                v.add('W_MERMAID_UNCHECKED', 'Mermaid source is preserved; no Mermaid syntax parser or renderer was run.', line=ln, column=col, actual=token.info, expected='syntax unchecked', hint='Review the diagram with a separately configured Mermaid renderer.')
            elif not token.info.strip():
                ln,col=where(line_starts[start])
                v.add('W_STYLE', 'A code-fence language identifier is recommended.', line=ln, column=col, expected='an optional language such as text or python', actual='', hint='Consider adding an appropriate language identifier.')
        # Root units plus nested rich blocks preserve both grouping and rich identity.
        if token.map and ((token.level == 0 and (token.nesting == 1 or token.type in ('fence','code_block','html_block','hr'))) or token.type in ('table_open','fence','code_block')):
            kind = {'table_open':'table','fence':'code','code_block':'code','html_block':'html','heading_open':'heading','paragraph_open':'paragraph','bullet_list_open':'list','ordered_list_open':'list','blockquote_open':'blockquote','hr':'thematic_break'}.get(token.type, token.type.removesuffix('_open'))
            if token.type == 'fence' and token.info.split()[:1] == ['mermaid']: kind='mermaid'
            a,b=token.map
            a_byte,b_byte=byte_starts[a],byte_starts[min(b,len(byte_starts)-1)]
            blocks.append(dict(kind=kind,start_byte=a_byte,end_byte=b_byte,heading_path=[x[1] for x in ancestry]))
    root_titles = [h for h in headings if h['level']==1]
    if not root_titles:
        v.add('W_STYLE', 'A title heading matching metadata.title is recommended.', line=submitted_body_line, column=1, expected='optional # title heading', hint='Consider adding a title heading.')
    elif len(root_titles)>1:
        v.add('W_STYLE', 'Multiple title headings are present.', line=root_titles[1]['line'], column=root_titles[1]['column'], expected='one title heading', actual=len(root_titles), hint='Consider using lower heading levels for sections.')
    if root_titles and root_titles[0]['text'] != v.title:
        v.add('W_STYLE', 'The first title heading differs from metadata.title.', line=root_titles[0]['line'], column=root_titles[0]['column'], expected=v.title, actual=root_titles[0]['text'], hint='Consider making the title heading match the metadata title.')
    # Preserve gaps (blank lines, reference definitions, opaque regions) as spans.
    covered = sorted((b['start_byte'],b['end_byte']) for b in blocks)
    cursor = canonical_body_offset
    for a,b in covered:
        if a > cursor: blocks.append(dict(kind='source',start_byte=cursor,end_byte=a,heading_path=[]))
        cursor=max(cursor,b)
    if cursor < len(canonical.encode('utf-8')):
        blocks.append(dict(kind='source',start_byte=cursor,end_byte=len(canonical.encode('utf-8')),heading_path=[]))
    blocks.sort(key=lambda b:(b['start_byte'],-b['end_byte']))
    # Each physical inline line is scanned once, preserving raw table escapes.
    intervals=[]
    for ln in sorted(eligible):
        if intervals and intervals[-1][1] == line_starts[ln]: intervals[-1]=(intervals[-1][0],line_starts[ln+1])
        else: intervals.append((line_starts[ln],line_starts[ln+1]))
    links=[]
    def record(raw, target, anchor, kind, offset):
        ln,col=where(offset)
        v.limit('raw_link', raw, 16384, 'UTF-8 bytes',line=ln,column=col)
        v.limit('target_text',target,1024,line=ln,column=col)
        if anchor is not None: v.limit('target_anchor',anchor,255,line=ln,column=col)
        body_ln=ln-submitted_body_line
        source_anchor=next((text for start,text in reversed(root_sections) if start<=body_ln),None)
        links.append(dict(ordinal=len(links),raw_link=raw,target_text=target,target_anchor=anchor,source_anchor=source_anchor,kind=kind,target_document_id=None,resolution='unresolved',line=ln,column=col))
    for a,b in intervals:
        source=body[a:b]
        state=StateInline(source,md,env,[])
        i=0
        while i<len(source):
            absolute=a+i
            masked_range=next(((x,y) for x,y in opaque if x<=absolute<y),None)
            if masked_range: i=min(len(source),masked_range[1]-a); continue
            ch=source[i]
            if ch=='\\':
                # GFM only escapes ASCII punctuation; otherwise this is literal.
                if i+1<len(source) and source[i+1] in r'!"#$%&\'()*+,-./:;<=>?@[\]^_`{|}~\\': i+=2
                else: i+=1
                continue
            if source.startswith('![[',i):
                end=source.find(']]',i+3); nl=source.find('\n',i)
                end=end+2 if end>=0 and (nl<0 or end<nl) else nl if nl>=0 else len(source)
                warn_extension(absolute,'Obsidian embed');i=end;continue
            if source.startswith('[[',i):
                nl=source.find('\n',i)
                line_end=nl if nl>=0 else len(source)
                end=source.find(']]',i+2,line_end)
                stop=end+2 if end>=0 else line_end
                raw=source[i:stop]
                inside=source[i+2:end] if end>=0 else ''
                line_no=bisect_right(line_starts,absolute)-1
                in_table=line_no in table_lines
                # Every table pipe must be escaped in the original source.
                bad_table_pipe=in_table and bool(re.search(r'(?<!\\)\|',inside))
                if in_table: inside=inside.replace('\\|','|')
                alias=inside.split('|')
                target_anchor=alias[0].split('#',1)
                components=[*target_anchor,*alias[1:]]
                good = (end >= 0 and len(alias) <= 2 and not bad_table_pipe
                        and (bool(target_anchor[0]) or len(target_anchor) == 2 and bool(target_anchor[1]))
                        and (len(target_anchor) == 1 or bool(target_anchor[1]))
                        and (len(alias) == 1 or bool(alias[1]))
                        and all(c == c.strip() and not any(unicode.category(x) == 'Cc' or x in '[]\\' for x in c) for c in components))
                if good:
                    record(raw,target_anchor[0],target_anchor[1] if len(target_anchor)==2 else None,'wiki',absolute)
                else:
                    ln,col=where(absolute)
                    v.add('W_WIKILINK_SYNTAX','Malformed wikilink is preserved literally and creates no relationship.',line=ln,column=col,actual=raw,expected='[[target#optional anchor|optional label]] with nonempty, unpadded components',hint='Remove extra separators, whitespace, brackets, or unsupported escapes; close the link on the same line.')
                i=stop if stop>i else i+1
                continue
            # Literal inline code consumes a matching code span before any links.
            if ch=='`':
                state.pos=i;state.tokens=[]
                backticks(state,False)
                if state.pos>i: i=state.pos;continue
            # Inline math and HTML are preserved conservatively as opaque regions.
            if ch=='$':
                marker='$$' if source.startswith('$$',i) else '$'
                end=source.find(marker,i+len(marker))
                if end>=0:
                    warn_extension(absolute,'inline math');i=end+len(marker);continue
            if source.startswith('%%',i):
                end=source.find('%%',i+2);warn_extension(absolute,'Obsidian comment');i=len(source) if end<0 else end+2;continue
            if ch=='<':
                # CommonMark autolinks are not internal document links.
                state.pos=i;state.tokens=[]
                if autolink(state,False): i=state.pos;continue
                html=re.match(r'</?([A-Za-z][\w:-]*)\b[^>]*>|<!--.*?-->',source[i:],re.S)
                if html:
                    end=i+html.end()
                    if not source.startswith('</',i) and not html.group(0).endswith('/>') and html.group(1):
                        closing=re.search(r'</'+re.escape(html.group(1))+r'\s*>',source[end:],re.I)
                        if closing: end+=closing.end()
                    warn_extension(absolute,'inline HTML');i=end;continue
            if ch in '[!':
                state.pos=i;state.tokens=[]
                matched=md_image(state,False) if ch=='!' else md_link(state,False)
                if matched:
                    end=state.pos
                    if ch=='[':
                        opening=next((t for t in state.tokens if t.type=='link_open'),None)
                        href=opening.attrGet('href') if opening else None
                        if href is not None:
                            u=_parts(href)
                            if u and not u.scheme and not u.netloc and not u.query:
                                target=unquote(u.path)
                                anchor=unquote(u.fragment) if '#' in href else None
                                if target.endswith('.md') or not target and anchor is not None:
                                    record(source[i:end],target,anchor,'markdown',absolute)
                    i=end;continue
            if source.startswith('[!',i) or source.startswith('==',i) or source.startswith('[^',i):
                warn_extension(absolute,'Obsidian inline extension')
            i+=1
    v.structure = build_structure(body=body, canonical=canonical, body_start=canonical_body_offset,
                                  submitted_body_line=submitted_body_line, tokens=tokens,
                                  headings=structural_headings, opaque=protected, eligible=eligible)
    return headings,blocks,links


def _resolve(results, validations):
    # Exclude invalid documents from the current identity/path namespace.
    index={p:r['document'] for p,r in results.items() if r['document'] and not any(d['severity']=='error' for d in r['diagnostics'])}
    stems={}
    for p,d in index.items(): stems.setdefault(p.rsplit('/',1)[-1][:-3],[]).append((p,d))
    for path,result in results.items():
        doc=result['document']
        if doc is None: continue
        v=validations[path]
        for link in doc['links']:
            target=link['target_text'];anchor=link['target_anchor'];matches=[]
            if not target:
                # Self-links remain useful while reporting independent metadata errors.
                matches=[(path,doc)]
            elif link['kind']=='wiki':
                if '/' in target:
                    lookup=target if target.endswith('.md') else target+'.md'
                    if lookup in index: matches=[(lookup,index[lookup])]
                else:
                    stem=target[:-3] if target.endswith('.md') else target
                    matches=stems.get(stem,[])
            else:
                lookup=posixpath.normpath(posixpath.join(posixpath.dirname(path),target))
                if not target.startswith('/') and not lookup.startswith('../') and lookup!='..' and '\\' not in lookup and lookup in index:
                    matches=[(lookup,index[lookup])]
            kw=dict(line=link['line'],column=link['column'],actual=link['raw_link'],field='links['+str(link['ordinal'])+']')
            if len(matches)!=1:
                ambiguous=len(matches)>1
                link['resolution']='ambiguous' if ambiguous else 'unresolved'
                v.add('W_LINK_AMBIGUOUS' if ambiguous else 'W_LINK_UNRESOLVED',
                      'Internal document target matches multiple documents.' if ambiguous else 'Internal document target was not found.',
                      expected='one exact case-sensitive document path or unique filename stem',hint='Use an exact qualified path or a relative Markdown link; check target spelling.',**kw)
                continue
            target_doc=matches[0][1]
            link['target_document_id']=target_doc['metadata'].get('id')
            link['resolution']='resolved'
            if anchor is not None:
                if '#' in anchor or anchor.startswith('^'):
                    link['resolution']='unresolved'
                    v.add('W_EXTENSION_UNSUPPORTED','Nested-heading or block-ID anchors are preserved but unsupported.',expected='one exact plain-text heading',hint='Use a unique ordinary heading anchor.',**kw)
                else:
                    candidates=[h for h in target_doc['headings'] if h['text']==anchor]
                    if len(candidates)!=1 or not candidates[0].get('_plain',True):
                        ambiguous=len(candidates)>1
                        link['resolution']='ambiguous' if ambiguous else 'unresolved'
                        v.add('W_LINK_AMBIGUOUS' if ambiguous else 'W_LINK_UNRESOLVED',
                              'Heading anchor is ambiguous.' if ambiguous else 'Heading anchor is missing or contains inline markup.',
                              expected='one exact heading containing plain inline text',hint='Check the heading text and remove inline markup or duplicate headings.',**kw)
        result['valid']=not any(d['severity']=='error' for d in result['diagnostics'])
    for result in results.values():
        if result['document']:
            for h in result['document']['headings']: h.pop('_plain',None)


def _document(content, path, knowledge_base, domains):
    if isinstance(content,bytes):
        try: content=content.decode('utf-8')
        except UnicodeDecodeError as e:
            v=_Validation(path,'')
            prefix=content[:e.start].decode('utf-8','replace').replace('\r\n','\n').replace('\r','\n')
            v.add('E_ENCODING','Content is not valid UTF-8.',line=prefix.count('\n')+1,column=len(prefix.rsplit('\n',1)[-1])+1,expected='UTF-8 without BOM or NUL',actual=str(e),hint='Save the file as UTF-8.')
            return dict(valid=False,path=path,diagnostics=v.diagnostics,document=None),v
    if not isinstance(content,str): raise TypeError('content must be str or UTF-8 bytes')
    normalized=content.replace('\r\n','\n').replace('\r','\n')
    if not normalized.endswith('\n'): normalized+='\n'
    v=_Validation(path,normalized)
    result=dict(valid=False,path=path,diagnostics=v.diagnostics,document=None)
    _path(v)
    for needle,description in [('\ufeff','byte-order mark'),('\0','NUL character')]:
        offset=normalized.find(needle)
        if offset>=0 and (needle!='\ufeff' or offset==0):
            prefix=normalized[:offset]
            v.add('E_ENCODING',f'Content contains a prohibited {description}.',line=prefix.count('\n')+1,column=len(prefix.rsplit('\n',1)[-1])+1,expected='UTF-8 without BOM or NUL',actual=description,hint=f'Remove the {description}.')
    try: normalized.encode('utf-8')
    except UnicodeEncodeError as e:
        v.add('E_ENCODING','Content contains an invalid Unicode surrogate.',line=1,column=1,expected='Unicode encodable as UTF-8',actual=str(e),hint='Replace the invalid surrogate with a Unicode character.')
        return result,v
    if any(d['code']=='E_ENCODING' for d in v.diagnostics): return result,v
    if normalized!=content:
        v.add('W_NORMALIZED','Line endings were normalized to LF or a final newline was appended.',line=1,column=1,expected='LF line endings and final newline',actual='normalization applied',hint='Save files with LF endings and a final newline for stable authored bytes.')
    parsed=_frontmatter(v)
    if parsed is None: return result,v
    meta,close,lines=parsed
    body=''.join(lines[close+1:])
    base=meta.pop('tribal_base_revision',None)
    transport_line=None
    if 'tribal_base_revision' in v.nodes:
        node=v.nodes['tribal_base_revision']; ln,col=v.positions['tribal_base_revision']
        raw_line=lines[ln-1]
        end_line=node.end_mark.line+2
        # Scalar ending immediately after its last quote shares its start line;
        # block scalars and continued scalars do not occupy one physical line.
        good=(isinstance(node,ScalarNode) and node.style not in ('|','>') and node.start_mark.line==node.end_mark.line and node.start_mark.line+2==ln and _uuid(base) and len(raw_line.encode('utf-8'))<=256)
        if not good:
            v.invalid('tribal_base_revision',base,'a canonical non-nil UUID string on one physical line of at most 256 UTF-8 bytes','E_TRANSPORT')
        else: transport_line=ln-1
    canonical=''.join(line for i,line in enumerate(lines) if i!=transport_line)
    v.limit('canonical_markdown',canonical,MAX_FILE,'UTF-8 bytes',line=1,column=1)
    if not body.strip(): v.add('E_EMPTY_BODY','The Markdown body contains no non-whitespace text.',line=close+2,column=1,expected='nonempty body',actual=body,hint='Add authored prose, table text, or code after frontmatter.')
    _metadata(v,meta,knowledge_base,domains)
    interpreted={k:(value.copy() if isinstance(value,(dict,list)) else value) for k,value in DEFAULTS.items()}
    interpreted.update(meta)
    v.title=meta.get('title')
    canonical_body_offset=len(''.join(line for i,line in enumerate(lines[:close+1]) if i!=transport_line).encode('utf-8'))
    headings,blocks,links=_markdown(v,body,canonical,canonical_body_offset,close+2)
    _contexts_sources(v,meta,headings)
    result['document']=dict(metadata=interpreted,canonical_markdown=canonical,body=body,content_hash=hashlib.sha256(canonical.encode('utf-8')).hexdigest(),base_revision=base,headings=headings,blocks=blocks,links=links)
    result['valid']=not any(d['severity']=='error' for d in v.diagnostics)
    return result,v


def validate_document(content, *, path='note.md', knowledge_base=None, domains=None):
    """Validate one document; external targets remain unresolved warnings."""
    result,v=_document(content,path,knowledge_base,domains)
    _resolve({path:result},{path:v})
    return result


def validate_vault(documents, *, knowledge_base=None, domains=None):
    """Validate a selected in-memory vault and resolve its current links."""
    results={};validations={};ids={};portable={};assignments={}
    if domains is not None: domains=set(domains)
    for path,content in documents.items():
        result,v=_document(content,path,knowledge_base,domains)
        results[path]=result;validations[path]=v
        doc=result['document']
        if not doc: continue
        ident=doc['metadata'].get('id')
        if _uuid(ident): ids.setdefault(ident,[]).append(path)
        portable.setdefault(_portable(path),[]).append(path)
        kb=doc['metadata'].get('knowledge_base')
        if isinstance(kb,str) and KEY.fullmatch(kb): assignments.setdefault(kb,[]).append(path)
    for ident,paths in ids.items():
        if len(paths)>1:
            for path in paths: validations[path].invalid('id',ident,'a document UUID unique in the vault; also used by '+', '.join(p for p in paths if p!=path),'E_IDENTITY_COLLISION')
    for paths in portable.values():
        if len(paths)>1:
            for path in paths: validations[path].invalid('path',path,'a path unique under Unicode 15.1 NFC/full default case folding; collides with '+', '.join(p for p in paths if p!=path),'E_PATH')
    if len(assignments)>1:
        for kb,paths in assignments.items():
            for path in paths: validations[path].invalid('knowledge_base',kb,'the single knowledge-base assignment shared by this vault','E_ASSIGNMENT')
    _resolve(results,validations)
    diagnostics=[d for r in results.values() for d in r['diagnostics']]
    errors=sum(d['severity']=='error' for d in diagnostics)
    warnings=sum(d['severity']=='warning' for d in diagnostics)
    return dict(valid=errors==0,diagnostics=diagnostics,documents=results,summary=dict(files=len(results),errors=errors,warnings=warnings))
