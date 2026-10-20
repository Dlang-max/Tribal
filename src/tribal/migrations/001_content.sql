-- ============================================================
-- 1. Knowledge bases
-- ============================================================

CREATE TABLE knowledge_bases (
    id                  BINARY(16) PRIMARY KEY,
    knowledge_base_key  VARCHAR(128) NOT NULL,
    name                VARCHAR(255) NOT NULL,
    description         TEXT NULL,
    active_profile_id   BINARY(16) NULL,
    knowledge_generation BIGINT UNSIGNED NOT NULL DEFAULT 0,
    indexing_generation BIGINT UNSIGNED NOT NULL DEFAULT 0,
    created_at          DATETIME(6) NOT NULL
                        DEFAULT CURRENT_TIMESTAMP(6),

    UNIQUE KEY uq_knowledge_base_key (knowledge_base_key)
) ENGINE = InnoDB;


-- ============================================================
-- 2. Domains
-- ============================================================

CREATE TABLE domains (
    id                  BINARY(16) PRIMARY KEY,
    knowledge_base_id   BINARY(16) NOT NULL,
    domain_key          VARCHAR(128) NOT NULL,
    name                VARCHAR(255) NOT NULL,
    description         TEXT NULL,
    created_at          DATETIME(6) NOT NULL
                        DEFAULT CURRENT_TIMESTAMP(6),

    UNIQUE KEY uq_domain_key (
        knowledge_base_id,
        domain_key
    ),

    -- Supports checking knowledge base ownership through composite FKs.
    UNIQUE KEY uq_domain_knowledge_base (
        knowledge_base_id,
        id
    ),

    CONSTRAINT fk_domain_knowledge_base
        FOREIGN KEY (knowledge_base_id)
        REFERENCES knowledge_bases (id)
) ENGINE = InnoDB;


-- ============================================================
-- 3. Documents: stable identity and current state
-- ============================================================

CREATE TABLE documents (
    id                   BINARY(16) PRIMARY KEY,
    knowledge_base_id    BINARY(16) NOT NULL,

    -- Current vault-relative path, including the ".md" extension.
    -- Portable NFC/case-fold collisions are checked under a knowledge base
    -- row lock; this SQL collation alone does not enforce that rule.
    vault_path           VARCHAR(512)
                         COLLATE utf8mb4_0900_bin NOT NULL,

    -- NULL only while creating the initial revision.
    current_revision_id  BINARY(16) NULL,

    created_at           DATETIME(6) NOT NULL
                         DEFAULT CURRENT_TIMESTAMP(6),

    deleted_at           DATETIME(6) NULL,

    UNIQUE KEY uq_document_path (
        knowledge_base_id,
        vault_path
    ),

    UNIQUE KEY uq_document_knowledge_base (
        knowledge_base_id,
        id
    ),

    CONSTRAINT fk_document_knowledge_base
        FOREIGN KEY (knowledge_base_id)
        REFERENCES knowledge_bases (id)
) ENGINE = InnoDB;


-- ============================================================
-- 4. Document revisions: immutable content snapshots
-- ============================================================

