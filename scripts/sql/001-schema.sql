-- Contract Intelligence POC — SQL schema
-- Target: Azure SQL Database (Serverless GP_S_Gen5_1) with AAD-only auth
-- Run after deploy: sqlcmd -S <server>.database.windows.net -d sqldb-contracts -G -i 001-schema.sql

SET NOCOUNT ON;
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

-- ====================================================================
-- AAD users for Function App managed identities.
-- Replace the names below with the actual Function App resource names
-- (the Function App's display name = its resource name on Azure).
-- These statements should be executed by the AAD admin (group) once
-- the Function Apps exist; they are commented out so the script is
-- idempotent and safe to re-run during development.
-- ====================================================================

-- CREATE USER [func-contracts-ingest-dev-xxxxxx] FROM EXTERNAL PROVIDER;
-- ALTER ROLE db_datareader ADD MEMBER [func-contracts-ingest-dev-xxxxxx];
-- ALTER ROLE db_datawriter ADD MEMBER [func-contracts-ingest-dev-xxxxxx];
-- ALTER ROLE db_ddladmin ADD MEMBER [func-contracts-ingest-dev-xxxxxx];

-- CREATE USER [func-contracts-api-dev-xxxxxx] FROM EXTERNAL PROVIDER;
-- ALTER ROLE db_datareader ADD MEMBER [func-contracts-api-dev-xxxxxx];

-- ====================================================================
-- Tables
-- ====================================================================

IF OBJECT_ID('dbo.Contract', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Contract (
        ContractId               UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_Contract PRIMARY KEY DEFAULT NEWID(),
        SharePointDriveItemId    NVARCHAR(128)    NULL,
        SharePointSiteId         NVARCHAR(128)    NULL,
        SharePointUrl            NVARCHAR(2048)   NULL,
        BlobUri                  NVARCHAR(2048)   NOT NULL,
        FileHash                 CHAR(64)         NOT NULL, -- SHA-256 hex
        FileVersion              NVARCHAR(64)     NOT NULL,
        ContractTitle            NVARCHAR(512)    NULL,
        ContractType             NVARCHAR(128)    NULL,    -- e.g. supplier, employment, license
        Counterparty             NVARCHAR(512)    NULL,
        EffectiveDate            DATE             NULL,
        ExpirationDate           DATE             NULL,
        RenewalDate              DATE             NULL,
        AutoRenewalFlag          BIT              NULL,
        GoverningLaw             NVARCHAR(128)    NULL,
        Jurisdiction             NVARCHAR(128)    NULL,
        ContractValue            DECIMAL(18, 2)   NULL,
        Currency                 CHAR(3)          NULL,
        BusinessOwner            NVARCHAR(256)    NULL,
        LegalOwner               NVARCHAR(256)    NULL,
        Status                   NVARCHAR(64)     NOT NULL CONSTRAINT DF_Contract_Status DEFAULT N'active',
        ExtractionConfidence     DECIMAL(5, 4)    NULL,
        ReviewStatus             NVARCHAR(64)     NOT NULL CONSTRAINT DF_Contract_ReviewStatus DEFAULT N'unreviewed',
        MetadataVersion          INT              NOT NULL CONSTRAINT DF_Contract_MetadataVersion DEFAULT 1,
        ExtractionVersion        INT              NOT NULL CONSTRAINT DF_Contract_ExtractionVersion DEFAULT 1,
        SearchIndexVersion       INT              NOT NULL CONSTRAINT DF_Contract_SearchIndexVersion DEFAULT 1,
        CreatedAt                DATETIME2(3)     NOT NULL CONSTRAINT DF_Contract_CreatedAt DEFAULT SYSUTCDATETIME(),
        UpdatedAt                DATETIME2(3)     NOT NULL CONSTRAINT DF_Contract_UpdatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_Contract_FileVersion UNIQUE (FileHash, FileVersion)
    );

    CREATE INDEX IX_Contract_ExpirationDate    ON dbo.Contract (ExpirationDate) INCLUDE (ContractTitle, Counterparty, Status);
    CREATE INDEX IX_Contract_Counterparty      ON dbo.Contract (Counterparty);
    CREATE INDEX IX_Contract_ContractType      ON dbo.Contract (ContractType);
    CREATE INDEX IX_Contract_Status_Expiration ON dbo.Contract (Status, ExpirationDate);
    CREATE INDEX IX_Contract_ReviewStatus      ON dbo.Contract (ReviewStatus);
END
GO

IF OBJECT_ID('dbo.StandardClause', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.StandardClause (
        StandardClauseId   NVARCHAR(128)    NOT NULL CONSTRAINT PK_StandardClause PRIMARY KEY,
        ClauseType         NVARCHAR(128)    NOT NULL,
        Version            INT              NOT NULL,
        ApprovedText       NVARCHAR(MAX)    NOT NULL,
        Jurisdiction       NVARCHAR(128)    NULL,
        BusinessUnit       NVARCHAR(128)    NULL,
        EffectiveFrom      DATE             NOT NULL,
        EffectiveTo        DATE             NULL,
        RiskPolicy         NVARCHAR(MAX)    NULL,
        ReviewOwner        NVARCHAR(256)    NULL,
        CreatedAt          DATETIME2(3)     NOT NULL CONSTRAINT DF_StandardClause_CreatedAt DEFAULT SYSUTCDATETIME()
    );

    CREATE INDEX IX_StandardClause_Type ON dbo.StandardClause (ClauseType, Jurisdiction, EffectiveFrom DESC);
END
GO

IF OBJECT_ID('dbo.ContractClause', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ContractClause (
        ClauseId             UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_ContractClause PRIMARY KEY DEFAULT NEWID(),
        ContractId           UNIQUEIDENTIFIER NOT NULL,
        ClauseType           NVARCHAR(128)    NULL,
        ClauseText           NVARCHAR(MAX)    NOT NULL,
        PageNumber           INT              NULL,
        BoundingBox          NVARCHAR(256)    NULL, -- JSON: x,y,w,h or polygon
        SectionHeading       NVARCHAR(512)    NULL,
        StandardClauseId     NVARCHAR(128)    NULL,
        DeviationScore       DECIMAL(5, 4)    NULL,
        RiskLevel            NVARCHAR(16)     NULL, -- low | medium | high
        ExtractionConfidence DECIMAL(5, 4)    NULL,
        ReviewedBy           NVARCHAR(256)    NULL,
        ReviewStatus         NVARCHAR(64)     NOT NULL CONSTRAINT DF_ContractClause_ReviewStatus DEFAULT N'unreviewed',
        CreatedAt            DATETIME2(3)     NOT NULL CONSTRAINT DF_ContractClause_CreatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_ContractClause_Contract       FOREIGN KEY (ContractId)       REFERENCES dbo.Contract (ContractId)       ON DELETE CASCADE,
        CONSTRAINT FK_ContractClause_StandardClause FOREIGN KEY (StandardClauseId) REFERENCES dbo.StandardClause (StandardClauseId)
    );

    CREATE INDEX IX_ContractClause_Contract_Type ON dbo.ContractClause (ContractId, ClauseType);
    CREATE INDEX IX_ContractClause_Risk          ON dbo.ContractClause (RiskLevel) WHERE RiskLevel IS NOT NULL;
    CREATE INDEX IX_ContractClause_StandardClause ON dbo.ContractClause (StandardClauseId);
END
GO

IF OBJECT_ID('dbo.ContractObligation', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ContractObligation (
        ObligationId    UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_ContractObligation PRIMARY KEY DEFAULT NEWID(),
        ContractId      UNIQUEIDENTIFIER NOT NULL,
        Party           NVARCHAR(256)    NULL,
        ObligationText  NVARCHAR(MAX)    NOT NULL,
        DueDate         DATE             NULL,
        Frequency       NVARCHAR(64)     NULL, -- one-time | monthly | quarterly | annually
        TriggerEvent    NVARCHAR(512)    NULL,
        RiskLevel       NVARCHAR(16)     NULL,
        CreatedAt       DATETIME2(3)     NOT NULL CONSTRAINT DF_ContractObligation_CreatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_ContractObligation_Contract FOREIGN KEY (ContractId) REFERENCES dbo.Contract (ContractId) ON DELETE CASCADE
    );

    CREATE INDEX IX_ContractObligation_Contract ON dbo.ContractObligation (ContractId);
    CREATE INDEX IX_ContractObligation_DueDate  ON dbo.ContractObligation (DueDate) WHERE DueDate IS NOT NULL;
END
GO

IF OBJECT_ID('dbo.IngestionJob', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.IngestionJob (
        JobId           UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_IngestionJob PRIMARY KEY DEFAULT NEWID(),
        ContractId      UNIQUEIDENTIFIER NULL,
        BlobUri         NVARCHAR(2048)   NOT NULL,
        Status          NVARCHAR(32)     NOT NULL, -- queued | running | success | failed
        ErrorMessage    NVARCHAR(MAX)    NULL,
        StartedAt       DATETIME2(3)     NOT NULL CONSTRAINT DF_IngestionJob_StartedAt DEFAULT SYSUTCDATETIME(),
        CompletedAt     DATETIME2(3)     NULL,
        Attempt         INT              NOT NULL CONSTRAINT DF_IngestionJob_Attempt DEFAULT 1,
        ExtractionVersion INT            NULL,
        CONSTRAINT FK_IngestionJob_Contract FOREIGN KEY (ContractId) REFERENCES dbo.Contract (ContractId)
    );

    CREATE INDEX IX_IngestionJob_Status ON dbo.IngestionJob (Status, StartedAt DESC);
    CREATE INDEX IX_IngestionJob_BlobUri ON dbo.IngestionJob (BlobUri);
END
GO

IF OBJECT_ID('dbo.QueryAudit', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.QueryAudit (
        AuditId         UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_QueryAudit PRIMARY KEY DEFAULT NEWID(),
        QuestionText    NVARCHAR(2000)   NOT NULL,
        Intent          NVARCHAR(64)     NULL,
        DataSourcesJson NVARCHAR(256)    NULL,
        Confidence      DECIMAL(5, 4)    NULL,
        FallbackReason  NVARCHAR(64)     NULL,
        CitationsJson   NVARCHAR(MAX)    NULL,
        ElapsedMs       INT              NOT NULL CONSTRAINT DF_QueryAudit_ElapsedMs DEFAULT 0,
        Status          NVARCHAR(32)     NOT NULL,  -- success | error
        ErrorMessage    NVARCHAR(MAX)    NULL,
        CorrelationId   NVARCHAR(64)     NULL,
        UserPrincipal   NVARCHAR(256)    NULL,
        CreatedAt       DATETIME2(3)     NOT NULL CONSTRAINT DF_QueryAudit_CreatedAt DEFAULT SYSUTCDATETIME()
    );

    CREATE INDEX IX_QueryAudit_Status_CreatedAt ON dbo.QueryAudit (Status, CreatedAt DESC);
    CREATE INDEX IX_QueryAudit_Intent_CreatedAt ON dbo.QueryAudit (Intent, CreatedAt DESC);
    CREATE INDEX IX_QueryAudit_Correlation     ON dbo.QueryAudit (CorrelationId);
END
GO

IF OBJECT_ID('dbo.ExtractionAudit', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ExtractionAudit (
        AuditId            UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_ExtractionAudit PRIMARY KEY DEFAULT NEWID(),
        ContractId         UNIQUEIDENTIFIER NOT NULL,
        FieldName          NVARCHAR(128)    NOT NULL,
        FieldValue         NVARCHAR(MAX)    NULL,
        SourceClauseId     UNIQUEIDENTIFIER NULL,
        SourceQuote        NVARCHAR(MAX)    NULL,
        SourcePage         INT              NULL,
        Confidence         DECIMAL(5, 4)    NULL,
        ExtractionMethod   NVARCHAR(64)     NULL, -- llm | regex | doc-intelligence | manual
        ModelName          NVARCHAR(128)    NULL,
        ModelVersion       NVARCHAR(64)     NULL,
        PromptVersion      NVARCHAR(64)     NULL,
        CreatedAt          DATETIME2(3)     NOT NULL CONSTRAINT DF_ExtractionAudit_CreatedAt DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_ExtractionAudit_Contract FOREIGN KEY (ContractId) REFERENCES dbo.Contract (ContractId) ON DELETE CASCADE
    );

    CREATE INDEX IX_ExtractionAudit_Contract_Field ON dbo.ExtractionAudit (ContractId, FieldName);
END
GO

-- ====================================================================
-- Token-usage columns. Idempotent ALTERs so existing deployments pick up
-- the new columns without dropping the table. Populated by `_persist_query_audit`
-- (api.py) and `_complete_job` (pipeline.py) via `shared.token_ledger`.
-- ====================================================================

IF COL_LENGTH('dbo.QueryAudit', 'PromptTokens') IS NULL
    ALTER TABLE dbo.QueryAudit ADD PromptTokens INT NULL;
IF COL_LENGTH('dbo.QueryAudit', 'CompletionTokens') IS NULL
    ALTER TABLE dbo.QueryAudit ADD CompletionTokens INT NULL;
IF COL_LENGTH('dbo.QueryAudit', 'EmbeddingTokens') IS NULL
    ALTER TABLE dbo.QueryAudit ADD EmbeddingTokens INT NULL;
IF COL_LENGTH('dbo.QueryAudit', 'EstimatedCostUsd') IS NULL
    ALTER TABLE dbo.QueryAudit ADD EstimatedCostUsd DECIMAL(12, 8) NULL;
GO

IF COL_LENGTH('dbo.IngestionJob', 'ExtractionPromptTokens') IS NULL
    ALTER TABLE dbo.IngestionJob ADD ExtractionPromptTokens INT NULL;
IF COL_LENGTH('dbo.IngestionJob', 'ExtractionCompletionTokens') IS NULL
    ALTER TABLE dbo.IngestionJob ADD ExtractionCompletionTokens INT NULL;
IF COL_LENGTH('dbo.IngestionJob', 'EmbeddingTokens') IS NULL
    ALTER TABLE dbo.IngestionJob ADD EmbeddingTokens INT NULL;
IF COL_LENGTH('dbo.IngestionJob', 'EstimatedCostUsd') IS NULL
    ALTER TABLE dbo.IngestionJob ADD EstimatedCostUsd DECIMAL(12, 8) NULL;
GO

PRINT 'Schema applied.';
GO
