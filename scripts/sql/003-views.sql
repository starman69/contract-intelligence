-- Views and stored procedures used by the router's "reporting" path.
-- Keep this file fast to evolve — the API binds to these names.

SET NOCOUNT ON;
GO

-- ====================================================================
-- View: contracts expiring within a window
-- ====================================================================
CREATE OR ALTER VIEW dbo.vContractsExpiring AS
SELECT
    c.ContractId,
    c.ContractTitle,
    c.Counterparty,
    c.ContractType,
    c.ExpirationDate,
    c.RenewalDate,
    c.AutoRenewalFlag,
    c.GoverningLaw,
    c.LegalOwner,
    c.BusinessOwner,
    c.Status,
    c.SharePointUrl,
    c.BlobUri,
    DATEDIFF(DAY, GETUTCDATE(), c.ExpirationDate) AS DaysUntilExpiration
FROM dbo.Contract c
WHERE c.ExpirationDate IS NOT NULL
  AND c.Status = N'active';
GO

-- ====================================================================
-- View: clauses flagged as high-deviation from gold
-- ====================================================================
CREATE OR ALTER VIEW dbo.vNonStandardClauses AS
SELECT
    cc.ClauseId,
    cc.ContractId,
    c.ContractTitle,
    c.Counterparty,
    c.ContractType,
    cc.ClauseType,
    cc.PageNumber,
    cc.SectionHeading,
    cc.RiskLevel,
    cc.DeviationScore,
    cc.StandardClauseId,
    cc.ReviewStatus
FROM dbo.ContractClause cc
JOIN dbo.Contract c ON c.ContractId = cc.ContractId
WHERE cc.DeviationScore IS NOT NULL
  AND cc.DeviationScore > 0.3;
GO

-- ====================================================================
-- Procedure: parameterized expiring-contracts query (router uses this)
-- ====================================================================
CREATE OR ALTER PROCEDURE dbo.usp_ContractsExpiringWithin
    @Days INT,
    @ContractType NVARCHAR(128) = NULL,
    @LegalOwner NVARCHAR(256) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    SELECT *
    FROM dbo.vContractsExpiring
    WHERE DaysUntilExpiration BETWEEN 0 AND @Days
      AND (@ContractType IS NULL OR ContractType = @ContractType)
      AND (@LegalOwner   IS NULL OR LegalOwner   = @LegalOwner)
    ORDER BY ExpirationDate ASC;
END
GO

-- ====================================================================
-- Procedure: contracts with auto-renewal
-- ====================================================================
CREATE OR ALTER PROCEDURE dbo.usp_ContractsWithAutoRenewal
    @ContractType NVARCHAR(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        ContractId, ContractTitle, Counterparty, ContractType,
        EffectiveDate, ExpirationDate, RenewalDate,
        LegalOwner, BlobUri, SharePointUrl, Status
    FROM dbo.Contract
    WHERE AutoRenewalFlag = 1
      AND Status = N'active'
      AND (@ContractType IS NULL OR ContractType = @ContractType)
    ORDER BY ExpirationDate ASC;
END
GO

-- ====================================================================
-- Procedure: contracts missing a metadata field (review queue helper)
-- ====================================================================
CREATE OR ALTER PROCEDURE dbo.usp_ContractsMissingField
    @FieldName NVARCHAR(128)
AS
BEGIN
    SET NOCOUNT ON;

    IF @FieldName = N'ExpirationDate'
        SELECT ContractId, ContractTitle, Counterparty, ReviewStatus FROM dbo.Contract WHERE ExpirationDate IS NULL;
    ELSE IF @FieldName = N'GoverningLaw'
        SELECT ContractId, ContractTitle, Counterparty, ReviewStatus FROM dbo.Contract WHERE GoverningLaw IS NULL;
    ELSE IF @FieldName = N'Counterparty'
        SELECT ContractId, ContractTitle, ContractType, ReviewStatus FROM dbo.Contract WHERE Counterparty IS NULL;
    ELSE
        THROW 51000, 'Unsupported FieldName. Add a branch above.', 1;
END
GO

PRINT 'Views and stored procedures created.';
GO
