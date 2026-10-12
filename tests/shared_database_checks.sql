-- SYNTHETIC TEST ONLY. Always rolls back. Never train on these records.
begin;
select set_config('request.jwt.claim.sub',(select user_id::text from public.research_members where role='admin' and active limit 1),true);
set local role authenticated;
do $$
declare n integer; blocked boolean := false; run uuid := gen_random_uuid();
begin
 if public.workspace_role() <> 'admin' then raise exception 'Admin membership check failed'; end if;
 if not public.training_lock('acquire',run) then raise exception 'Lease acquisition failed'; end if;
 if public.training_lock('acquire',gen_random_uuid()) then raise exception 'Concurrent training was allowed'; end if;
 if not public.training_lock('check',run) then raise exception 'Lease verification failed'; end if;
 perform public.training_lock('release',run);
 n := public.save_reviewed_annotations('[{"phrase":"SYNTHETIC QA","normalized_phrase":"synthetic qa","label":"Technical","source_type":"jobs","source_id":"SYNTHETIC-QA-ONLY"}]','{}','{}');
 if n<>1 then raise exception 'Save failed'; end if;
 begin
  perform public.save_reviewed_annotations('[{"phrase":"SYNTHETIC QA","normalized_phrase":"synthetic qa","label":"Soft","source_type":"jobs","source_id":"SYNTHETIC-QA-ONLY"}]','{}','{}');
 exception when serialization_failure then blocked:=true;
 end;
 if not blocked then raise exception 'Stale save was allowed'; end if;
 perform public.save_reviewed_annotations('[{"phrase":"SYNTHETIC QA","normalized_phrase":"synthetic qa","label":"Technical","source_type":"jobs","source_id":"SYNTHETIC-QA-SECOND"}]','{"synthetic qa":1}','{}');
 perform public.save_reviewed_annotations('[]','{"synthetic qa":2}','{"synthetic qa":"Soft"}');
 if (select count(*) from public.research_annotations where normalized_phrase='synthetic qa' and label='Soft')<>2 then raise exception 'Category reconciliation failed'; end if;
 blocked:=false;
 begin update public.research_annotations set label='Forged' where normalized_phrase='synthetic qa';
 exception when insufficient_privilege then blocked:=true; end;
 if not blocked then raise exception 'Direct write bypassed review RPC'; end if;
 if not exists(select 1 from public.annotation_audit where new_row->>'normalized_phrase'='synthetic qa') then raise exception 'Missing audit'; end if;
end $$;
reset role;
select set_config('request.jwt.claim.sub',(select user_id::text from public.research_members where role='reviewer' and active limit 1),true);
set local role authenticated;
do $$
declare saved integer; blocked boolean:=false;
begin
 if public.workspace_role()<>'reviewer' then raise exception 'Reviewer membership failed'; end if;
 if (select count(*) from public.research_annotations where normalized_phrase='synthetic qa')<>2 then raise exception 'Reviewer cannot read team labels'; end if;
 saved:=public.save_reviewed_annotations('[{"phrase":"SYNTHETIC REVIEWER QA","normalized_phrase":"synthetic reviewer qa","label":"Data","source_type":"jobs","source_id":"SYNTHETIC-REVIEWER-QA"}]','{}','{}');
 if saved<>1 then raise exception 'Reviewer cannot save reviewed annotations'; end if;
 begin insert into public.app_state(name,payload) values('synthetic-forbidden','{}');
 exception when insufficient_privilege then blocked:=true; end;
 if not blocked then raise exception 'Reviewer gained admin-only data permissions'; end if;
end $$;
reset role;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000000',true);
set local role authenticated;
do $$
begin
 if public.workspace_role() is not null then raise exception 'Nonmember has a role'; end if;
 if exists(select 1 from public.research_annotations) then raise exception 'Nonmember can read labels'; end if;
 begin
  perform public.save_reviewed_annotations('[]','{}','{}');
  raise exception 'Nonmember can write';
 exception when insufficient_privilege then null; end;
end $$;
rollback;
select 'PASS: membership, training lease, stale saves, category reconciliation, direct-write denial, audit, nonmember isolation (all test rows rolled back)' as result;
