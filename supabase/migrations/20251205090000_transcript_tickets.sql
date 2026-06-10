CREATE TABLE teams (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name       TEXT NOT NULL,
  created_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE team_members (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  team_id    UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  email      TEXT,
  role       TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE transcript_jobs (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  team_id      UUID NOT NULL REFERENCES teams(id),
  transcript   TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','processing','complete','error')),
  error_msg    TEXT,
  submitted_by UUID REFERENCES auth.users(id),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE tickets (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  transcript_job_id UUID REFERENCES transcript_jobs(id),
  team_id           UUID NOT NULL REFERENCES teams(id),
  title             TEXT NOT NULL,
  description       TEXT,
  assignee_id       UUID REFERENCES team_members(id),
  assignee_name     TEXT,
  due_date          DATE,
  status            TEXT NOT NULL DEFAULT 'open',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE teams           ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_members    ENABLE ROW LEVEL SECURITY;
ALTER TABLE transcript_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE tickets         ENABLE ROW LEVEL SECURITY;

CREATE POLICY teams_owner           ON teams           FOR ALL USING (created_by = auth.uid());
CREATE POLICY team_members_owner    ON team_members    FOR ALL USING (team_id IN (SELECT id FROM teams WHERE created_by = auth.uid()));
CREATE POLICY transcript_jobs_owner ON transcript_jobs FOR ALL USING (submitted_by = auth.uid());
CREATE POLICY tickets_owner         ON tickets         FOR ALL USING (team_id IN (SELECT id FROM teams WHERE created_by = auth.uid()));
