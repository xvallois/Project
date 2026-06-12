# ADR 0008 — Labeled stub provider behind the model seam
**Status** accepted (Phase 2) · **Decision** `AnalystProvider` seam with
`AnthropicProvider` (live) and `StubProvider` (deterministic, templated,
always labeled "stub" in data and UI). Tests + keyless environments run
the stub through the identical gate/budget/persistence path.
**Why** the contract must be testable without a key and the user must
never mistake templated prose for Claude.
