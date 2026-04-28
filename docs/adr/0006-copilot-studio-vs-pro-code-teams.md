# ADR 0006 — Pro-Code Web UI for POC; Defer Copilot Studio and Teams App

**Status**: Accepted (POC). Hybrid revisit at production.
**Date**: 2026-04-24

## Context

Architecture §9 + §10 propose Copilot Studio (low-code, Teams-native) as a fast POC option, and a pro-code Teams Toolkit + Bot Framework app for production. We need a chat surface for the POC.

## Decision

For POC: ship a single-page web UI on Static Web Apps Standard with built-in Entra ID auth. No Copilot Studio agent and no Teams app at POC.

Document the Copilot Studio + Power Automate alternatives in [`../poc/06-low-code-alternatives.md`](../poc/06-low-code-alternatives.md) with constraints, so we know exactly when to revisit.

## Consequences

- Full control over router, citation rendering, and clause-comparison UI.
- Faster iteration on the prompts and retrieval logic without designer-tier friction.
- Loses Teams/M365 distribution for stakeholders. Mitigation: revisit hybrid (pro-code pipeline + Copilot Studio plugin) post-POC.
- Auth is single-tenant Entra ID — uses SWA's built-in provider, zero custom code.

## When to Revisit

- Stakeholders need Teams distribution before pro-code Teams app is built
- M365 Copilot becomes the org's standard chat surface
- Power Platform team is doing the build (low-code path becomes natural)
