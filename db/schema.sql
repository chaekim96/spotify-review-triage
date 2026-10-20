-- Postgres (Supabase) schema for the dashboard. Loaded by `python -m spp db-load`; read-only for the backend.
drop table if exists recommendations, claims, ranking, membership, issues, area_aggregates, records, run_summary cascade;

create table run_summary (
  key   text primary key,
  value jsonb not null
);
create table records (
  review_id       text primary key,
  source_sha256   text not null,
  status          text not null check (status in ('completed','quarantined')),
  reason          text,
  topic           text,
  intent          text,
  sentiment       double precision,
  severity        smallint,
  entities        jsonb,
  evidence_quote  text,
  needs_review    boolean,
  label_config    text,
  cache_source_id text,
  issue_id        text
);
create index records_issue on records(issue_id);
create table issues (
  issue_id    text primary key,
  topic       text not null,
  area        text not null,
  name        text not null,
  description text not null,
  keywords    jsonb not null
);
create table membership (
  issue_id  text not null references issues(issue_id),
  review_id text not null references records(review_id),
  primary key (issue_id, review_id)
);
create table ranking (
  rank            int primary key,
  issue_id        text not null references issues(issue_id),
  complaint_count int not null,
  severity_sum    int not null,
  mean_severity   text not null,   -- exact 6-decimal string, as exported
  priority_score  int not null
);
create table claims (
  claim_id text primary key,
  issue_id text not null references issues(issue_id),
  metric   text not null,
  value    text not null
);
create table area_aggregates (
  area                  text primary key,
  complaint_count       int not null,
  severity_sum          int not null,
  mean_severity         text not null,
  share_of_severity_pct text not null,
  cancellation_count    int not null,
  severity_4_plus       int not null
);
create table recommendations (
  id                  serial primary key,
  generated_utc       text not null,
  model_config        text not null,
  recommended_area    text not null,
  memo_markdown       text not null,
  cited_claim_ids     jsonb not null,
  cited_issue_ids     jsonb not null,
  evidence_review_ids jsonb not null
);
