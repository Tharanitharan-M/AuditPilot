-- Sprint 7 chunk 7.6 — questionnaire_runs + questionnaire_questions tables
-- Refs: PLAN.md chunks 7.6-7.10; ADR-0010 (job lifecycle); system-design 3.4, 11.7.

-- questionnaire_runs — one row per uploaded questionnaire.
CREATE TABLE IF NOT EXISTS questionnaire_runs (
    id                   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              TEXT         NOT NULL,
    filename             TEXT         NOT NULL DEFAULT '',
    format               TEXT         NOT NULL DEFAULT 'sig-lite'
        CHECK (format IN ('sig-lite', 'custom')),
    status               TEXT         NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'parsing', 'drafting', 'ready', 'failed')),
    source_r2_key        TEXT         NOT NULL DEFAULT '',
    output_r2_key        TEXT,
    question_count       INTEGER      NOT NULL DEFAULT 0,
    answered_count       INTEGER      NOT NULL DEFAULT 0,
    flagged_count        INTEGER      NOT NULL DEFAULT 0,
    cluster_count        INTEGER      NOT NULL DEFAULT 0,
    job_idempotency_key  TEXT         NOT NULL DEFAULT '',
    failure_reason       TEXT,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_questionnaire_runs__user_status_created
    ON questionnaire_runs (user_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_questionnaire_runs__user_id
    ON questionnaire_runs (user_id);

ALTER TABLE questionnaire_runs ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'questionnaire_runs'
          AND policyname = 'questionnaire_runs__user_isolation'
    ) THEN
        CREATE POLICY questionnaire_runs__user_isolation ON questionnaire_runs
            USING (user_id = current_setting('app.current_user_id', true))
            WITH CHECK (user_id = current_setting('app.current_user_id', true));
    END IF;
END $$;


-- questionnaire_questions — one row per parsed cell. Drives the grid UI
-- and persists user edits so refresh does not lose work.
CREATE TABLE IF NOT EXISTS questionnaire_questions (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id            UUID         NOT NULL REFERENCES questionnaire_runs(id) ON DELETE CASCADE,
    user_id           TEXT         NOT NULL,
    question_id       TEXT         NOT NULL,
    sheet             TEXT         NOT NULL,
    row_idx           INTEGER      NOT NULL,
    column_idx        INTEGER      NOT NULL,
    section           TEXT         NOT NULL DEFAULT '',
    domain            TEXT         NOT NULL DEFAULT 'uncategorized',
    answer_type       TEXT         NOT NULL DEFAULT 'unknown',
    question_text     TEXT         NOT NULL DEFAULT '',
    answer_text       TEXT         NOT NULL DEFAULT '',
    confidence        REAL         NOT NULL DEFAULT 0.0
        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    flagged           BOOLEAN      NOT NULL DEFAULT FALSE,
    citations         JSONB        NOT NULL DEFAULT '[]'::jsonb,
    edited_by_user    BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (run_id, question_id)
);

CREATE INDEX IF NOT EXISTS ix_questionnaire_questions__run
    ON questionnaire_questions (run_id, sheet, row_idx);

CREATE INDEX IF NOT EXISTS ix_questionnaire_questions__user_run
    ON questionnaire_questions (user_id, run_id);

CREATE INDEX IF NOT EXISTS ix_questionnaire_questions__flagged
    ON questionnaire_questions (run_id, flagged)
    WHERE flagged = TRUE;

ALTER TABLE questionnaire_questions ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'questionnaire_questions'
          AND policyname = 'questionnaire_questions__user_isolation'
    ) THEN
        CREATE POLICY questionnaire_questions__user_isolation ON questionnaire_questions
            USING (user_id = current_setting('app.current_user_id', true))
            WITH CHECK (user_id = current_setting('app.current_user_id', true));
    END IF;
END $$;


-- LISTEN/NOTIFY bridge: every UPDATE on questionnaire_runs broadcasts a
-- compact JSON payload on the 'questionnaire_run_updates' channel. The
-- API's SSE bridge (chunk 7.8) subscribes via asyncpg LISTEN.
CREATE OR REPLACE FUNCTION questionnaire_runs__notify_update()
RETURNS TRIGGER AS $$
DECLARE
    payload TEXT;
BEGIN
    payload := json_build_object(
        'run_id', NEW.id::text,
        'user_id', NEW.user_id,
        'status', NEW.status,
        'question_count', NEW.question_count,
        'answered_count', NEW.answered_count,
        'flagged_count', NEW.flagged_count,
        'cluster_count', NEW.cluster_count
    )::text;
    PERFORM pg_notify('questionnaire_run_updates', payload);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS questionnaire_runs__notify_update_trigger
    ON questionnaire_runs;

CREATE TRIGGER questionnaire_runs__notify_update_trigger
    AFTER INSERT OR UPDATE ON questionnaire_runs
    FOR EACH ROW
    EXECUTE FUNCTION questionnaire_runs__notify_update();
