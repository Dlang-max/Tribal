"""Load explicit local server settings and construct real storage adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import sysconfig

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    project_id: str
    host: str = "127.0.0.1"
    port: int = 8000
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "tribal"
    mysql_password: str = "tribal-local"
    mysql_database: str = "tribal"
    s3_endpoint_url: str = "http://127.0.0.1:8333"
    s3_bucket: str = "tribal"
    s3_access_key: str = "tribal-local"
    s3_secret_key: str = "tribal-local-secret"
    codex_bin: str = "codex"
    codex_model: str | None = None
    curator_timeout_seconds: float = 300
    internal_url: str = "http://127.0.0.1:8000/internal/mcp"
    gui_directory: str | None = None
    spec_root: str | None = None
    validator_path: str | None = None
    mcp_bearer_token: str | None = field(default=None, repr=False)

    # Read configuration without importing or contacting optional backend dependencies.
    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(Path.cwd() / ".env", override=False)
        project_id = os.environ.get("TRIBAL_PROJECT_ID", "").strip()
        if not project_id:
            raise ValueError("Set TRIBAL_PROJECT_ID to the knowledge base's project ID")
        port = int(os.environ.get("PORT", "8000"))
        return cls(
            project_id=project_id, host=os.environ.get("HOST", "127.0.0.1"), port=port,
            mysql_host=os.environ.get("TRIBAL_MYSQL_HOST", "127.0.0.1"),
            mysql_port=int(os.environ.get("TRIBAL_MYSQL_PORT", "3306")),
            mysql_user=os.environ.get("TRIBAL_MYSQL_USER", "tribal"),
            mysql_password=os.environ.get("TRIBAL_MYSQL_PASSWORD", "tribal-local"),
            mysql_database=os.environ.get("TRIBAL_MYSQL_DATABASE", "tribal"),
            s3_endpoint_url=os.environ.get("TRIBAL_S3_ENDPOINT_URL", "http://127.0.0.1:8333"),
            s3_bucket=os.environ.get("TRIBAL_S3_BUCKET", "tribal"),
            s3_access_key=os.environ.get("TRIBAL_S3_ACCESS_KEY", "tribal-local"),
            s3_secret_key=os.environ.get("TRIBAL_S3_SECRET_KEY", "tribal-local-secret"),
            codex_bin=os.environ.get("TRIBAL_CODEX_BIN", "codex"),
            codex_model=os.environ.get("TRIBAL_CODEX_MODEL") or None,
            curator_timeout_seconds=float(os.environ.get("TRIBAL_CURATOR_TIMEOUT_SECONDS", "300")),
            internal_url=os.environ.get("TRIBAL_INTERNAL_URL", f"http://127.0.0.1:{port}/internal/mcp"),
            gui_directory=os.environ.get("TRIBAL_GUI_DIRECTORY") or None,
            spec_root=os.environ.get("TRIBAL_SPEC_ROOT") or None,
            validator_path=os.environ.get("TRIBAL_VALIDATOR_PATH") or None,
            mcp_bearer_token=os.environ.get("TRIBAL_MCP_BEARER_TOKEN"),
        )


# Build the production service with real MySQL, SeaweedFS, and optional embeddings.
def build_service(settings: Settings):
    from .embeddings import OpenAIEmbeddingClient
    from .service import KnowledgeBaseService
    from .storage import MySQLCatalog, SeaweedObjectStore

    resources = Path(__file__).resolve().parents[3] / "agent-knowledge-base"
    if not resources.is_dir():
        resources = Path(sysconfig.get_path("data")) / "share/tribal/agent-knowledge-base"
    spec_root = Path(settings.spec_root) if settings.spec_root else resources / "specs/v1"
    validator_path = Path(settings.validator_path) if settings.validator_path else (
        resources / "validation/v1/validate_knowledge_base_notes.py")
    if not spec_root.is_dir() or not validator_path.is_file():
        raise ValueError("Knowledge-base specs/validator are missing; reinstall Tribal or set TRIBAL_SPEC_ROOT/TRIBAL_VALIDATOR_PATH")

    catalog = MySQLCatalog(
        host=settings.mysql_host, port=settings.mysql_port, user=settings.mysql_user,
        password=settings.mysql_password, database=settings.mysql_database,
    )
    objects = SeaweedObjectStore(
        settings.s3_bucket, endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key, secret_key=settings.s3_secret_key,
    )
    key = os.environ.get("OPENAI_API_KEY")
    embedding = OpenAIEmbeddingClient(api_key=key) if key else None
    return KnowledgeBaseService(
        settings.project_id, objects, catalog, embedding_client=embedding,
        spec_root=spec_root, validator_path=validator_path,
    )
