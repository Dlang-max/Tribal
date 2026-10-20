"""Deterministic source-preserving Markdown chunk preview."""
from __future__ import annotations

from .errors import TribalError
from .structure import parse_structure

CHUNKER_VERSION = 'tribal-structure-bytes-v1'
TARGET_BYTES = 4096


def _invariant(message, path):
    raise TribalError('E_CHUNK_INVARIANT', message, path=path,
                     hint='Do not publish this layout; report the source structure failure.')


def chunk_document(content, *, path='note.md', revision_id=None,
                   knowledge_base=None, domains=None):
    """Validate and partition canonical body bytes, without persistence or I/O."""
    validation, structure = parse_structure(content, path=path,
                                             knowledge_base=knowledge_base, domains=domains)
    document = validation['document']
    result = dict(valid=validation['valid'], path=path,
                  diagnostics=list(validation['diagnostics']),
                  document_id=document['metadata'].get('id') if document else None,
                  revision_id=revision_id,
                  content_hash=document['content_hash'] if document else None,
                  chunker_version=CHUNKER_VERSION,
                  body_start_byte=structure.body_start_byte if structure else None,
                  chunks=[])
    if not result['valid']:
        return result
    if structure is None:
        _invariant('Validated document has no shared source structure.', path)
    source = structure.canonical_bytes

    def emit(start, end, section):
        if not structure.body_start_byte <= start < end <= len(source):
            _invariant('Chunk range is outside the canonical body.', path)
        try:
            text = source[start:end].decode('utf-8')
        except UnicodeDecodeError:
            _invariant('Chunk boundary divides a UTF-8 character.', path)
        result['chunks'].append(dict(revision_id=revision_id, ordinal=len(result['chunks']),
                                     heading_path=list(section.heading_path),
                                     section_anchor=section.section_anchor,
                                     start_byte=start, end_byte=end, content=text,
                                     chunker_version=CHUNKER_VERSION))

    def warn(unit):
        line, column = structure.location(unit.start_byte)
        result['diagnostics'].append(dict(
            code='W_OVERSIZED_BLOCK', severity='warning',
            message='A complete source unit exceeds the 4,096-byte soft target.',
            path=path, line=line, column=column, field=None, expected=TARGET_BYTES,
            actual=dict(start_byte=unit.start_byte, end_byte=unit.end_byte,
                        bytes=unit.end_byte-unit.start_byte, unit_kind=unit.kind),
            hint='Keep the preserved unit, or edit the authored source to create smaller complete units.',
            excerpt=source[unit.start_byte:unit.end_byte].decode('utf-8').split('\n', 1)[0][:240]))

    for section in structure.sections:
        units = []
        for unit in section.units:
            if unit.kind == 'list' and unit.end_byte-unit.start_byte > TARGET_BYTES and unit.items:
                units.extend(unit.items)
            else:
                units.append(unit)
        pending_start = pending_end = None
        for unit in units:
            size = unit.end_byte-unit.start_byte
            if size > TARGET_BYTES:
                if pending_start is not None:
                    emit(pending_start, pending_end, section)
                    pending_start = pending_end = None
                emit(unit.start_byte, unit.end_byte, section)
                warn(unit)
            elif pending_start is not None and unit.end_byte-pending_start > TARGET_BYTES:
                emit(pending_start, pending_end, section)
                pending_start, pending_end = unit.start_byte, unit.end_byte
            else:
                if pending_start is None:
                    pending_start = unit.start_byte
                pending_end = unit.end_byte
        if pending_start is not None:
            emit(pending_start, pending_end, section)

    cursor = structure.body_start_byte
    for chunk in result['chunks']:
        if chunk['start_byte'] != cursor or chunk['content'].encode('utf-8') != source[cursor:chunk['end_byte']]:
            _invariant('Chunks do not form an exact contiguous source partition.', path)
        cursor = chunk['end_byte']
    if cursor != len(source) or ''.join(c['content'] for c in result['chunks']) != document['body']:
        _invariant('Chunks do not reconstruct the complete canonical body.', path)
    return result
