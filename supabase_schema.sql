-- Shared research workspace. Membership is explicit: Auth alone grants no access.
create schema if not exists research_private;
revoke all on schema research_private from public, anon;
grant usage on schema research_private to authenticated;
create table public.research_members (
 user_id uuid primary key references auth.users(id) on delete cascade,
 role text not null check (role in ('admin','reviewer')), active boolean not null default true
);
alter table public.research_members enable row level security;
grant select on public.research_members to authenticated;
create policy own_membership on public.research_members for select to authenticated using (user_id = (select auth.uid()));
create function public.workspace_role() returns text language sql stable security invoker set search_path = '' as $$
 select role from public.research_members where user_id = auth.uid() and active
$$;
revoke all on function public.workspace_role() from public, anon;
grant execute on function public.workspace_role() to authenticated;

create table public.app_state (
 name text primary key, payload jsonb not null, updated_at timestamptz not null default now(), updated_by uuid references auth.users(id)
);
create table public.phrase_labels (
 normalized_phrase text primary key check (btrim(normalized_phrase) <> ''),
 label text not null check (btrim(label) <> ''), version bigint not null default 1, unique(normalized_phrase,label)
);
create table public.research_annotations (
 phrase text not null check (btrim(phrase) <> ''), normalized_phrase text not null, label text not null,
 psf_competency text not null default '', source_type text not null,
 source_id text not null check (btrim(source_id) <> ''), reviewer text not null, "timestamp" text not null,
 updated_at timestamptz not null default now(), updated_by uuid references auth.users(id),
 primary key(normalized_phrase,source_type,source_id),
 foreign key(normalized_phrase,label) references public.phrase_labels(normalized_phrase,label) on update cascade
);
create table public.research_candidates (
 phrase text not null, normalized_phrase text not null, source_type text not null default '', source_id text not null default '',
 job_title text not null default '', company text not null default '', source_url text not null default '',
 original_text text not null default '', candidate_file text not null default '', created_at timestamptz not null default now(),
 primary key(normalized_phrase,source_type,source_id)
);
create table public.annotation_audit (
 id bigint generated always as identity primary key, actor uuid not null references auth.users(id),
 changed_at timestamptz not null default now(), old_row jsonb, new_row jsonb
);
create index on public.app_state(updated_by);
create index on public.research_annotations(updated_by);
create index on public.annotation_audit(actor);
alter table public.app_state enable row level security;
revoke all on public.app_state from anon, authenticated;
grant select on public.app_state to authenticated;
create policy team_read on public.app_state for select to authenticated using ((select public.workspace_role()) is not null);
grant insert,update on public.app_state to authenticated;
create policy admin_insert on public.app_state for insert to authenticated with check ((select public.workspace_role()) = 'admin');
create policy admin_update on public.app_state for update to authenticated using ((select public.workspace_role()) = 'admin') with check ((select public.workspace_role()) = 'admin');
alter table public.phrase_labels enable row level security;
revoke all on public.phrase_labels from anon, authenticated;
grant select on public.phrase_labels to authenticated;
create policy team_read on public.phrase_labels for select to authenticated using ((select public.workspace_role()) is not null);
alter table public.research_annotations enable row level security;
revoke all on public.research_annotations from anon, authenticated;
grant select on public.research_annotations to authenticated;
create policy team_read on public.research_annotations for select to authenticated using ((select public.workspace_role()) is not null);
alter table public.research_candidates enable row level security;
revoke all on public.research_candidates from anon, authenticated;
grant select on public.research_candidates to authenticated;
create policy team_read on public.research_candidates for select to authenticated using ((select public.workspace_role()) is not null);
grant insert,update on public.research_candidates to authenticated;
create policy admin_insert on public.research_candidates for insert to authenticated with check ((select public.workspace_role()) = 'admin');
create policy admin_update on public.research_candidates for update to authenticated using ((select public.workspace_role()) = 'admin') with check ((select public.workspace_role()) = 'admin');
alter table public.annotation_audit enable row level security;
revoke all on public.annotation_audit from anon, authenticated;
grant select on public.annotation_audit to authenticated;
create policy team_read on public.annotation_audit for select to authenticated using ((select public.workspace_role()) is not null);

create function research_private.audit_annotation() returns trigger language plpgsql security definer set search_path = '' as $$
begin
 insert into public.annotation_audit(actor,old_row,new_row) values(auth.uid(),case when TG_OP = 'UPDATE' then to_jsonb(old) else null end,to_jsonb(new));
 return new;
end $$;
revoke all on function research_private.audit_annotation() from public, anon, authenticated;
create trigger annotation_history after insert or update on public.research_annotations for each row execute function research_private.audit_annotation();
create function research_private.stamp_editor() returns trigger language plpgsql set search_path = '' as $$
begin new.updated_by := auth.uid(); new.updated_at := clock_timestamp(); return new; end $$;
revoke all on function research_private.stamp_editor() from public, anon, authenticated;
create trigger state_editor before insert or update on public.app_state for each row execute function research_private.stamp_editor();
create trigger annotation_editor before insert or update on public.research_annotations for each row execute function research_private.stamp_editor();

