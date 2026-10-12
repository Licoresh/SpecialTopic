-- Explicit deny policy: only the guarded private function manages this lease.
create policy no_direct_lease_access on research_private.training_lease for all to authenticated using (false) with check (false);
