create or replace function public.clear_generated_extractions()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare removed integer;
begin
 if auth.uid() is null or not exists (
   select 1 from public.research_members
   where user_id = auth.uid() and active and role = 'admin'
 ) then
  raise exception 'Active research administrator membership is required'
   using errcode = '42501';
 end if;

 delete from public.app_state
 where name in ('frame:extractions_original', 'frame:nlp_processed', 'json:extraction_metadata')
    or name like 'frame:extractions_original:chunk:%'
    or name like 'frame:nlp_processed:chunk:%';
 get diagnostics removed = row_count;
 return removed;
end;
$$;

revoke all on function public.clear_generated_extractions() from public, anon;
grant execute on function public.clear_generated_extractions() to authenticated;
