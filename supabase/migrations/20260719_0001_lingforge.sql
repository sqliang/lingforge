create schema if not exists app;
revoke all on schema app from anon, authenticated;

create type app.project_lifecycle as enum ('provisioning', 'draft', 'awaiting_approval', 'ready', 'archived');
create type app.contract_status as enum ('draft', 'approved', 'superseded');
create type app.run_kind as enum ('initial', 'update', 'retry', 'restore');
create type app.run_status as enum ('queued', 'claimed', 'running', 'awaiting_approval', 'cancelling', 'completed', 'failed', 'cancelled');
create type app.run_stage as enum ('planning', 'generating', 'validating', 'typechecking', 'building', 'repairing', 'committing', 'promoting');

create table app.projects (
  id uuid primary key,
  owner_id uuid not null references auth.users(id),
  title text not null default 'Untitled project',
  original_prompt text not null check (char_length(original_prompt) between 10 and 2000),
  lifecycle_status app.project_lifecycle not null default 'provisioning',
  stable_version_id uuid,
  template_version text not null default 'v1',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  archived_at timestamptz
);

create table app.build_contracts (
  id uuid primary key,
  project_id uuid not null references app.projects(id) on delete cascade,
  version integer not null,
  content_json jsonb not null,
  status app.contract_status not null default 'draft',
  created_by uuid not null references auth.users(id),
  approved_at timestamptz,
  superseded_at timestamptz,
  created_at timestamptz not null default now(),
  unique (project_id, version)
);
create unique index build_contracts_one_approved on app.build_contracts(project_id) where status = 'approved';

create table app.agent_runs (
  id uuid primary key,
  project_id uuid not null references app.projects(id) on delete cascade,
  kind app.run_kind not null,
  request_id uuid not null,
  contract_id uuid references app.build_contracts(id),
  base_version_id uuid,
  thread_id text,
  status app.run_status not null default 'queued',
  stage app.run_stage,
  next_event_sequence integer not null default 1,
  repair_attempts smallint not null default 0 check (repair_attempts between 0 and 1),
  cancel_requested_at timestamptz,
  lease_expires_at timestamptz,
  agent_config_version text not null default 'v1',
  model_id text,
  prompt_version text not null default 'v1',
  error_code text,
  error_message text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  unique (project_id, request_id)
);
create unique index agent_runs_one_active on app.agent_runs(project_id)
where status in ('queued', 'claimed', 'running', 'awaiting_approval', 'cancelling');

create table app.messages (
  id uuid primary key,
  project_id uuid not null references app.projects(id) on delete cascade,
  run_id uuid references app.agent_runs(id),
  role text not null check (role in ('user', 'assistant', 'system')),
  visible_content text not null,
  summary text,
  created_at timestamptz not null default now()
);

create table app.run_events (
  id uuid primary key,
  run_id uuid not null references app.agent_runs(id) on delete cascade,
  sequence integer not null,
  type text not null,
  schema_version smallint not null default 1,
  payload_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (run_id, sequence)
);

create table app.build_attempts (
  id uuid primary key,
  run_id uuid not null references app.agent_runs(id) on delete cascade,
  attempt_no smallint not null check (attempt_no between 1 and 2),
  source_commit_sha text,
  status text not null check (status in ('running', 'succeeded', 'failed', 'cancelled')),
  diagnostics_ref text,
  build_log_ref text,
  runner_image_digest text,
  duration_ms integer,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  unique (run_id, attempt_no)
);

create table app.preview_artifacts (
  id uuid primary key,
  build_id uuid not null references app.build_attempts(id),
  storage_key text not null unique,
  integrity_hash text not null,
  manifest_json jsonb not null,
  state text not null check (state in ('uploading', 'ready', 'failed')),
  created_at timestamptz not null default now()
);

create table app.project_versions (
  id uuid primary key,
  project_id uuid not null references app.projects(id) on delete cascade,
  commit_sha text not null,
  parent_version_id uuid references app.project_versions(id),
  build_id uuid not null references app.build_attempts(id),
  template_version text not null,
  message text not null,
  origin_kind app.run_kind not null,
  restored_from_version_id uuid references app.project_versions(id),
  created_at timestamptz not null default now(),
  unique (project_id, commit_sha)
);
alter table app.projects add constraint projects_stable_version_fk foreign key (stable_version_id) references app.project_versions(id);

create table app.agent_checkpoints (
  run_id uuid primary key references app.agent_runs(id) on delete cascade,
  checkpoint_ref text not null,
  updated_at timestamptz not null default now()
);

create index projects_owner_updated_idx on app.projects(owner_id, updated_at desc);
create index run_events_run_sequence_idx on app.run_events(run_id, sequence);
create index agent_runs_queue_idx on app.agent_runs(status, created_at) where status = 'queued';

alter table app.projects enable row level security;
alter table app.build_contracts enable row level security;
alter table app.agent_runs enable row level security;
alter table app.messages enable row level security;
alter table app.run_events enable row level security;
alter table app.build_attempts enable row level security;
alter table app.preview_artifacts enable row level security;
alter table app.project_versions enable row level security;

create policy projects_owner on app.projects for all using (owner_id = auth.uid()) with check (owner_id = auth.uid());
create policy contracts_owner on app.build_contracts for all using (exists (select 1 from app.projects p where p.id = project_id and p.owner_id = auth.uid()));
create policy runs_owner on app.agent_runs for all using (exists (select 1 from app.projects p where p.id = project_id and p.owner_id = auth.uid()));
create policy messages_owner on app.messages for all using (exists (select 1 from app.projects p where p.id = project_id and p.owner_id = auth.uid()));
create policy events_owner on app.run_events for select using (exists (select 1 from app.agent_runs r join app.projects p on p.id = r.project_id where r.id = run_id and p.owner_id = auth.uid()));
create policy builds_owner on app.build_attempts for select using (exists (select 1 from app.agent_runs r join app.projects p on p.id = r.project_id where r.id = run_id and p.owner_id = auth.uid()));
create policy artifacts_owner on app.preview_artifacts for select using (exists (select 1 from app.build_attempts b join app.agent_runs r on r.id = b.run_id join app.projects p on p.id = r.project_id where b.id = build_id and p.owner_id = auth.uid()));
create policy versions_owner on app.project_versions for select using (exists (select 1 from app.projects p where p.id = project_id and p.owner_id = auth.uid()));

-- Browser clients never receive a Storage policy. Preview, build logs and exports are
-- private platform artifacts accessed only by trusted API/Preview Gateway credentials.
insert into storage.buckets (id, name, public)
values ('preview-artifacts', 'preview-artifacts', false),
       ('build-logs', 'build-logs', false),
       ('exports', 'exports', false)
on conflict (id) do update set public = false;
