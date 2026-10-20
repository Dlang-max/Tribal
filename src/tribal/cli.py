"""Command line entry point for the format-only validator."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

from .parser import validate_document, validate_vault

IGNORED = {'.git', '.obsidian', '.tribal-staging', '.venv', 'venv', 'env', '.env', 'virtualenv', '__pycache__'}


def _io(path, error):
    return dict(code='E_IO',severity='error',message=f'Cannot read {path}: {error}',path=str(path),line=None,column=None,field=None,expected='a readable file or Tribal vault directory',actual=str(error),hint='Check the path and filesystem permissions.',excerpt=None)


def _text_diagnostic(d):
    location=d['path']
    if d['line'] is not None: location+=f":{d['line']}:{d['column'] or 1}"
    lines=[f"{location}: {d['severity']} {d['code']}: {d['message']}"]
    for key in ('field','expected','actual','hint','excerpt'):
        if d[key] is not None: lines.append(f'  {key}: {d[key]}')
    return '\n'.join(lines)


def main(argv=None):
    parser=argparse.ArgumentParser(prog='tribal',description='Validate Tribal Markdown v1 without executing content or accessing external evidence.')
    sub=parser.add_subparsers(dest='command',required=True)
    validate=sub.add_parser('validate',help='validate a file or an entire Tribal vault')
    validate.add_argument('path',type=Path)
    validate.add_argument('--json',action='store_true',dest='as_json')
    validate.add_argument('--knowledge-base')
    validate.add_argument('--domain',nargs='+',action='append',default=[])
    args=parser.parse_args(argv)
    path=args.path
    domains=[key for group in args.domain for key in group] or None
    io_errors=[]
    result=None
    if path.is_file():
        try:
            result=validate_document(path.read_bytes(),path=path.name,knowledge_base=args.knowledge_base,domains=domains)
        except OSError as e: io_errors.append(_io(path,e))
    elif path.is_dir():
        documents={}
        def onerror(error): io_errors.append(_io(error.filename or path,error))
        for root,dirs,names in os.walk(path,onerror=onerror,followlinks=False):
            # A virtual environment may have an arbitrary directory name.
            dirs[:]=sorted(d for d in dirs if d not in IGNORED and not (Path(root)/d/'pyvenv.cfg').is_file() and not (Path(root)/d).is_symlink())
            for name in sorted(names):
                if name.endswith('.md'):
                    filename=Path(root)/name
                    relative=filename.relative_to(path).as_posix()
                    try: documents[relative]=filename.read_bytes()
                    except OSError as e: io_errors.append(_io(relative,e))
        result=validate_vault(documents,knowledge_base=args.knowledge_base,domains=domains)
        if not documents and not io_errors:
            io_errors.append(_io(path,'No lowercase .md knowledge documents were found; select a Tribal vault.'))
    else:
        io_errors.append(_io(path,'Path does not exist or is not a regular file/directory.'))
    if result is None:
        result=dict(valid=False,path=str(path),diagnostics=[],document=None)
    if io_errors:
        result['valid']=False
        result['diagnostics'].extend(io_errors)
        if 'summary' in result: result['summary']['errors']+=len(io_errors)
    if args.as_json:
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    else:
        for diagnostic in result['diagnostics']: print(_text_diagnostic(diagnostic))
        if 'summary' in result:
            s=result['summary']; print(f"{s['files']} file(s), {s['errors']} error(s), {s['warnings']} warning(s).")
        else:
            errors=sum(d['severity']=='error' for d in result['diagnostics'])
            warnings=sum(d['severity']=='warning' for d in result['diagnostics'])
            print(f'{path}: {errors} error(s), {warnings} warning(s).')
    return 2 if io_errors else 0 if result['valid'] else 1
