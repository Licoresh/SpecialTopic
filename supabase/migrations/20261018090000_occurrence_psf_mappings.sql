-- One atomic review decision per extracted phrase and advertisement.
create table public.psf_mapping_reviews (
 extraction_id text primary key, records jsonb not null,
 version bigint not null check (version > 0),
 updated_at timestamptz not null default now(), updated_by uuid not null references auth.users(id)
);
create table public.psf_mapping_audit (
 id bigint generated always as identity primary key,
 extraction_id text not null, records jsonb not null, version bigint not null,
 changed_at timestamptz not null default now(), actor uuid not null references auth.users(id)
);
alter table public.psf_mapping_reviews enable row level security;
alter table public.psf_mapping_audit enable row level security;
revoke all on public.psf_mapping_reviews, public.psf_mapping_audit from anon, authenticated;
grant select on public.psf_mapping_reviews, public.psf_mapping_audit to authenticated;
create policy team_read on public.psf_mapping_reviews for select to authenticated
 using ((select public.workspace_role()) is not null);
create policy team_read on public.psf_mapping_audit for select to authenticated
 using ((select public.workspace_role()) is not null);

create function public.save_psf_mapping_review(rows jsonb, expected_version bigint)
 returns bigint language plpgsql security definer set search_path = '' as $$
declare occurrence text; current_version bigint; actor_name text; stamped jsonb;
begin
 if auth.uid() is null or not exists(select 1 from public.research_members where user_id=auth.uid() and active) then
  raise exception 'Active research membership is required';
 end if;
 if jsonb_typeof(rows) is distinct from 'array' or jsonb_array_length(rows)=0 then
  raise exception 'Supply a complete occurrence review';
 end if;
 occurrence := rows->0->>'extraction_id';
 if coalesce(btrim(occurrence),'')='' or expected_version is null or expected_version < 0 then
  raise exception 'An occurrence and expected version are required';
 end if;
 if exists(select 1 from jsonb_array_elements(rows) r
   where r->>'extraction_id' is distinct from occurrence
      or r->>'source_id' is distinct from rows->0->>'source_id'
      or r->>'normalized_phrase' is distinct from rows->0->>'normalized_phrase'
      or r->>'reference_hash' is distinct from rows->0->>'reference_hash'
      or r->>'occurrence_hash' is distinct from rows->0->>'occurrence_hash'
      or coalesce(btrim(r->>'source_id'),'')=''
      or coalesce(btrim(r->>'normalized_phrase'),'')=''
      or coalesce(btrim(r->>'reference_hash'),'')=''
      or coalesce(btrim(r->>'occurrence_hash'),'')=''
      or coalesce(btrim(r->>'rationale'),'')=''
      or r->>'competency_id' is null)
 then raise exception 'Every link needs consistent source evidence and a rationale'; end if;
 if (select count(distinct r->>'competency_id') from jsonb_array_elements(rows) r) <> jsonb_array_length(rows)
 or (jsonb_array_length(rows)>1 and (
   exists(select 1 from jsonb_array_elements(rows) r where btrim(r->>'competency_id')='')
   or (select count(distinct lower(btrim(r->>'rationale'))) from jsonb_array_elements(rows) r) <> jsonb_array_length(rows)))
 then raise exception 'Each selected competency needs a distinct rationale; no-match cannot have links'; end if;
 perform pg_advisory_xact_lock(hashtextextended(occurrence, 0));
 select version into current_version from public.psf_mapping_reviews where extraction_id=occurrence;
 if coalesce(current_version,0) <> expected_version then
  raise exception 'This occurrence changed. Refresh and review the current links.';
 end if;
 select email into actor_name from auth.users where id=auth.uid();
 select jsonb_agg(r || jsonb_build_object('reviewer',actor_name,'timestamp',clock_timestamp(),
                                       'version',expected_version+1)) into stamped
 from jsonb_array_elements(rows) r;
 insert into public.psf_mapping_reviews(extraction_id,records,version,updated_by)
 values(occurrence,stamped,expected_version+1,auth.uid())
 on conflict(extraction_id) do update set records=excluded.records,version=excluded.version,
 updated_at=clock_timestamp(),updated_by=excluded.updated_by;
 insert into public.psf_mapping_audit(extraction_id,records,version,actor)
 values(occurrence,stamped,expected_version+1,auth.uid());
 return expected_version+1;
end $$;
revoke all on function public.save_psf_mapping_review(jsonb,bigint) from public, anon;
grant execute on function public.save_psf_mapping_review(jsonb,bigint) to authenticated;
notify pgrst, 'reload schema';
