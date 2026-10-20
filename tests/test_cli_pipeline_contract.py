"""Operator CLI checks at public subprocess and real database boundaries."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid

import pytest

from acceptance_helpers import diagnostic_codes, note


def cli(*args, env=None):
    return subprocess.run([sys.executable, "-m", "tribal", *map(str, args)],
                          capture_output=True, text=True, env=env, timeout=30)


@pytest.mark.parametrize("command", [
    ["chunk"], ["db", "migrate"], ["kb", "ensure"], ["domain", "ensure"],
    ["profile", "ensure"], ["profile", "activate"], ["ingest"], ["rechunk"],
    ["index", "backfill"], ["index", "retry"], ["index", "worker"], ["index", "status"],
    ["search"], ["read"], ["context"], ["delete"], ["restore"],
])
def test_every_frozen_leaf_command_exposes_json_help(command):
    result = cli(*command, "--help")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--json" in result.stdout


def test_chunk_json_matches_public_library_and_preserves_warning_success(tmp_path):
    from tribal import chunk_document
    path = tmp_path / "warning.md"
    content = note("[[Missing]]\n")
    path.write_text(content, encoding="utf-8")
    result = cli("chunk", path, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    response = json.loads(result.stdout)
    assert response == chunk_document(content, path="warning.md")
    assert "W_LINK_UNRESOLVED" in diagnostic_codes(response)


def test_chunk_validation_failure_is_actionable_in_json_and_text(tmp_path):
    path = tmp_path / "bad.md"
    path.write_text(note(kind="wrong"), encoding="utf-8")
    result = cli("chunk", path, "--json")
    assert result.returncode == 1
    response = json.loads(result.stdout)
    assert response["valid"] is False and response["chunks"] == []
    assert "E_FIELD_TYPE" in diagnostic_codes(response)
    result = cli("chunk", path)
    assert result.returncode == 1
    assert "E_FIELD_TYPE" in result.stdout + result.stderr
    assert "bad.md" in result.stdout + result.stderr
    assert "kind" in result.stdout + result.stderr


def test_chunk_missing_file_is_safe_operational_error(tmp_path):
    result = cli("chunk", tmp_path / "absent.md", "--json")
    assert result.returncode == 2
    response = json.loads(result.stdout)
    assert response.get("ok", response.get("valid")) is False
    assert "E_IO" in diagnostic_codes(response)


def test_malformed_database_port_produces_safe_json_diagnostic():
    env = os.environ.copy()
    env.update(TRIBAL_DB_PORT="not-a-number", TRIBAL_DB_USER="test", TRIBAL_DB_PASSWORD="private-password-sentinel")
    result = cli("db", "migrate", "--json", env=env)
    assert result.returncode == 2
    response = json.loads(result.stdout)
    assert response["ok"] is False
    assert "E_ARGUMENT" in diagnostic_codes(response)
    assert "private-password-sentinel" not in result.stdout + result.stderr


@pytest.mark.mysql
def test_cli_end_to_end_nonsoftware_vault_without_git(mysql_config, tmp_path):
    env = os.environ.copy()
    env.update(TRIBAL_DB_HOST=str(mysql_config.get("host", "127.0.0.1")),
               TRIBAL_DB_PORT=str(mysql_config.get("port", 3306)),
               TRIBAL_DB_USER=str(mysql_config["user"]),
               TRIBAL_DB_PASSWORD=str(mysql_config.get("password", "")),
               TRIBAL_DB_NAME=str(mysql_config["database"]), OPENAI_API_KEY="test-placeholder")
    key = "cli-" + uuid.uuid4().hex
    def run(*args):
        result = cli(*args, "--json", env=env)
        assert result.returncode == 0, result.stdout + result.stderr
        response = json.loads(result.stdout)
        assert response.get("ok", response.get("valid")) is True
        return response
    run("db", "migrate")
    run("kb", "ensure", key, "--name", "Botany notebook")
    run("domain", "ensure", "research", "--knowledge-base", key, "--name", "Research")
    config = dict(wrapper="tribal-title-headings-v1", encoding="cl100k_base", max_input_tokens=8192,
                  distance="cosine", normalization="l2-float32-v1")
    profile = run("profile", "ensure", "--key", "cli-profile-" + uuid.uuid4().hex,
                  "--dimensions", "3", "--configuration", json.dumps(config))["profile"]
    run("profile", "activate", profile["id"], "--knowledge-base", key)
    idle = run("index", "worker", "--once", "--knowledge-base", key)
    assert idle["state"] == "idle"
    vault = tmp_path / "vault"
    vault.mkdir()
    authored = note("## Observation\n\nSeed germination needle.\n", knowledge_base=key, id=str(uuid.uuid4()),
                    contexts=[dict(key="trial", type="experiment", locator="trial-12")])
    (vault / "botany.md").write_text(authored, encoding="utf-8")
    for name in (".git", ".obsidian", ".venv", ".tribal-staging"):
        (vault / name).mkdir()
        (vault / name / "ignored.md").write_text("ordinary ignored content\n", encoding="utf-8")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    marker = tmp_path / "git-was-run"
    trap = binaries / "git"
    trap.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 97\n", encoding="utf-8")
    trap.chmod(0o755)
    env["PATH"] = str(binaries) + os.pathsep + env.get("PATH", "")
    ingested = run("ingest", vault, "--knowledge-base", key)
    assert ingested["summary"]["created"] == 1
    head = ingested["documents"]["botany.md"]
    assert run("ingest", vault, "--knowledge-base", key)["summary"]["unchanged"] == 1
    status = run("index", "status", "--knowledge-base", key)
    assert status["pending"] == status["total"] == 1
    assert run("index", "backfill", "--knowledge-base", key)["enqueued"] == 0
    assert run("index", "retry", "--knowledge-base", key)["retried"] == 0
    hit = run("search", "needle", "--knowledge-base", key, "--mode", "lexical", "--lexical-mode", "literal")["hits"][0]
    assert hit["contexts"][0]["type"] == "experiment" and hit["applicability"] == "unknown"
    assert run("read", head["document_id"], "--knowledge-base", key)["content"] == authored
    context = run("context", head["document_id"], head["revision_id"], hit["chunk_id"], "--knowledge-base", key)
    assert context["chunks"][0]["content"] == "## Observation\n\nSeed germination needle.\n"
    replaced = run("rechunk", head["document_id"], "--knowledge-base", key)
    assert not set(replaced["chunk_ids"]).intersection(head["chunk_ids"])
    assert not marker.exists(), "nonsoftware import/search/read must not probe Git"
