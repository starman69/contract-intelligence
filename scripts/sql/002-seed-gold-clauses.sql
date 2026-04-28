-- Seed the StandardClause table from samples/gold-clauses/*.md.
-- This is a manual seed for the 7 POC clause types. Production will load
-- via a versioned data-migration job.

SET NOCOUNT ON;
GO

MERGE dbo.StandardClause AS T
USING (VALUES
    (N'gc-indemnity-us-v1',
     N'indemnity', 1,
     N'See samples/gold-clauses/indemnity.md (full text loaded by an out-of-band script).',
     N'US', N'enterprise', '2026-01-01', NULL,
     N'mutual; IP carve-outs mandatory; deviations require Legal sign-off',
     N'legal-contracts'),

    (N'gc-lol-us-v1',
     N'limitation_of_liability', 1,
     N'See samples/gold-clauses/limitation-of-liability.md.',
     N'US', N'enterprise', '2026-01-01', NULL,
     N'mutual cap; 12-month look-back; $100K floor; 4 mandatory exclusions',
     N'legal-contracts'),

    (N'gc-termination-us-v1',
     N'termination', 1,
     N'See samples/gold-clauses/termination.md.',
     N'US', N'enterprise', '2026-01-01', NULL,
     N'30-day notice; cure window; survival list; 90-day data export window',
     N'legal-contracts'),

    (N'gc-confidentiality-us-v1',
     N'confidentiality', 1,
     N'See samples/gold-clauses/confidentiality.md.',
     N'US', N'enterprise', '2026-01-01', NULL,
     N'5-year survival; trade-secret perpetual; compelled-disclosure carve-out',
     N'legal-contracts'),

    (N'gc-governing-law-us-ny-v1',
     N'governing_law', 1,
     N'See samples/gold-clauses/governing-law.md.',
     N'US-NY', N'enterprise', '2026-01-01', NULL,
     N'NY default; equitable-relief carve-out non-negotiable',
     N'legal-contracts'),

    (N'gc-auto-renewal-us-v1',
     N'auto_renewal', 1,
     N'See samples/gold-clauses/auto-renewal.md.',
     N'US', N'enterprise', '2026-01-01', NULL,
     N'default = no auto-renewal; 60-day notice if permitted; price cap mandatory',
     N'legal-contracts'),

    (N'gc-audit-rights-us-v1',
     N'audit_rights', 1,
     N'See samples/gold-clauses/audit-rights.md.',
     N'US', N'enterprise', '2026-01-01', NULL,
     N'1x/12mo; 30-day notice; SOC 2/ISO substitution; security-incident exception',
     N'legal-contracts'),

    (N'gc-non-solicitation-us-v1',
     N'non_solicitation', 1,
     N'See samples/gold-clauses/non-solicitation.md.',
     N'US', N'enterprise', '2026-01-01', NULL,
     N'12-month restricted period; "material contact" qualifier mandatory; general-advertising and 6-month-cooled-off carve-outs non-negotiable',
     N'legal-contracts'),

    (N'gc-return-of-information-us-v1',
     N'return_of_information', 1,
     N'See samples/gold-clauses/return-of-information.md.',
     N'US', N'enterprise', '2026-01-01', NULL,
     N'30-day return/destroy window; written certification mandatory; legal-archive + automated-backup retention carve-outs non-negotiable',
     N'legal-contracts')
) AS S (StandardClauseId, ClauseType, Version, ApprovedText, Jurisdiction, BusinessUnit, EffectiveFrom, EffectiveTo, RiskPolicy, ReviewOwner)
ON T.StandardClauseId = S.StandardClauseId
WHEN NOT MATCHED BY TARGET THEN
    INSERT (StandardClauseId, ClauseType, Version, ApprovedText, Jurisdiction, BusinessUnit, EffectiveFrom, EffectiveTo, RiskPolicy, ReviewOwner)
    VALUES (S.StandardClauseId, S.ClauseType, S.Version, S.ApprovedText, S.Jurisdiction, S.BusinessUnit, S.EffectiveFrom, S.EffectiveTo, S.RiskPolicy, S.ReviewOwner)
WHEN MATCHED AND T.ApprovedText <> S.ApprovedText THEN
    UPDATE SET
        ApprovedText = S.ApprovedText,
        RiskPolicy = S.RiskPolicy;
GO

-- The full markdown text of each gold clause is loaded by an out-of-band Python
-- script (see scripts/data-prep/) which reads samples/gold-clauses/*.md and
-- updates StandardClause.ApprovedText. The MERGE above creates the rows with
-- a pointer-style placeholder so SQL constraints are satisfied.
PRINT 'Gold clause seed applied. Run loader script to populate ApprovedText.';
GO
