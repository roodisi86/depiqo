-- Depiqo platform, migration 006 (version 0.4.0): provider registry for deposits held elsewhere
-- and the confirmation of a release at that provider.
-- Runs statement by statement. No semicolons inside strings or comments.

-- Where a deposit held elsewhere (holding = 'external') actually sits. NULL means not known yet.
--   verhuurder_rekening  rekening van verhuurder of beheerder
--   bank_geblokkeerd     geblokkeerde rekening bij een bank op naam van de huurder
--   e_depo               Deposito- en Consignatiekas
--   verzekering_tak26    kapitalisatiecontract bij een verzekeraar
--   borggarantie         garantie of borgstelling door een derde (geen geld gestort)
--   ocmw                 waarborg via OCMW of lokaal bestuur (BE)
--   anders               iets anders
ALTER TABLE deposits ADD COLUMN provider_kind TEXT CHECK (provider_kind IN ('verhuurder_rekening', 'bank_geblokkeerd', 'e_depo', 'verzekering_tak26', 'borggarantie', 'ocmw', 'anders'));
ALTER TABLE deposits ADD COLUMN provider_name TEXT;
ALTER TABLE deposits ADD COLUMN provider_reference TEXT;
ALTER TABLE deposits ADD COLUMN guarantee_expires_on TEXT;

-- The proof that the provider released the deposit (a document of kind 'vrijgave').
ALTER TABLE deposits ADD COLUMN release_document_id INTEGER REFERENCES documents(id);

CREATE INDEX idx_deposits_org_provider ON deposits (org_id, holding, provider_kind)

-- No backfill on purpose: for deposits held elsewhere before 0.4.0 Depiqo does not know the provider.
-- They show as "aanbieder onbekend" on the dashboard and as an exception in the reconciliation
-- until someone records the provider on the deposit.
