"""Validate complete project vaults and expose revision-safe KB reads and publication."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import math
from pathlib import Path
import re
import sys
import tempfile
import uuid

import yaml

from .embeddings import validate_vectors

TYPES = {"project", "repository", "branch", "commit", "merge", "push", "finding",
         "insight", "decision", "handoff", "guide"}
ROOT = Path(__file__).resolve().parents[4]


# Load the existing standalone validator without moving or changing its rules.
def _validator(path):
    name = "_tribal_note_validator_" + hashlib.sha256(str(path).encode()).hexdigest()[:12]
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


# Parse metadata from source already checked by the native validator.
def _metadata(markdown):
    return yaml.safe_load(markdown.partition("\n---\n")[0].removeprefix("---\n"))


# Identify one stable directed graph edge independently of its link spelling.
def _edge(source, target):
    return {"id": hashlib.sha256((source + "\0" + target).encode()).hexdigest(),
            "source": source, "target": target}


# Return a structured batch outcome with the shared public fields.
def _result(status, message, notes=None, issues=None):
    return {"status": status, "message": message, "notes": notes or [], "issues": issues or []}


class KnowledgeBaseService:
    # Bind one project to its storage adapters, structural validator, and optional indexer.
    def __init__(self, project_id, object_store, catalog, embedding_client=None,
                 spec_root=None, validator_path=None):
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("project_id must be nonblank")
        self.project_id = project_id
        self.object_store = object_store
        self.catalog = catalog
        self.embedding_client = embedding_client
        self.spec_root = Path(spec_root) if spec_root else ROOT / "agent-knowledge-base/specs/v1"
        validator_path = Path(validator_path) if validator_path else (
            ROOT / "agent-knowledge-base/validation/v1/validate_knowledge_base_notes.py")
        self.validator = _validator(validator_path)
        self._index_tasks = set()

    # Rehydrate source Markdown exclusively from current immutable object references.
    def _snapshot(self):
        notes = self.catalog.list_notes(self.project_id)
        return [(note, self.object_store.get(note["object_key"]).decode("utf-8")) for note in notes]

    # Extract resolved native wikilinks while respecting code and comment masking.
    def _links(self, note_id, markdown, manifests):
        by_path = {note["path"][:-3]: note["id"] for note in manifests}
        body = markdown.partition("\n---\n")[2]
        visible = self.validator._visible_markdown(body)
        links = [match[1] for match in self.validator.WIKILINK.finditer(visible)]
        metadata = _metadata(markdown)
        for key in self.validator.LINK_FIELDS:
            value = metadata.get(key)
            match = self.validator.WIKILINK.fullmatch(value) if isinstance(value, str) else None
            if match:
                links.append(match[1])
        targets = set()
        for link in links:
            path, _ = self.validator._link_parts(link)
            if path in by_path and by_path[path] != note_id:
                targets.add(by_path[path])
        return [_edge(note_id, target) for target in sorted(targets)]

    # Read an exact note revision with its resolved outgoing graph links.
    async def read_note(self, note_id: str) -> dict:
        snapshot = await asyncio.to_thread(self._snapshot)
        manifests = [note for note, _ in snapshot]
        for note, markdown in snapshot:
            if note["id"] == note_id:
                return {key: note[key] for key in ("id", "title", "type", "path", "revision")} | {
                    "markdown": markdown, "links": self._links(note_id, markdown, manifests)}
        raise KeyError(f"Note not found: {note_id}")

    # Permit graph traversal only along a link present in the source note.
    async def follow_link(self, source_id: str, target_id: str) -> dict:
        source = await self.read_note(source_id)
        if not any(link["target"] == target_id for link in source["links"]):
            raise KeyError(f"No link from {source_id} to {target_id}")
        return await self.read_note(target_id)

    # Return the project graph including archived history as valid link targets.
    async def graph(self) -> dict:
        snapshot = await asyncio.to_thread(self._snapshot)
        manifests = [note for note, _ in snapshot]
        return {"project_id": self.project_id,
                "nodes": [{key: note[key] for key in ("id", "title", "type", "path")}
                          for note in sorted(manifests, key=lambda n: n["id"])],
                "edges": [edge for note, text in sorted(snapshot, key=lambda n: n[0]["id"])
                          for edge in self._links(note["id"], text, manifests)]}

    # Return common and type-specific specification text from a closed filename allowlist.
    async def get_note_spec(self, note_type: str) -> str:
        if not isinstance(note_type, str) or note_type not in TYPES:
            raise ValueError(f"Unknown note type: {note_type}")
        common, specific = await asyncio.gather(
            asyncio.to_thread((self.spec_root / "common-note-format.md").read_text),
            asyncio.to_thread((self.spec_root / f"{note_type}-note.md").read_text))
        return common + "\n\n" + specific

    # Resolve a successful prior publication without rerunning its changes.
    async def get_request_result(self, request_id: str, request_hash: str) -> dict | None:
        return await asyncio.to_thread(self.catalog.get_request_result, self.project_id,
                                       request_id, request_hash)

    # Save a final no-change curator outcome under a project-scoped replay key.
    async def remember_request_result(self, request_id: str, request_hash: str, result: dict) -> None:
        await asyncio.to_thread(self.catalog.remember_request_result, self.project_id,
                                request_id, request_hash, result)

    # Check change shape and paths before writing any proposed file to disk.
    def _input_issues(self, changes):
        if not isinstance(changes, list):
            return [{"path": ".", "code": "change.input", "message": "changes must be a list"}]
        issues = []
        seen = set()
        for change in changes:
            if not isinstance(change, dict):
                issues.append({"path": ".", "code": "change.input", "message": "change must be an object"})
                continue
            path = change.get("path")
            problem = (self.validator._path_problem(path) if isinstance(path, str)
                       else "path must be a string")
            if not problem and not path.endswith(".md"):
                problem = "path must end with .md"
            if not problem and ".obsidian" in path.split("/"):
                problem = "notes cannot be hidden inside .obsidian"
            if problem:
                issues.append({"path": str(path), "code": "file.path", "message": problem})
            elif path in seen:
                issues.append({"path": path, "code": "change.duplicate", "message": "path occurs twice"})
            seen.add(path if isinstance(path, str) else None)
            action = change.get("action")
            if not isinstance(action, str) or action not in {"create", "update", "archive"}:
                issues.append({"path": str(path), "code": "change.action", "message": "unknown action"})
            if isinstance(action, str) and action in {"create", "update"} and not isinstance(change.get("markdown"), str):
                issues.append({"path": str(path), "code": "change.markdown", "message": "markdown must be text"})
            revision = change.get("expected_revision")
            if isinstance(action, str) and action in {"update", "archive"} and (type(revision) is not int or revision < 1):
                issues.append({"path": str(path), "code": "change.revision", "message": "positive expected_revision required"})
        return issues

    # Validate the full proposed snapshot under the native Markdown and graph rules.
    def _validate(self, proposed):
        collisions = []
        for path in proposed:
            parts = path.split("/")
            if any("/".join(parts[:index]) in proposed for index in range(1, len(parts))):
                collisions.append({"path": path, "code": "file.path_conflict",
                                   "message": "A parent path is already a Markdown file"})
        if collisions:
            return collisions
        with tempfile.TemporaryDirectory(prefix="tribal-vault-") as directory:
            root = Path(directory)
            for path, markdown in proposed.items():
                file = root / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(markdown.encode("utf-8"))
            return [asdict(issue) for issue in self.validator.validate_vault(
                root, expected_project_id=self.project_id)]

    # Replace lifecycle scalar spans while preserving other valid YAML and source formatting.
    def _archive(self, markdown):
        header, separator, body = markdown.partition("\n---\n")
        frontmatter = header.removeprefix("---\n")
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        replacements = []
        for key, value in yaml.compose(frontmatter).value:
            if key.value in {"status", "updated_at"}:
                text = "archived" if key.value == "status" else f'"{now}"'
                if frontmatter[value.start_mark.index:value.end_mark.index].endswith("\n"):
                    text += "\n"
                replacements.append((value.start_mark.index, value.end_mark.index, text))
        for start, end, text in sorted(replacements, reverse=True):
            frontmatter = frontmatter[:start] + text + frontmatter[end:]
        return "---\n" + frontmatter + separator + body

    # Coordinate revision checks, whole-vault validation, immutable uploads, and SQL publication.
    def _publish(self, changes, request_id, request_hash):
        with self.catalog.publication(self.project_id) as transaction:
            if request_id is not None:
                receipt = transaction.get_request_result(request_id, request_hash)
                if receipt is not None:
                    return receipt, []
            current = {note["path"]: note for note in transaction.list_notes()}
            source = {path: self.object_store.get(note["object_key"]).decode("utf-8")
                      for path, note in current.items()}
            proposed = dict(source)
            for change in changes:
                path, action = change["path"], change["action"]
                old = current.get(path)
                if (action == "create" and old is not None) or (action != "create" and
                        (old is None or old["revision"] != change["expected_revision"])):
                    return _result("conflict", f"Revision or create collision at {path}"), []
                if action == "archive":
                    proposed[path] = self._archive(source[path])
                else:
                    proposed[path] = change["markdown"]
            if not changes:
                return _result("unchanged", "No changes requested"), []
            issues = self._validate(proposed)
            if issues:
                return _result("invalid", "Proposed vault failed structural validation", issues=issues), []
            staged = []
            for change in changes:
                path, action = change["path"], change["action"]
                text = proposed[path]
                old = current.get(path)
                metadata = _metadata(text)
                if old is not None and metadata["id"] != old["id"]:
                    return _result("conflict", f"Stable note identity cannot change at {path}"), []
                if old is not None and metadata["created_at"] != _metadata(source[path])["created_at"]:
                    return _result("conflict", f"Original creation time cannot change at {path}"), []
                if old is not None and source[path] == text:
                    continue
                if action == "create" and any(n["id"] == metadata["id"] for n in current.values()):
                    return _result("conflict", f"Note ID already exists at {path}"), []
                note = {key: metadata[key] for key in ("id", "title", "type", "status")}
                note.update(path=path, revision=old["revision"] + 1 if old else 1,
                            content_hash=hashlib.sha256(text.encode()).hexdigest(),
                            object_key=f"projects/{hashlib.sha256(self.project_id.encode()).hexdigest()}/"
                                       f"versions/{uuid.uuid4().hex}.md")
                staged.append((note, text, {"path": path, "action": {
                    "create": "created", "update": "updated", "archive": "archived"}[action]}))
            for note, text, _ in staged:
                self.object_store.put(note["object_key"], text.encode("utf-8"))
            for note, _, _ in staged:
                transaction.put_note(note)
            outcome = _result("updated" if staged else "unchanged",
                              "Published validated notes" if staged else "Notes already match",
                              notes=[public for _, _, public in staged])
            # Only saved changes finalize here; the runtime records final no-change outcomes.
            if staged and request_id is not None:
                transaction.remember_request_result(request_id, request_hash, outcome)
            return outcome, [(note, text) for note, text, _ in staged]

    # Apply one atomic validated batch and start optional indexing after publication.
    async def apply_changes(self, changes: list[dict], *, request_id=None, request_hash=None) -> dict:
        if (request_id is None) != (request_hash is None):
            raise ValueError("request_id and request_hash must be provided together")
        if request_id is not None:
            receipt = await self.get_request_result(request_id, request_hash)
            if receipt is not None:
                return receipt
        issues = self._input_issues(changes)
        if issues:
            return _result("invalid", "Malformed changes", issues=issues)
        outcome, published = await asyncio.to_thread(self._publish, changes, request_id, request_hash)
        for note, text in published:
            task = asyncio.create_task(self._index(note, text))
            self._index_tasks.add(task)
            task.add_done_callback(self._index_tasks.discard)
        return outcome

    # Build an overview and bounded heading/content chunks without touching source text.
    def _chunks(self, note, markdown):
        body = markdown.split("\n---\n", 1)[1]
        sections = re.split(r"(?m)^(?=##?\s)", body)
        pieces = [("Overview", note["title"] + "\n" + body[:2000])]
        for section in sections:
            if not section.strip():
                continue
            heading = section.splitlines()[0].lstrip("# ")
            for offset in range(0, len(section), 4000):
                pieces.append((heading, section[offset:offset + 4000]))
        return [{"note_id": note["id"], "revision": note["revision"], "position": position,
                 "heading": heading, "text": text, "content_hash": hashlib.sha256(text.encode()).hexdigest(),
                 "model": None, "dimensions": None, "vector": None}
                for position, (heading, text) in enumerate(pieces)]

    # Attach lexical chunks first and discard failed or stale optional vector results.
    async def _index(self, note, markdown):
        try:
            chunks = self._chunks(note, markdown)
            attached = await asyncio.to_thread(self.catalog.replace_chunks, self.project_id,
                                               note["id"], note["revision"], chunks)
            client = self.embedding_client
            if not attached or client is None or not getattr(client, "available", True):
                return
            vectors = validate_vectors(await client.embed([chunk["text"] for chunk in chunks]),
                                       len(chunks), client.dimensions)
            enriched = [chunk | {"model": client.model, "dimensions": client.dimensions,
                                  "vector": vector} for chunk, vector in zip(chunks, vectors)]
            await asyncio.to_thread(self.catalog.replace_chunks, self.project_id,
                                    note["id"], note["revision"], enriched)
        except Exception:
            # Optional index/provider failures leave published Markdown fully readable.
            return

    # Await outstanding derived indexing when shutting down or synchronizing callers.
    async def drain_indexing(self):
        while self._index_tasks:
            tasks = tuple(self._index_tasks)
            await asyncio.gather(*tasks, return_exceptions=True)
            self._index_tasks.difference_update(tasks)

    # Rank active project notes lexically and add only fresh compatible vector similarities.
    async def search_notes(self, query: str, limit: int = 10) -> list[dict]:
        if not isinstance(query, str) or not query.strip() or limit <= 0:
            return []
        snapshot = await asyncio.to_thread(self._snapshot)
        active = {note["id"]: (note, text) for note, text in snapshot if note["status"] == "active"}
        terms = re.findall(r"\w+", query.casefold())
        scores = {note_id: sum(text.casefold().count(term) + 3 * note["title"].casefold().count(term)
                               for term in terms) for note_id, (note, text) in active.items()}
        client = self.embedding_client
        if client is not None and getattr(client, "available", True):
            try:
                vector = validate_vectors(await client.embed([query]), 1, client.dimensions)[0]
                norm = math.sqrt(sum(value * value for value in vector))
                chunks = await asyncio.to_thread(self.catalog.list_chunks, self.project_id)
                for chunk in chunks:
                    item = active.get(chunk["note_id"])
                    if item is None or chunk["revision"] != item[0]["revision"] or (
                            chunk.get("model") != client.model or chunk.get("dimensions") != client.dimensions):
                        continue
                    candidate = validate_vectors([chunk.get("vector")], 1, client.dimensions)[0]
                    other_norm = math.sqrt(sum(value * value for value in candidate))
                    similarity = sum(a * b for a, b in zip(vector, candidate)) / (norm * other_norm) if norm and other_norm else 0
                    scores[chunk["note_id"]] = max(scores[chunk["note_id"]], max(0, similarity))
            except Exception:
                pass
        results = []
        for note_id in sorted(active, key=lambda key: (-scores[key], active[key][0]["path"])):
            if scores[note_id] <= 0:
                continue
            note, markdown = active[note_id]
            body = markdown.split("\n---\n", 1)[1]
            results.append({key: note[key] for key in ("id", "title", "path")} | {"excerpt": body[:400]})
            if len(results) >= min(limit, 100):
                break
        return results
