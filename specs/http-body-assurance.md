# Strict typing and coverage for shared HTTP body framing

The shared request reader must preserve strict JSON validation, reject ambiguous
framing, restore the caller's socket timeout, and retain partial-read accounting.
Use structural types for the headers, connection and byte stream. Parsed JSON is
untrusted until a route validates it.

Run Pyright strict for this module and reject new untyped public functions.
The existing coverage job must enforce separate per-module floors of 95% line
and 90% branch coverage. Missing modules and malformed reports fail the job.
Existing schedule authority floors and mutation checks remain in effect.

This slice covers the shared body reader, not all HTTP routes or the whole core.
