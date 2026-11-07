from tribal.project_store import ProjectStore


def test_sqlite_records_survive_store_restart(tmp_path):
    database = tmp_path / "tribal.sqlite3"
    first_store = ProjectStore(database)

    created = first_store.create_project(
        name="Compiler notes",
        owner_id=314159,
        owner_login="ada",
        mcp_url="https://tribal.example/projects/abc/mcp",
        token_signing_key="project-signing-key",
    )

    reopened_store = ProjectStore(database)
    loaded = reopened_store.get_project_for_owner(created.id, 314159)

    assert loaded == created
    assert loaded.status == "provisioning"
    assert reopened_store.allowed_github_ids(created.id) == frozenset({314159})


def test_project_reads_and_initial_membership_are_owner_scoped(tmp_path):
    store = ProjectStore(tmp_path / "tribal.sqlite3")
    owned = store.create_project("Private project", 101, "owner", "/projects/a/mcp", "key-a")
    another = store.create_project("Other project", 202, "other", "/projects/b/mcp", "key-b")

    assert [project.id for project in store.list_projects(101)] == [owned.id]
    assert [project.id for project in store.list_projects(202)] == [another.id]
    assert store.get_project_for_owner(owned.id, 202) is None
    assert store.get_project_for_owner("missing-project", 101) is None
    assert store.allowed_github_ids(owned.id) == frozenset({101})
    assert store.allowed_github_ids(another.id) == frozenset({202})


def test_incomplete_project_query_includes_failed_and_provisioning_only(tmp_path):
    store = ProjectStore(tmp_path / "tribal.sqlite3")
    provisioning = store.create_project("Still provisioning", 101, "owner", "/a", "key-a")
    failed = store.create_project("Failed", 101, "owner", "/b", "key-b")
    ready = store.create_project("Ready", 101, "owner", "/c", "key-c")
    store.set_status(failed.id, "failed", "Kubernetes API unavailable")
    store.set_status(ready.id, "ready")

    incomplete_ids = {project.id for project in store.list_incomplete_projects()}

    assert incomplete_ids == {provisioning.id, failed.id}
    assert store.get_project_for_owner(failed.id, 101).error == "Kubernetes API unavailable"
