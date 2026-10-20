CREATE TABLE embedding_jobs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    knowledge_base_id BINARY(16) NOT NULL,
    chunk_id BIGINT UNSIGNED NOT NULL,
    revision_id BINARY(16) NOT NULL,
    profile_id BINARY(16) NOT NULL,
    input_hash BINARY(32) NOT NULL,
    state ENUM('queued','running','succeeded','oversized','failed','discarded')
        NOT NULL DEFAULT 'queued',
    attempts INT UNSIGNED NOT NULL DEFAULT 0,
    available_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    claim_token BINARY(16) NULL,
    lease_expires_at DATETIME(6) NULL,
    last_error_code VARCHAR(64) NULL,
    last_error_message VARCHAR(1024) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_job_identity (chunk_id, profile_id, input_hash),
    KEY ix_job_claim (state, available_at, id),
    KEY ix_job_status (knowledge_base_id, profile_id, state),
    CONSTRAINT fk_job_knowledge_base FOREIGN KEY (knowledge_base_id)
        REFERENCES knowledge_bases (id),
    CONSTRAINT fk_job_revision FOREIGN KEY (revision_id)
        REFERENCES document_revisions (id),
    CONSTRAINT fk_job_profile FOREIGN KEY (profile_id)
        REFERENCES embedding_profiles (id),
    CONSTRAINT chk_job_claim CHECK (
        (state = 'running' AND claim_token IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR (state <> 'running' AND claim_token IS NULL AND lease_expires_at IS NULL)
    )
) ENGINE = InnoDB;

CREATE TABLE search_sessions (
    id BINARY(16) PRIMARY KEY,
    knowledge_base_id BINARY(16) NOT NULL,
    profile_id BINARY(16) NULL,
    query TEXT NOT NULL,
    query_vector VECTOR(16383) NULL,
    mode ENUM('semantic','lexical','hybrid') NOT NULL,
    lexical_mode ENUM('fulltext','literal') NOT NULL,
    parameters JSON NOT NULL,
    knowledge_generation BIGINT UNSIGNED NOT NULL,
    indexing_generation BIGINT UNSIGNED NOT NULL,
    result_count BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    expires_at DATETIME(6) NOT NULL,
    KEY ix_session_expiry (expires_at),
    KEY ix_session_knowledge_base (knowledge_base_id, created_at),
    CONSTRAINT fk_session_knowledge_base FOREIGN KEY (knowledge_base_id)
        REFERENCES knowledge_bases (id),
    CONSTRAINT fk_session_profile FOREIGN KEY (profile_id)
        REFERENCES embedding_profiles (id),
    CONSTRAINT chk_session_parameters CHECK (JSON_TYPE(parameters) = 'OBJECT')
) ENGINE = InnoDB;

CREATE TABLE search_session_results (
    session_id BINARY(16) NOT NULL,
    `rank` BIGINT UNSIGNED NOT NULL,
    document_id BINARY(16) NOT NULL,
    revision_id BINARY(16) NOT NULL,
    chunk_id BIGINT UNSIGNED NOT NULL,
    score DOUBLE NOT NULL,
    semantic_score DOUBLE NULL,
    lexical_score DOUBLE NULL,
    PRIMARY KEY (session_id, `rank`),
    UNIQUE KEY uq_session_chunk (session_id, chunk_id),
    CONSTRAINT fk_result_session FOREIGN KEY (session_id)
        REFERENCES search_sessions (id) ON DELETE CASCADE,
    CONSTRAINT fk_result_document FOREIGN KEY (document_id)
        REFERENCES documents (id),
    CONSTRAINT fk_result_revision FOREIGN KEY (revision_id)
        REFERENCES document_revisions (id),
    CONSTRAINT chk_result_rank CHECK (`rank` > 0)
) ENGINE = InnoDB;
