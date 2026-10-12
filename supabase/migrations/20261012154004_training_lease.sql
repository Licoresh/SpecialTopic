create table research_private.training_lease (
 singleton boolean primary key default true check(singleton),
 run_id uuid not null, owner_id uuid not null references auth.users(id), expires_at timestamptz not null
);
alter table research_private.training_lease enable row level security;
revoke all on research_private.training_lease from public,anon,authenticated;
create function research_private.training_lock(action text, run_id uuid) returns boolean language plpgsql security definer set search_path='' as $$
declare acquired boolean;
begin
 if auth.uid() is null or not exists(select 1 from public.research_members where user_id=auth.uid() and active and role='admin') then
  raise exception 'Only a project administrator can train models' using errcode='42501';
 end if;
 if action='acquire' then
  insert into research_private.training_lease as lease(singleton,run_id,owner_id,expires_at)
   values(true,run_id,auth.uid(),now()+interval '2 hours')
   on conflict(singleton) do update set run_id=excluded.run_id,owner_id=excluded.owner_id,expires_at=excluded.expires_at
   where lease.expires_at<now();
  get diagnostics acquired = row_count;
  return acquired;
 elsif action='release' then
  delete from research_private.training_lease t where t.run_id=training_lock.run_id and t.owner_id=auth.uid();
  return true;
 elsif action='check' then
  return exists(select 1 from research_private.training_lease t where t.run_id=training_lock.run_id and t.owner_id=auth.uid() and expires_at>now());
 end if;
 raise exception 'Unknown training action';
end $$;
revoke all on function research_private.training_lock(text,uuid) from public,anon;
grant execute on function research_private.training_lock(text,uuid) to authenticated;
create function public.training_lock(action text,run_id uuid) returns boolean language sql security invoker set search_path='' as $$
 select research_private.training_lock(action,run_id)
$$;
revoke all on function public.training_lock(text,uuid) from public,anon;
grant execute on function public.training_lock(text,uuid) to authenticated;
notify pgrst,'reload schema';
