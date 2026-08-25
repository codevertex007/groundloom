# ADR-031: Bounded OCR provider boundary

**Status:** Accepted  
**Date:** 2026-08-25

## Context

PDF text extraction cannot read image-only/scanned pages. Treating an empty
extract as a successful source or fabricating local OCR would create
unsupported evidence and hide an infrastructure dependency.

## Decision

The ingestion state machine includes an explicit `ocr` stage for PDF versions
whose safe parser produces no text. The local adapter fails with a typed
configuration error and never claims OCR success. Deployments may configure a
narrow HTTP sidecar that receives bounded source bytes and returns only a
bounded `{text}` result; timeouts, outages, rejected requests, and malformed
responses use the standard typed dependency boundary. OCR output is then fed
through the same normalization, embedding, indexing, and lineage path as
parser output.

## Consequences

Scanned PDFs remain visibly incomplete in local development until an OCR
provider is configured. Production startup requires an explicit OCR provider,
while OCR credentials and service capacity remain deployment-owned.

## Validation

`backend/tests/test_ocr.py` covers the HTTP request contract, bounded result
validation, outage/configuration errors, and ingestion-stage integration.