-- A single SQL statement gives a consistent snapshot, including optimistic versions.
create function public.annotation_snapshot() returns jsonb language sql stable security invoker set search_path = '' as $$
 select coalesce(jsonb_agg(to_jsonb(a) || jsonb_build_object('version',p.version)
 order by a.normalized_phrase,a.source_type,a.source_id),'[]'::jsonb)
 from public.research_annotations a join public.phrase_labels p using(normalized_phrase)
$$;
revoke all on function public.annotation_snapshot() from public, anon;
grant execute on function public.annotation_snapshot() to authenticated;

-- Only this transaction can write annotations. Sorted locks avoid deadlocks.
create function research_private.save_annotations(rows jsonb, expected_versions jsonb, resolutions jsonb)
 returns integer language plpgsql security definer set search_path = '' as $$
declare p text; wanted text; current_label text; current_version bigint; r jsonb; actor_name text; saved integer := 0;
begin
 if auth.uid() is null or not exists(select 1 from public.research_members where user_id=auth.uid() and active) then
  raise exception 'Active team membership required' using errcode='42501';
 end if;
 select email into actor_name from auth.users where id=auth.uid();
 if jsonb_typeof(rows) is distinct from 'array' or jsonb_array_length(rows) > 1000 then raise exception 'Save at most 1000 reviewed rows at a time'; end if;
 if jsonb_typeof(expected_versions) is distinct from 'object' or jsonb_typeof(resolutions) is distinct from 'object' then raise exception 'Invalid review versions'; end if;
 if exists(select 1 from jsonb_array_elements(rows) x where
  coalesce(btrim(x->>'phrase'),'')='' or coalesce(btrim(x->>'normalized_phrase'),'')='' or
  coalesce(btrim(x->>'label'),'')='' or coalesce(btrim(x->>'source_id'),'')='' or coalesce(btrim(x->>'source_type'),'')='') then
  raise exception 'Phrase, category and source provenance are required'; end if;
 if exists(select 1 from jsonb_array_elements(rows) x group by x->>'normalized_phrase' having count(distinct x->>'label')>1) then
  raise exception 'Choose one category per normalized phrase'; end if;
 for p in select x->>'normalized_phrase' from jsonb_array_elements(rows) x
          union select jsonb_object_keys(resolutions) order by 1 loop
  perform pg_advisory_xact_lock(hashtextextended(p,0));
  select label,version into current_label,current_version from public.phrase_labels where normalized_phrase=p for update;
  if coalesce(current_version,0) <> coalesce((expected_versions->>p)::bigint,0) then
   raise exception 'Another researcher changed "%". Refresh the review table and reconcile your edit.',p using errcode='40001';
  end if;
  wanted := coalesce(resolutions->>p,(select x->>'label' from jsonb_array_elements(rows) x where x->>'normalized_phrase'=p limit 1));
  if wanted is null or btrim(wanted)='' then raise exception 'Category is required'; end if;
  if current_label is not null and current_label <> wanted and not (resolutions ? p) then
   raise exception 'Resolve the category for "%" explicitly before saving.',p;
  end if;
  insert into public.phrase_labels(normalized_phrase,label,version) values(p,wanted,1)
   on conflict(normalized_phrase) do update set label=excluded.label,version=public.phrase_labels.version+1;
  if current_label is distinct from wanted then
   update public.research_annotations set reviewer=actor_name,"timestamp"=clock_timestamp()::text where normalized_phrase=p;
  end if;
 end loop;
 for r in select value from jsonb_array_elements(rows) loop
  insert into public.research_annotations(phrase,normalized_phrase,label,psf_competency,source_type,source_id,reviewer,"timestamp")
   values(r->>'phrase',r->>'normalized_phrase',coalesce(resolutions->>(r->>'normalized_phrase'),r->>'label'),
    coalesce(r->>'psf_competency',''),r->>'source_type',r->>'source_id',actor_name,clock_timestamp()::text)
   on conflict(normalized_phrase,source_type,source_id) do update set
    phrase=excluded.phrase,label=excluded.label,psf_competency=excluded.psf_competency,reviewer=excluded.reviewer,"timestamp"=excluded."timestamp";
  saved := saved+1;
 end loop;
 return saved;
end $$;
revoke all on function research_private.save_annotations(jsonb,jsonb,jsonb) from public, anon;
grant execute on function research_private.save_annotations(jsonb,jsonb,jsonb) to authenticated;
create function public.save_reviewed_annotations(rows jsonb, expected_versions jsonb, resolutions jsonb default '{}'::jsonb)
 returns integer language sql security invoker set search_path = '' as $$
 select research_private.save_annotations(rows,expected_versions,resolutions)
$$;
revoke all on function public.save_reviewed_annotations(jsonb,jsonb,jsonb) from public, anon;
grant execute on function public.save_reviewed_annotations(jsonb,jsonb,jsonb) to authenticated;
notify pgrst, 'reload schema';
