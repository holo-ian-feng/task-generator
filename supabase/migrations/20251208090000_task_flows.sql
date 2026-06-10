CREATE TABLE task_flows (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  transcript_job_id UUID REFERENCES transcript_jobs(id) ON DELETE CASCADE,
  team_id           UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  title             TEXT NOT NULL,
  topic             TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE task_flow_steps (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_flow_id  UUID NOT NULL REFERENCES task_flows(id) ON DELETE CASCADE,
  title         TEXT NOT NULL,
  description   TEXT,
  step_order    INT NOT NULL,
  assignee_id   UUID REFERENCES team_members(id),
  assignee_name TEXT,
  due_date      DATE,
  status        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'done')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE task_flows       ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_flow_steps  ENABLE ROW LEVEL SECURITY;

CREATE POLICY task_flows_owner ON task_flows FOR ALL
  USING (team_id IN (SELECT id FROM teams WHERE created_by = auth.uid()));

CREATE POLICY task_flow_steps_owner ON task_flow_steps FOR ALL
  USING (task_flow_id IN (
    SELECT id FROM task_flows
    WHERE team_id IN (SELECT id FROM teams WHERE created_by = auth.uid())
  ));
