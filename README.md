# Specimen Digitization Platform

A Flutter and Firebase application for converting natural-history specimen images into evidence-backed, reviewable digital records. The first pilot targets the Field Museum Insects subcollection.

The selected processing architecture uses Temporal for durable specimen workflows and Pydantic AI for typed, collection-specific agent harnesses.

## Current status

Product definition and architecture setup. Application implementation has not started.

## Documentation

- [Product requirements](docs/product-requirements/PRD.md)
- [Agent harness decision and alternatives](docs/product-requirements/HARNESS_OPTIONS.md)
- [Validated GBIF integration strategy](docs/GBIF.md)
- [Field Museum EMu Parties and IRN availability check](docs/product-requirements/EMU_PARTIES_IRN_RESEARCH.md)

## Safe local setup

1. Copy `.env.example` to `.env` and fill credentials locally.
2. Never commit `.env`, cloud credential files, museum images, raw transcripts, or production exports.
3. Install both Git hooks:

   ```bash
   pre-commit install --hook-type pre-commit --hook-type pre-push
   ```

4. Run all safety checks before a commit or push:

   ```bash
   pre-commit run --all-files
   ```

Use short-lived, least-privilege development credentials. Production BYOK credentials will live in a cloud secret manager and will be referenced by identifier rather than stored in Firestore or local configuration.
