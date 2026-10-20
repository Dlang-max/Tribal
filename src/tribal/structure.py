"""Internal source structure shared by validation, chunking, and context reads.

All ranges are half-open offsets in canonical UTF-8 bytes. Heading anchors are
metadata; a section's source range is its identity, including duplicate headings.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, replace
from itertools import islice
import re


@dataclass(frozen=True)
class SourceRange:
    start_byte: int
    end_byte: int
    kind: str


@dataclass(frozen=True)
class Unit(SourceRange):
    items: tuple[SourceRange, ...] = ()


@dataclass(frozen=True)
class Heading(SourceRange):
    level: int
    text: str
    plain: bool
    root: bool


@dataclass(frozen=True)
class Section:
    start_byte: int
    end_byte: int
    heading_path: tuple[str, ...]
    section_anchor: str | None
    units: tuple[Unit, ...]


@dataclass(frozen=True)
class Structure:
    canonical_bytes: bytes
    body_start_byte: int
    submitted_body_line: int
    body_line_starts: tuple[int, ...]
    headings: tuple[Heading, ...]
    sections: tuple[Section, ...]
    protected_ranges: tuple[SourceRange, ...]
    definitions: tuple[SourceRange, ...]
    eligible_ranges: tuple[SourceRange, ...]

    @property
    def mermaid_ranges(self):
        return tuple(region for region in self.protected_ranges if region.kind == 'mermaid')

    def location(self, byte_offset):
        """Map a canonical body offset to normalized submitted line/column."""
        if not self.body_start_byte <= byte_offset <= len(self.canonical_bytes):
            raise ValueError('offset is outside the canonical body')
        index = bisect_right(self.body_line_starts, byte_offset) - 1
        line_start = self.body_line_starts[index]
        column = len(self.canonical_bytes[line_start:byte_offset].decode('utf-8')) + 1
        return self.submitted_body_line + index, column

    def section_for_range(self, start_byte, end_byte):
        """Return the precise containing section, or None for a crossing range."""
        return next((section for section in self.sections
                     if section.start_byte <= start_byte < end_byte <= section.end_byte), None)


def _attach_gaps(units, start, end):
    """Attach leading source to the first unit and later gaps to predecessors."""
    if not units:
        return (Unit(start, end, 'source'),) if start < end else ()
    attached = []
    for index, unit in enumerate(units):
        a = start if index == 0 else unit.start_byte
        b = units[index + 1].start_byte if index + 1 < len(units) else end
        items = unit.items
        if items:
            items = tuple(SourceRange(a if i == 0 else item.start_byte,
                                     items[i + 1].start_byte if i + 1 < len(items) else b,
                                     'list_item') for i, item in enumerate(items))
        attached.append(replace(unit, start_byte=a, end_byte=b, items=items))
    return tuple(attached)


def build_structure(*, body, canonical, body_start, submitted_body_line,
                    tokens, headings, opaque, eligible):
    """Retain the validator's exact token interpretation without parsing again."""
    source = canonical.encode('utf-8')
    char_starts = [0]
    for match in re.finditer('\n', body):
        char_starts.append(match.end())
    byte_starts = [body_start]
    for line in body.split('\n')[:-1]:
        byte_starts.append(byte_starts[-1] + len(line.encode('utf-8')) + 1)

    def offset(character):
        line = bisect_right(char_starts, character) - 1
        return byte_starts[line] + len(body[char_starts[line]:character].encode('utf-8'))

    def token_range(token, kind):
        return SourceRange(byte_starts[token.map[0]], byte_starts[token.map[1]], kind)

    opaque_kinds = {'math block': 'math', 'footnote definition': 'definition'}
    protected = [SourceRange(offset(a), offset(b), opaque_kinds.get(kind, 'opaque'))
                 for a, b, kind in opaque]
    units = []
    kinds = {'table_open': 'table', 'fence': 'code', 'code_block': 'code',
             'html_block': 'opaque', 'heading_open': 'heading',
             'paragraph_open': 'paragraph', 'bullet_list_open': 'list',
             'ordered_list_open': 'list', 'blockquote_open': 'blockquote',
             'hr': 'thematic_break'}
    for index, token in enumerate(tokens):
        if not token.map:
            continue
        kind = kinds.get(token.type, token.type.removesuffix('_open'))
        if token.type == 'fence' and token.info.split()[:1] == ['mermaid']:
            kind = 'mermaid'
        region = token_range(token, kind)
        if kind in ('table', 'code', 'mermaid', 'opaque', 'blockquote'):
            protected.append(region)
        if token.level != 0 or not (token.nesting == 1 or token.type in ('fence', 'code_block', 'html_block', 'hr')):
            continue
        items = ()
        if kind == 'list':
            immediate = []
            for child in islice(tokens, index + 1, None):
                if child.level == token.level and child.nesting == -1:
                    break
                if child.type == 'list_item_open' and child.level == token.level + 1 and child.map:
                    immediate.append(token_range(child, 'list_item'))
            items = tuple(immediate)
        units.append(Unit(region.start_byte, region.end_byte, kind, items))

    # CommonMark reference definitions are absent from the rendered token stream.
    # Preserve their continuation source, just as masked footnotes are preserved.
    definitions = [region for region in protected if region.kind == 'definition']
    lines = body.split('\n')
    for index, line in enumerate(lines[:-1]):
        if not re.match(r' {0,3}\[(?!\^)[^\]\n]+\]:', line):
            continue
        start = byte_starts[index]
        if any(region.start_byte <= start < region.end_byte for region in protected):
            continue
        end = index + 1
        while end < len(lines) - 1:
            if re.match(r'(?: {4}|\t)', lines[end]):
                end += 1
            elif not lines[end].strip() and end + 1 < len(lines) - 1 and re.match(r'(?: {4}|\t)', lines[end + 1]):
                end += 1
            else:
                break
        definitions.append(SourceRange(start, byte_starts[end], 'definition'))
    protected.extend(region for region in definitions if region not in protected)

    # Containers and their descendants are alternative segmentation levels.
    # Union any crossing protected region before considering packing boundaries.
    candidates = units + [Unit(r.start_byte, r.end_byte, r.kind) for r in protected]
    merged = []
    for unit in sorted(candidates, key=lambda r: (r.start_byte, -r.end_byte)):
        if merged and unit.start_byte < merged[-1].end_byte:
            previous = merged[-1]
            if unit.end_byte > previous.end_byte:
                merged[-1] = Unit(previous.start_byte, unit.end_byte, previous.kind)
        else:
            merged.append(unit)

    counts = Counter(heading.text for heading in headings)
    roots = [heading for heading in headings if heading.root]
    boundaries = [body_start] if not roots or roots[0].start_byte > body_start else []
    boundaries.extend(heading.start_byte for heading in roots)
    root_by_start = {heading.start_byte: heading for heading in roots}
    sections = []
    ancestry = []
    unit_cursor = 0
    for index, start in enumerate(boundaries):
        end = boundaries[index + 1] if index + 1 < len(boundaries) else len(source)
        heading = root_by_start.get(start)
        anchor = None
        if heading:
            while ancestry and ancestry[-1].level >= heading.level:
                ancestry.pop()
            ancestry.append(heading)
            if heading.text and heading.plain and counts[heading.text] == 1:
                anchor = heading.text
        section_units = []
        while unit_cursor < len(merged) and merged[unit_cursor].start_byte < end:
            section_units.append(merged[unit_cursor])
            unit_cursor += 1
        if any(unit.end_byte > end for unit in section_units):
            from .errors import TribalError
            raise TribalError('E_CHUNK_INVARIANT', 'A structural unit crosses a root heading.',
                              hint='Do not publish this layout; report the structural parser failure.')
        sections.append(Section(start, end, tuple(h.text for h in ancestry), anchor,
                                _attach_gaps(section_units, start, end)))
    eligible_ranges = tuple(SourceRange(byte_starts[line], byte_starts[line + 1], 'inline')
                            for line in sorted(eligible))
    return Structure(source, body_start, submitted_body_line, tuple(byte_starts),
                     tuple(headings), tuple(sections), tuple(protected),
                     tuple(definitions), eligible_ranges)


def parse_structure(content, *, path='note.md', knowledge_base=None, domains=None):
    """Validate once and return (ordinary validation result, internal structure)."""
    from .parser import _document, _resolve
    result, validation = _document(content, path, knowledge_base, domains)
    _resolve({path: result}, {path: validation})
    return result, getattr(validation, 'structure', None)