CREATE TABLE document_revisions (
    id                   BINARY(16) PRIMARY KEY,
    document_id          BINARY(16) NOT NULL,
    knowledge_base_id    BINARY(16) NOT NULL,
    domain_id            BINARY(16) NOT NULL,

    revision_number      INT UNSIGNED NOT NULL,
    parent_revision_id   BINARY(16) NULL,

    -- Version of Tribal's Markdown schema.
    schema_version       SMALLINT UNSIGNED NOT NULL,

    -- Historical location at the time this revision was created.
    vault_path           VARCHAR(512)
                         COLLATE utf8mb4_0900_bin NOT NULL,

    title                VARCHAR(255) NOT NULL,
    summary              TEXT NOT NULL,

    kind                 ENUM(
                             'finding',
                             'overview',
                             'decision',
                             'procedure',
                             'reference'
                         ) NOT NULL,

    status               ENUM(
                             'active',
                             'superseded',
                             'archived'
                         ) NOT NULL DEFAULT 'active',

    verification_state   ENUM(
                             'unverified',
                             'verified',
                             'disputed'
                         ) NOT NULL DEFAULT 'unverified',

    verified_at          DATETIME(6) NULL,

    -- Domain-specific applicability, e.g. region, population,
    -- date range, experimental conditions, or operating environment.
    scope                JSON NOT NULL,

    -- Explicit external working contexts, defaulted to [] by the API.
    -- Example: [{"key":"trial","type":"experiment",
    --            "locator":"urn:trial:germination-2026"}]
    -- Git metadata belongs in a declared git_repository context.
    contexts             JSON NOT NULL,

    -- Arrays of strings.
    tags                 JSON NOT NULL,
    aliases              JSON NOT NULL,

    -- Canonical authored document, including YAML frontmatter.
    markdown             LONGTEXT NOT NULL,

    -- SHA-256 of the exact stored Markdown's UTF-8 bytes.
    content_hash         BINARY(32) NOT NULL,

    author_type          ENUM(
                             'human',
                             'agent',
                             'system'
                         ) NOT NULL,

    author_id            VARCHAR(255) NOT NULL,
    change_summary       TEXT NULL,

    created_at           DATETIME(6) NOT NULL
                         DEFAULT CURRENT_TIMESTAMP(6),

    UNIQUE KEY uq_document_revision_number (
        document_id,
        revision_number
    ),

    UNIQUE KEY uq_revision_document (
        document_id,
        id
    ),

    KEY ix_revision_domain (
        domain_id,
        kind,
        status
    ),

    FULLTEXT KEY ft_revision_description (
        title,
        summary
    ),

    -- The document must belong to the supplied knowledge base.
    CONSTRAINT fk_revision_document
        FOREIGN KEY (knowledge_base_id, document_id)
        REFERENCES documents (knowledge_base_id, id),

    -- The domain must belong to that same knowledge base.
    CONSTRAINT fk_revision_domain
        FOREIGN KEY (knowledge_base_id, domain_id)
        REFERENCES domains (knowledge_base_id, id),

    -- A parent revision must belong to the same document.
    CONSTRAINT fk_revision_parent
        FOREIGN KEY (document_id, parent_revision_id)
        REFERENCES document_revisions (document_id, id),

    CONSTRAINT chk_revision_number
        CHECK (revision_number > 0),

    CONSTRAINT chk_schema_version
        CHECK (schema_version > 0),

    CONSTRAINT chk_verified_timestamp
        CHECK (
            verification_state <> 'verified'
            OR verified_at IS NOT NULL
        ),

    CONSTRAINT chk_scope_object
        CHECK (JSON_TYPE(scope) = 'OBJECT'),

    CONSTRAINT chk_contexts_array
        CHECK (JSON_TYPE(contexts) = 'ARRAY'),

    CONSTRAINT chk_tags_array
        CHECK (JSON_TYPE(tags) = 'ARRAY'),

    CONSTRAINT chk_aliases_array
        CHECK (JSON_TYPE(aliases) = 'ARRAY'),

    CONSTRAINT chk_summary_capacity
        CHECK (OCTET_LENGTH(summary) <= 8192),

    CONSTRAINT chk_markdown_capacity
        CHECK (OCTET_LENGTH(markdown) <= 8388608)
) ENGINE = InnoDB;


-- Added after document_revisions exists because the tables
-- reference one another. This also checks revision ownership.

ALTER TABLE documents
    ADD CONSTRAINT fk_document_current_revision
    FOREIGN KEY (id, current_revision_id)
    REFERENCES document_revisions (document_id, id);


-- ============================================================
-- 5. Sources: evidence extracted from a revision
-- ============================================================

CREATE TABLE document_sources (
    id                   BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    revision_id          BINARY(16) NOT NULL,

    -- NULL means the source applies to the whole document.
    section_anchor       VARCHAR(255) NULL,

    -- Extensible domain-neutral classification; validated by the API.
    source_type          VARCHAR(64) NOT NULL,

    -- File path, URL, document UUID, or another source identifier.
    locator              TEXT NOT NULL,

    -- Optional reference to contexts[].key on this source revision.
    -- JSON context membership is validated by the API.
    context_key          VARCHAR(128) NULL,

    -- Source-specific version: edition, release, entry ID, timestamp,
    -- or Git object ID only when the declared context is Git.
    source_revision      VARCHAR(255) NULL,

    -- Source-specific information such as method, edition, page,
    -- observation time, symbol, line range, outcome, or reviewer.
    details              JSON NULL,

    KEY ix_source_revision (
        revision_id,
        section_anchor
    ),

    CONSTRAINT fk_source_revision
        FOREIGN KEY (revision_id)
        REFERENCES document_revisions (id),

    CONSTRAINT chk_source_locator_capacity
        CHECK (OCTET_LENGTH(locator) <= 8192)
) ENGINE = InnoDB;


-- ============================================================
-- 6. Links: outgoing references and backlink lookup
-- ============================================================

CREATE TABLE document_links (
    id                   BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    source_revision_id   BINARY(16) NOT NULL,

    -- Occurrence order within the source document.
    ordinal              INT UNSIGNED NOT NULL,

    source_anchor        VARCHAR(255) NULL,

    -- Original syntax, including aliases and unresolved references.
    raw_link             TEXT NOT NULL,

    -- Parsed target name or path, excluding its anchor.
    target_text          VARCHAR(1024) NOT NULL,
    target_anchor        VARCHAR(255) NULL,

    -- NULL when missing or ambiguous.
    target_document_id   BINARY(16) NULL,

    UNIQUE KEY uq_link_occurrence (
        source_revision_id,
        ordinal
    ),

    KEY ix_link_target (
        target_document_id
    ),

    CONSTRAINT fk_link_source
        FOREIGN KEY (source_revision_id)
        REFERENCES document_revisions (id),

    CONSTRAINT fk_link_target
        FOREIGN KEY (target_document_id)
        REFERENCES documents (id),

    CONSTRAINT chk_raw_link_capacity
        CHECK (OCTET_LENGTH(raw_link) <= 16384)
) ENGINE = InnoDB;


