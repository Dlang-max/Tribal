"""Operator commands for validation, publication, indexing, and retrieval."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

from .errors import TribalError
from .parser import validate_document, validate_vault

IGNORED = {'.git', '.obsidian', '.tribal-staging', '.venv', 'venv', 'env', '.env', 'virtualenv', '__pycache__'}


def _io(path, error):
    return dict(code='E_IO', severity='error', message=f'Cannot read {path}: {error}', path=str(path), line=None, column=None, field=None, expected='a readable file or Tribal vault directory', actual=str(error), hint='Check the path and filesystem permissions.', excerpt=None)


def _text_diagnostic(d):
    location = d.get('path') or 'tribal'
    if d['line'] is not None:
        location += f":{d['line']}:{d['column'] or 1}"
    lines = [f"{location}: {d['severity']} {d['code']}: {d['message']}"]
    for key in ('field', 'expected', 'actual', 'hint', 'excerpt'):
        if d[key] is not None:
            lines.append(f'  {key}: {d[key]}')
    return '\n'.join(lines)


def _collect_documents(path):
    """Read a selected batch without Git probing or implied deletions."""
    documents, errors = {}, []
    if path.is_file():
        try:
            documents[path.name] = path.read_bytes()
        except OSError as error:
            errors.append(_io(path, error))
    elif path.is_dir():
        def onerror(error):
            errors.append(_io(error.filename or path, error))
        for root, dirs, names in os.walk(path, onerror=onerror, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in IGNORED and not (Path(root) / d / 'pyvenv.cfg').is_file() and not (Path(root) / d).is_symlink())
            for name in sorted(names):
                if name.endswith('.md'):
                    filename = Path(root) / name
                    relative = filename.relative_to(path).as_posix()
                    try:
                        documents[relative] = filename.read_bytes()
                    except OSError as error:
                        errors.append(_io(relative, error))
        if not documents and not errors:
            errors.append(_io(path, 'No lowercase .md knowledge documents were found; select a Tribal vault.'))
    else:
        errors.append(_io(path, 'Path does not exist or is not a regular file/directory.'))
    return documents, errors


def _flatten(groups):
    return [key for group in groups for key in group] or None


def _validate(args):
    documents, io_errors = _collect_documents(args.path)
    options = dict(knowledge_base=args.knowledge_base, domains=_flatten(args.domain))
    if args.path.is_file() and documents:
        result = validate_document(next(iter(documents.values())), path=args.path.name, **options)
    elif args.path.is_dir():
        result = validate_vault(documents, **options)
    else:
        result = dict(valid=False, path=str(args.path), diagnostics=[], document=None)
    if io_errors:
        result['valid'] = False
        result['diagnostics'].extend(io_errors)
        if 'summary' in result:
            result['summary']['errors'] += len(io_errors)
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        for diagnostic in result['diagnostics']:
            print(_text_diagnostic(diagnostic))
        if 'summary' in result:
            summary = result['summary']
            print(f"{summary['files']} file(s), {summary['errors']} error(s), {summary['warnings']} warning(s).")
        else:
            errors = sum(d['severity'] == 'error' for d in result['diagnostics'])
            warnings = sum(d['severity'] == 'warning' for d in result['diagnostics'])
            print(f'{args.path}: {errors} error(s), {warnings} warning(s).')
    return 2 if io_errors else 0 if result['valid'] else 1


def _chunk(args):
    from .chunking import chunk_document
    documents, errors = _collect_documents(args.path)
    options = dict(knowledge_base=args.knowledge_base, domains=_flatten(args.domain), revision_id=args.revision_id)
    if args.path.is_file() and documents:
        result = chunk_document(next(iter(documents.values())), path=args.path.name, **options)
        result['diagnostics'].extend(errors)
    else:
        results = {path: chunk_document(content, path=path, **options) for path, content in documents.items()}
        diagnostics = [d for result in results.values() for d in result['diagnostics']] + errors
        result = dict(valid=not errors and all(item['valid'] for item in results.values()), path=str(args.path), diagnostics=diagnostics, documents=results,
                      summary=dict(files=len(results), chunks=sum(len(item['chunks']) for item in results.values()), errors=sum(d['severity'] == 'error' for d in diagnostics), warnings=sum(d['severity'] == 'warning' for d in diagnostics)))
    if errors:
        result['valid'] = False
    return result, 2 if errors else 0 if result['valid'] else 1


def _database():
    user = os.environ.get('TRIBAL_DB_USER')
    if not user:
        raise TribalError('E_ARGUMENT', 'Database user is not configured.', field='TRIBAL_DB_USER', hint='Set TRIBAL_DB_USER and the other TRIBAL_DB_* connection variables before running this command.')
    try:
        port = int(os.environ.get('TRIBAL_DB_PORT', '3306'))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise TribalError('E_ARGUMENT', 'Database port must be an integer from 1 to 65535.', field='TRIBAL_DB_PORT', hint='Set TRIBAL_DB_PORT to the MySQL TCP port.') from None
    from .storage import Database
    return Database(host=os.environ.get('TRIBAL_DB_HOST', '127.0.0.1'), port=port, user=user, password=os.environ.get('TRIBAL_DB_PASSWORD', ''), database=os.environ.get('TRIBAL_DB_NAME', 'tribal'))


def _provider():
    if not os.environ.get('OPENAI_API_KEY'):
        raise TribalError('E_ARGUMENT', 'OpenAI credentials are not configured.', field='OPENAI_API_KEY', hint='Set OPENAI_API_KEY before running an embedding worker or a new semantic/hybrid search; lexical search does not require it.')
    from .embeddings import OpenAIProvider
    return OpenAIProvider()


def _configuration(value):
    if value is None:
        return None
    try:
        result = json.loads(value)
        if not isinstance(result, dict):
            raise ValueError
        # Reject Python's permissive NaN/Infinity JSON extensions as well.
        json.dumps(result, allow_nan=False)
    except (ValueError, TypeError):
        raise TribalError('E_ARGUMENT', 'Profile configuration must be a JSON object with finite values.', field='configuration', hint='Pass --configuration followed by a valid JSON object; omit it to use the default profile configuration.') from None
    return result


def _run_operation(args, db):
    if args.command == 'db':
        from .storage import migrate
        return migrate(db)
    if args.command == 'kb':
        from .storage import ensure_knowledge_base
        return ensure_knowledge_base(db, key=args.key, name=args.name, description=args.description)
    if args.command == 'domain':
        from .storage import ensure_domain
        return ensure_domain(db, knowledge_base=args.knowledge_base, key=args.key, name=args.name, description=args.description)
    if args.command == 'profile':
        if args.action == 'ensure':
            from .storage import ensure_profile
            return ensure_profile(db, key=args.key, provider=args.provider, model=args.model, dimensions=args.dimensions, configuration=_configuration(args.configuration))
        from .embeddings import activate_profile
        return activate_profile(db, knowledge_base=args.knowledge_base, profile_id=args.profile_id, allow_partial=args.allow_partial)
    if args.command == 'ingest':
        from .publication import ingest_vault
        documents, errors = _collect_documents(args.path)
        if errors:
            return dict(ok=False, diagnostics=errors)
        return ingest_vault(db, documents, knowledge_base=args.knowledge_base, author_type=args.author_type, author_id=args.author_id, change_summary=args.change_summary)
    if args.command == 'rechunk':
        from .publication import rechunk_revision
        return rechunk_revision(db, knowledge_base=args.knowledge_base, document_id=args.document_id, revision_id=args.revision_id)
    if args.command == 'index':
        from .embeddings import backfill_embeddings, indexing_status, retry_embeddings
        options = dict(knowledge_base=args.knowledge_base, profile_id=args.profile_id)
        if args.action == 'backfill':
            return backfill_embeddings(db, **options)
        if args.action == 'retry':
            return retry_embeddings(db, **options)
        return indexing_status(db, **options)
    from .retrieval import read_context, read_document, search
    if args.command == 'search':
        provider = _provider() if args.mode != 'lexical' and args.cursor is None else None
        return search(db, args.query, knowledge_base=args.knowledge_base, provider=provider, mode=args.mode, lexical_mode=args.lexical_mode, domains=_flatten(args.domain), statuses=_flatten(args.status), include_deleted=args.include_deleted, limit=args.limit, cursor=args.cursor)
    if args.command == 'read':
        return read_document(db, knowledge_base=args.knowledge_base, document_id=args.document_id, revision_id=args.revision_id, start_byte=args.start_byte, end_byte=args.end_byte)
    return read_context(db, knowledge_base=args.knowledge_base, document_id=args.document_id, revision_id=args.revision_id, chunk_id=args.chunk_id, budget_bytes=args.budget_bytes)


def _emit(result, *, as_json, json_lines=False):
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=None if json_lines else 2, allow_nan=False), flush=True)
        return
    for diagnostic in result.get('diagnostics', []):
        print(_text_diagnostic(diagnostic))
    for key, value in result.items():
        if key in {'diagnostics', 'ok', 'valid'}:
            continue
        if key == 'content':
            print(value, end='' if value.endswith('\n') else '\n')
        elif value is not None:
            rendered = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) if isinstance(value, (dict, list)) else str(value)
            print(f'{key}: {rendered}')
    if not any(key not in {'diagnostics', 'ok', 'valid'} for key in result):
        print('Done.' if result.get('ok', result.get('valid', False)) else 'Operation failed.')
    sys.stdout.flush()


def _worker(args, db):
    from .embeddings import run_worker_once
    provider = _provider()
    try:
        while True:
            result = run_worker_once(db, provider, knowledge_base=args.knowledge_base)
            _emit(result, as_json=args.as_json, json_lines=not args.once)
            if args.once:
                return 0 if result['ok'] else 2
            if result['state'] in {'idle', 'queued'}:
                time.sleep(1)
    except KeyboardInterrupt:
        return 0


def _parser():
    parser = argparse.ArgumentParser(prog='tribal', description='Validate, publish, index, and retrieve Tribal Markdown knowledge.')
    commands = parser.add_subparsers(dest='command', required=True)

    def leaf(parent, name, help):
        command = parent.add_parser(name, help=help)
        command.add_argument('--json', action='store_true', dest='as_json')
        return command

    def group(name, help):
        return commands.add_parser(name, help=help).add_subparsers(dest='action', required=True)

    def knowledge_base(command, required=True):
        command.add_argument('--knowledge-base', required=required)

    def domains(command):
        command.add_argument('--domain', nargs='+', action='append', default=[])

    for name in ('validate', 'chunk'):
        command = leaf(commands, name, f'{name} a note or vault directory')
        command.add_argument('path', type=Path)
        knowledge_base(command, required=False)
        domains(command)
        if name == 'chunk':
            command.add_argument('--revision-id')
    leaf(group('db', 'database migrations'), 'migrate', 'apply versioned database migrations')
    for name in ('kb', 'domain'):
        command = leaf(group(name, f'{name} registry'), 'ensure', f'create or verify a {name} registry entry')
        command.add_argument('key')
        command.add_argument('--name', required=True)
        command.add_argument('--description')
        if name == 'domain':
            knowledge_base(command)
    command = leaf(commands, 'ingest', 'atomically publish a note or vault batch')
    command.add_argument('path', type=Path)
    knowledge_base(command)
    command.add_argument('--author-type', choices=('human', 'agent', 'system'), default='human')
    command.add_argument('--author-id', default='cli')
    command.add_argument('--change-summary')
    command = leaf(commands, 'rechunk', 'explicitly replace one revision chunk set')
    command.add_argument('document_id')
    knowledge_base(command)
    command.add_argument('--revision-id')
    profiles = group('profile', 'immutable embedding profiles')
    command = leaf(profiles, 'ensure', 'create or verify an embedding profile')
    command.add_argument('--key', default='openai-text-embedding-3-small-v1')
    command.add_argument('--provider', choices=('openai',), default='openai')
    command.add_argument('--model', default='text-embedding-3-small')
    command.add_argument('--dimensions', type=int, default=1536)
    command.add_argument('--configuration')
    command = leaf(profiles, 'activate', 'activate a profile after checking indexing coverage')
    command.add_argument('profile_id')
    knowledge_base(command)
    command.add_argument('--allow-partial', action='store_true')
    index = group('index', 'embedding queue and indexing readiness')
    for name in ('backfill', 'retry', 'status'):
        command = leaf(index, name, f'{name} indexing work for current chunks')
        knowledge_base(command)
        command.add_argument('--profile-id')
    command = leaf(index, 'worker', 'process durable embedding jobs')
    knowledge_base(command, required=False)
    command.add_argument('--once', action='store_true')
    command = leaf(commands, 'search', 'search current eligible knowledge chunks')
    command.add_argument('query')
    knowledge_base(command)
    command.add_argument('--mode', choices=('semantic', 'lexical', 'hybrid'), default='semantic')
    command.add_argument('--lexical-mode', choices=('fulltext', 'literal'), default='fulltext')
    domains(command)
    command.add_argument('--status', nargs='+', action='append', default=[], choices=('active', 'superseded', 'archived'))
    command.add_argument('--include-deleted', action='store_true')
    command.add_argument('--limit', type=int, default=20)
    command.add_argument('--cursor')
    command = leaf(commands, 'read', 'read canonical Markdown from a pinned revision')
    command.add_argument('document_id')
    knowledge_base(command)
    command.add_argument('--revision-id')
    command.add_argument('--start-byte', type=int)
    command.add_argument('--end-byte', type=int)
    command = leaf(commands, 'context', 'read complete chunks and diagrams from the matched section')
    command.add_argument('document_id')
    command.add_argument('revision_id')
    command.add_argument('chunk_id', type=int)
    knowledge_base(command)
    command.add_argument('--budget-bytes', type=int, default=65536)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.command == 'validate':
        return _validate(args)
    try:
        if args.command == 'chunk':
            result, status = _chunk(args)
        else:
            db = _database()
            try:
                if args.command == 'index' and args.action == 'worker':
                    return _worker(args, db)
                result = _run_operation(args, db)
            finally:
                db.close()
            status = 0 if result['ok'] else 2 if any(d['code'] == 'E_IO' for d in result['diagnostics']) else 1
    except TribalError as error:
        result, status = error.as_dict(), 2
    _emit(result, as_json=args.as_json)
    return status