-- ============================================================
-- 7. Chunks: focused retrieval units
-- ============================================================

CREATE TABLE document_chunks (
    -- Published chunk identity is immutable. Rechunking allocates new IDs.
    id                   BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    revision_id          BINARY(16) NOT NULL,

    -- Position within the revision's chunk sequence.
    ordinal              INT UNSIGNED NOT NULL,

    -- Example: ["Architecture", "Startup sequence"].
    heading_path         JSON NOT NULL,

    section_anchor       VARCHAR(255) NULL,
    content              MEDIUMTEXT NOT NULL,

    -- Half-open byte range [start_byte, end_byte)
    -- within the canonical UTF-8 Markdown.
    start_byte           INT UNSIGNED NOT NULL,
    end_byte             INT UNSIGNED NOT NULL,

    chunker_version      VARCHAR(32) NOT NULL,

    UNIQUE KEY uq_chunk_position (
        revision_id,
        ordinal
    ),

    FULLTEXT KEY ft_chunk_content (
        content
    ),

    CONSTRAINT fk_chunk_revision
        FOREIGN KEY (revision_id)
        REFERENCES document_revisions (id),

    CONSTRAINT chk_chunk_range
        CHECK (end_byte > start_byte),

    CONSTRAINT chk_heading_path_array
        CHECK (JSON_TYPE(heading_path) = 'ARRAY'),

    CONSTRAINT chk_chunk_capacity
        CHECK (OCTET_LENGTH(content) <= 8388608),

    CONSTRAINT chk_chunk_end
        CHECK (end_byte <= 8388608)
) ENGINE = InnoDB;


-- ============================================================
-- 8. Embedding profiles: immutable model configurations
-- ============================================================

CREATE TABLE embedding_profiles (
    id                   BINARY(16) PRIMARY KEY,
    profile_key          VARCHAR(128) NOT NULL,

    provider             VARCHAR(128) NOT NULL,
    model                VARCHAR(255) NOT NULL,
    model_version        VARCHAR(128) NULL,

    dimensions           SMALLINT UNSIGNED NOT NULL,

    -- Input templates, normalization, distance metric,
    -- output dimensions, and other model settings.
    configuration        JSON NOT NULL,

    created_at           DATETIME(6) NOT NULL
                         DEFAULT CURRENT_TIMESTAMP(6),

    UNIQUE KEY uq_embedding_profile_key (
        profile_key
    ),

    UNIQUE KEY uq_embedding_profile_dimensions (
        id,
        dimensions
    ),

    CONSTRAINT chk_profile_dimensions
        CHECK (dimensions BETWEEN 1 AND 16383),

    CONSTRAINT chk_embedding_configuration_object
        CHECK (JSON_TYPE(configuration) = 'OBJECT')
) ENGINE = InnoDB;


-- ============================================================
-- 9. Chunk embeddings: vectors generated from chunk inputs
-- ============================================================

CREATE TABLE chunk_embeddings (
    chunk_id             BIGINT UNSIGNED NOT NULL,
    profile_id           BINARY(16) NOT NULL,
    dimensions           SMALLINT UNSIGNED NOT NULL,

    -- Capacity accommodates profiles with different dimensions.
    embedding            VECTOR(16383) NOT NULL,

    -- SHA-256 of the exact text submitted to the embedding model.
    input_hash           BINARY(32) NOT NULL,

    created_at           DATETIME(6) NOT NULL
                         DEFAULT CURRENT_TIMESTAMP(6),

    PRIMARY KEY (
        chunk_id,
        profile_id
    ),

    KEY ix_embedding_reuse (
        profile_id,
        input_hash
    ),

    CONSTRAINT fk_embedding_chunk
        FOREIGN KEY (chunk_id)
        REFERENCES document_chunks (id),

    -- Checks that the declared dimensions match the profile.
    CONSTRAINT fk_embedding_profile
        FOREIGN KEY (profile_id, dimensions)
        REFERENCES embedding_profiles (id, dimensions)
) ENGINE = InnoDB;

ALTER TABLE knowledge_bases
    ADD CONSTRAINT fk_knowledge_base_active_profile
    FOREIGN KEY (active_profile_id) REFERENCES embedding_profiles (id);

-- MySQL 9.7.2 rejects VECTOR references in CHECK constraints (error 3064).
-- Triggers enforce the same actual-vector dimension invariant on both writes.
DELIMITER $$
CREATE TRIGGER chunk_embeddings_dimensions_insert
BEFORE INSERT ON chunk_embeddings
FOR EACH ROW
BEGIN
    IF VECTOR_DIM(NEW.embedding) <> NEW.dimensions THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Vector dimensions do not match profile';
    END IF;
END$$
CREATE TRIGGER chunk_embeddings_dimensions_update
BEFORE UPDATE ON chunk_embeddings
FOR EACH ROW
BEGIN
    IF VECTOR_DIM(NEW.embedding) <> NEW.dimensions THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Vector dimensions do not match profile';
    END IF;
END$$
DELIMITER ;
