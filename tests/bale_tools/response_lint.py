#!/usr/bin/env python3
"""response_lint.py — mechanical self-check for a bale response directory.

A WORKER runs this against its own response-NNN/ directory before
packing, without bale installed. It executes the TARBALL.md §10.1
step-10 self-check as code instead of discipline, and it is the tool
that catches compaction-corrupted manifests at the source (AGENT.md
§11.6's re-derivation duty, mechanized).

Checks are authored from the DOCUMENTED contract — TARBALL.md §5.2,
§5.2.1, §5.3, §5.6.1, §5.9.2, §10.1 — and the two schema files under
schemas/, NOT from bale_validate. This is a deliberately independent
second implementation of the written contract (ADR-0002's rejection
of the self-oracle, applied to pre-pack linting).

Usage:
    response_lint.py <response-dir> [--json | --emit-feedback-mechanical]
                     [--request FILE] [--schema-dir DIR]

--emit-feedback-mechanical prints the paste-ready feedback.mechanical
object on stdout (the TARBALL.md §5.2.2 fill-by-running-the-lint
workflow, mechanized): every field is this run's own computation —
the same derivation the feedback-block check verifies a shipped block
against — never a transcription. The two optional members
(linkage, provenance) are not emitted, because neither is
lint-computable: provenance is seeded into the manifest skeleton by
tools/craft_response.py's --request (the request's provenance echoed
verbatim plus an empty model_identity the worker fills), and linkage
the worker adds by hand when the session went through a probe or
clarification round. Pasting this object over the seeded block's four
lint-computable placeholders, key for key, leaves both in place. The
flag exits 0 whenever the object was written, findings or not: its
typical input is a crafter-seeded block whose four placeholders are
the run's only findings, and a worker chaining `emit && paste` must
reach the paste. The findings still print on stderr and the plain
re-run after the paste is the verdict; when no object could be
emitted (manifest.json unavailable) it exits 1 (wave 10's tools micro).

--request FILE names the request's manifest.json, the lint's only view
of the request, and enables two warning-tier checks (TARBALL.md §3.2,
§5.4): `forecast-departures` names every changes[] path outside the
request's resolved_scope (directory entries covering their subtrees)
that no feedback.self_reported.forecast_departures entry names
(FORECAST_DEPARTURE_UNDECLARED — a warning, because the path may be
drift the operator admits at apply, where bale's own-forecast gate
enforces) and, conversely, every declared entry that is not a
departure — its path inside resolved_scope, or naming no changes[]
path (FORECAST_DEPARTURE_NOT_A_DEPARTURE, same tier) — and
`readme-in-docs-read` warns README_NOT_IN_DOCS_READ
when the request's `readme` key is non-null (a brief shipped) and no
docs_read entry names README.md. Without the flag both report [SKIP].

Exit codes:
    0  clean — every check passed (warnings, if any, are printed but
       never flip the exit code or the report's `ok`); under
       --emit-feedback-mechanical, the object was written
    1  findings — at least one contract violation, all of them named;
       under --emit-feedback-mechanical, no object could be emitted
    2  the lint itself errored (bad usage, unreadable dir, unreadable
       --request file)

Two checks guard the self-check against the request's own layout and
clock (v0.4.30; TARBALL.md §1 and §3.1): `context-prefix`
flags a changes[] path carrying the tarball-layout `context/` prefix
(a finding — bale would land it at the wrong place) and a
feedback.self_reported.docs_read entry carrying it (a warning — the
stats read side sees two spellings of one path); `dated-artifacts`
flags a dated artifact the response authors whose date is not the
session id's date — a created .md carrying DOCS.md §5's
`- **Date:** YYYY-MM-DD` header must carry the sid's date, and a
modified one must carry no dated line later than it. Warnings are a
separate tier: reported as [WARN] with their own `warnings[]` in the
JSON report, never counted as findings.

`claims-value` files CLAIMS_VALUE for a bare-string claims
value outside pass|fail|untested|unknown — the vocabulary bale's apply
enforces in Python, which the embedded schema does not express for the
bare-string form (a split that predates the subset validator's oneOf).
Before it, such a value linted clean and refused at apply.
`docs-read-stub` warns DOCS_READ_EMPTY_STUB when
feedback.self_reported.docs_read is present and exactly [] — the
crafter's seeded stub shipped unfilled: fill it or delete the key.
Omission (reported nothing) stays silent.

Output:
    Default: human-readable report on stdout, every failure named
    with path, expected, and got — never first-failure-only.
    --json:  one JSON line on stdout (stable keys for an orchestrator);
    the human-readable findings move to stderr.

Schemas:
    Verbatim copies of schemas/response-manifest.schema.json and
    schemas/diagnostics.schema.json are embedded below so the file is
    standalone. If the project's schema files evolve, refresh the
    embedded copies (they are JSON-equal to the source files), or
    point --schema-dir at a directory containing the two files to
    override the embedded copies at runtime. validate.sh asserts the
    JSON-equality on every run, so a schema edit that forgets the
    refresh fails install validation loudly rather than drifting.

Stdlib only. Python 3.10+. No network. No bale imports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2

VALID_KINDS = ("normal", "bailout", "clarification")

# ---------------------------------------------------------------------------
# Embedded schemas — verbatim copies of the files named in the header.
# ---------------------------------------------------------------------------

RESPONSE_MANIFEST_SCHEMA_JSON = r"""
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/anthropics/bale/schemas/response-manifest.schema.json",
  "title": "bale response manifest",
  "description": "Shape of response-NNN/manifest.json per TARBALL.md sections 5.2, 5.6.2, and 5.9.2. Field semantics live in TARBALL.md; this schema constrains only the universal envelope. Cross-field invariants (sha256 file match, path-safety, claims subset of validation_will_run, stripped-non-empty reasons, bailout-shape and clarification-shape rules) stay in bale's Python validators.",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "session_id",
    "responds_to",
    "corrects",
    "summary",
    "changes",
    "deferred",
    "validation_will_run",
    "claims"
  ],
  "properties": {
    "session_id": {
      "type": "string",
      "minLength": 1,
      "description": "YYYY-MM-DD-<slug>-NNN per TARBALL.md section 1. For a normal response this equals responds_to; for a bailout it equals responds_to too, since the bailout is the answer to the same request; and for a clarification as well, since a clarification suspends rather than consumes its session (TARBALL.md section 5.9) and carries the same sid the eventual normal response will."
    },
    "responds_to": {
      "type": "string",
      "minLength": 1,
      "description": "Session ID of the request this response answers. Bale verifies it matches the locked session."
    },
    "corrects": {
      "type": ["string", "null"],
      "description": "Session ID of a prior response this re-attempts, or null."
    },
    "response_kind": {
      "type": "string",
      "enum": ["normal", "bailout", "clarification"],
      "description": "Optional, defaults to 'normal' if absent so v0.0.5-shaped manifests pass through. 'bailout' triggers TARBALL.md section 5.6's distinct shape; 'clarification' triggers section 5.9's (both enforced in Python)."
    },
    "summary": {
      "type": "string",
      "minLength": 1,
      "description": "One paragraph: what this response delivers."
    },
    "changes": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["path", "action", "reason", "size_bytes", "sha256"],
        "properties": {
          "path": {
            "type": "string",
            "minLength": 1,
            "description": "Repo-relative path. Path-safety (no traversal, no .git/.bale, no .baleignore match) is enforced in Python."
          },
          "action": {
            "type": "string",
            "enum": ["created", "modified", "deleted"]
          },
          "reason": {
            "type": "string",
            "minLength": 1,
            "description": "Non-empty. The stripped-non-empty rule is enforced in Python; this schema only catches the empty-string case."
          },
          "size_bytes": {
            "type": "integer",
            "minimum": 0
          },
          "sha256": {
            "type": ["string", "null"],
            "description": "Required string for created/modified; required null for deleted. The conditional rule is enforced in Python — this schema admits either."
          }
        }
      }
    },
    "deferred": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["what", "why"],
        "properties": {
          "what": { "type": "string", "minLength": 1 },
          "why":  { "type": "string", "minLength": 1 }
        }
      }
    },
    "validation_will_run": {
      "type": "array",
      "items": { "type": "string", "minLength": 1 },
      "description": "Declarative list of what validation.sh is configured to do. Strings are freeform — they're labels the user reads, not commands bale invokes."
    },
    "claims": {
      "type": "object",
      "description": "The worker's predictions for each project-level check. Keys are freeform check names (must be a subset of validation_will_run; enforced in Python). A value is the bare claim string ('pass', 'fail', 'untested', 'unknown'), or — from v0.4.7, the manifest carrier for the record-side shape — the annotated object form {\"value\": ..., \"claim_basis\": ...}, declaring at ship time whether the claim was predicted from structural grounds or observed from a real run; apply's verbatim promotion into the telemetry record's attempts[].validation.claims carries the object through unchanged. Bare-string values keep validating (everything additive). The bare-string enum is enforced in Python (validate_response_manifest) — the schema pins only the object form's shape here and the type alternatives, a division that predates the subset validator's oneOf (v0.4.42, for contract_docs) and stays as it is.",
      "additionalProperties": {
        "type": ["string", "object"],
        "additionalProperties": false,
        "required": ["value"],
        "properties": {
          "value": {
            "type": "string",
            "enum": ["pass", "fail", "untested", "unknown"],
            "description": "The claim itself — same vocabulary as the bare-string form."
          },
          "claim_basis": {
            "type": "string",
            "enum": ["predicted", "observed"],
            "description": "Optional, mirroring telemetry-record.schema.json's annotated claims form exactly: predicted from structural grounds, or observed from a real run before shipping. Omit the key when the basis is unknown — null is not a basis."
          }
        }
      }
    },
    "questions": {
      "type": "array",
      "description": "Blocking intent-gap questions per TARBALL.md section 5.9.2. Required and non-empty when response_kind='clarification'; on every other kind the block is absent or an EMPTY array (an empty array is tolerated, matching the doc's 'Forbidden (or empty)' wording — the doc is the contract of record; the conditional rule is enforced in Python — this schema only constrains entry shape).",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["question", "context", "default_assumption", "why_blocked"],
        "properties": {
          "question": {
            "type": "string",
            "minLength": 1,
            "description": "The question itself, stated so it can be answered in one short paragraph or less."
          },
          "context": {
            "type": "string",
            "minLength": 1,
            "description": "What the worker was trying to do when it hit the gap."
          },
          "default_assumption": {
            "type": "string",
            "minLength": 1,
            "description": "What the worker would have assumed absent an answer. Load-bearing: lets the planner answer with a single 'your assumption is correct'."
          },
          "why_blocked": {
            "type": "string",
            "minLength": 1,
            "description": "Why the worker declined to proceed on that assumption."
          },
          "options": {
            "type": "array",
            "minItems": 1,
            "items": { "type": "string", "minLength": 1 },
            "description": "Optional (v0.4.7): candidate answers, at least one when present — the asker's read of the choices, so the question arrives answerable. Doctrine: PLANNER.md §15. Legacy four-field rows without this key keep validating."
          },
          "recommendation": {
            "type": "string",
            "minLength": 1,
            "description": "Optional (v0.4.7): the worker's pick among the choices, extending default_assumption's cheapest-possible-answer role. Doctrine: PLANNER.md §15."
          },
          "priority": {
            "type": "string",
            "enum": ["blocking", "batched"],
            "description": "Optional (v0.4.7): PLANNER.md §15's two classes — only critical-path blockers interrupt; everything else batches. The vocabulary is CLOSED; validate_clarification_questions (bin/bale_validate.py) additionally enforces it row-wide at any depth."
          },
          "origin": {
            "type": "string",
            "enum": ["intent-gap", "probe-forbidden-environment"],
            "description": "Optional (v0.4.24): which gap class put this question on the clarification path — 'intent-gap' for the canonical ambiguity/contradiction/untransported-decision triggers (TARBALL.md section 5.9.1), or 'probe-forbidden-environment' for an environment gap asked here because the request set expects_probe: no and the probe recourse was unavailable (TARBALL.md section 3.3). Both origins still indict packing — a probe-forbidden environment gap is an include-completeness failure under a probe ban — so the tag does not de-noise the packing signal; it splits it into two different fixes (brief/decomposition vs include completeness). The vocabulary is CLOSED; validate_clarification_questions (bin/bale_validate.py) additionally enforces it row-wide at any depth, the priority discipline applied again. Legacy rows without this key keep validating."
          }
        }
      }
    },
    "feedback": {
      "type": "object",
      "additionalProperties": false,
      "required": ["mechanical", "self_reported"],
      "description": "Dual-stream session feedback (v0.3.8+, session B1). Optional so pre-B1 manifests validate; apply persists the block verbatim (the B2 telemetry record builds on it). Two streams by trust level: 'mechanical' holds values the lint (tools/response_lint.py) can recompute and verify; 'self_reported' holds worker-authored judgment the lint cannot check.",
      "properties": {
        "mechanical": {
          "type": "object",
          "additionalProperties": false,
          "required": ["response_kind", "schema_valid", "mirror_agreement", "claims_subset"],
          "description": "Lint-computable results. The worker fills these by running the lint; the lint's feedback-block check recomputes each and flags any disagreement — a mismatch is the tell of a hand-filled or stale block.",
          "properties": {
            "response_kind": {
              "type": "string",
              "enum": ["normal", "bailout", "clarification"],
              "description": "Echo of the manifest's effective response_kind (defaulted 'normal' when the top-level key is absent)."
            },
            "schema_valid": {
              "type": "boolean",
              "description": "Whether the manifest validates against this schema, as found by the lint's manifest-schema check."
            },
            "mirror_agreement": {
              "type": "object",
              "additionalProperties": false,
              "required": ["changes_to_files", "files_to_changes"],
              "description": "The TARBALL.md section 10.1 both-directions mirror result, split by direction.",
              "properties": {
                "changes_to_files": {
                  "type": "boolean",
                  "description": "Every created/modified entry has its files/ member with matching size and recomputed sha256; deleted entries follow the section 5.2 shape. Vacuously true on kinds that ship no files/."
                },
                "files_to_changes": {
                  "type": "boolean",
                  "description": "Nothing under files/ is undeclared in changes[]. Vacuously true on kinds that ship no files/."
                }
              }
            },
            "claims_subset": {
              "type": "boolean",
              "description": "set(claims) is a verbatim subset of validation_will_run (TARBALL.md section 5.3)."
            },
            "linkage": {
              "type": ["object", "null"],
              "additionalProperties": false,
              "required": ["kind", "point"],
              "description": "Present when the session went through a probe or clarification round on the way to this response; null or absent otherwise. Self-reported placement data riding in mechanical because its shape is fixed even though the lint cannot verify it.",
              "properties": {
                "kind": {
                  "type": "string",
                  "enum": ["probe", "clarification"],
                  "description": "Which recourse the session used (TARBALL.md section 5.9's taxonomy)."
                },
                "point": {
                  "type": "string",
                  "enum": ["pre-read", "pre-build", "mid-build"],
                  "description": "When in the session the gap surfaced: before any triggered drill-down reading, after reading but before building, or mid-build."
                },
                "depends_on": {
                  "type": ["string", "null"],
                  "description": "Session ID of the linked round when it exists as a durable artifact (a file-based probe or a shipped clarification response); null for a paste-back probe or an in-chat ask, which resolve within the session (TARBALL.md sections 4.5, 5.9.1)."
                }
              }
            },
            "provenance": {
              "type": ["object", "null"],
              "additionalProperties": false,
              "required": ["bale_version", "contract_docs", "packer", "work_class", "model_identity"],
              "description": "The request manifest's provenance block echoed verbatim, plus model_identity. Null when the request carried no provenance (packed by a pre-0.3.8 bale — the one-apply-behind bootstrap case).",
              "properties": {
                "bale_version": { "type": "string", "minLength": 1 },
                "contract_docs": {
                  "type": "object",
                  "description": "Verbatim echo of the request's contract_docs. PLANNER.md joined the carried set in v0.4.11 — admitted, not required (one-apply-behind: the wiring session's own response echoes a four-key block, and pre-v0.4.11 echoes stay valid). Since v0.4.42 a oneOf over the same two key sets the request schema admits — the four-key set keyed by CLAUDE.md (every pack before v0.4.43), and the same set with AGENT.md in place of CLAUDE.md (the current spelling, stamped since v0.4.43) — so the verbatim echo validates whichever spelling the request was stamped under, for good; exactly one of the pair may be present (request-manifest.schema.json).",
                  "oneOf": [
                    {
                      "additionalProperties": false,
                      "required": ["CLAUDE.md", "TARBALL.md", "DOCS.md", "CODE.md"],
                      "properties": {
                        "CLAUDE.md": { "type": "string", "minLength": 1 },
                        "TARBALL.md": { "type": "string", "minLength": 1 },
                        "DOCS.md":    { "type": "string", "minLength": 1 },
                        "CODE.md":    { "type": "string", "minLength": 1 },
                        "PLANNER.md": { "type": "string", "minLength": 1 }
                      }
                    },
                    {
                      "additionalProperties": false,
                      "required": ["AGENT.md", "TARBALL.md", "DOCS.md", "CODE.md"],
                      "properties": {
                        "AGENT.md":  { "type": "string", "minLength": 1 },
                        "TARBALL.md": { "type": "string", "minLength": 1 },
                        "DOCS.md":    { "type": "string", "minLength": 1 },
                        "CODE.md":    { "type": "string", "minLength": 1 },
                        "PLANNER.md": { "type": "string", "minLength": 1 }
                      }
                    }
                  ]
                },
                "packer": { "type": "string", "minLength": 1 },
                "work_class": {
                  "type": "string",
                  "enum": ["code", "doc", "contract-doc", "meta", "mixed"]
                },
                "checkpoint": {
                  "type": ["object", "null"],
                  "additionalProperties": false,
                  "required": ["path", "sha256"],
                  "description": "Echo of the request's provenance.checkpoint stamp (v0.3.28) — the blind checkpoint's pack-time {path, sha256} identity, or null when the request was packed with no checkpoint configured. Optional so echoes of pre-v0.3.28 requests (which carry no key) stay valid; when the request carries it, the verbatim echo does too.",
                  "properties": {
                    "path":   { "type": "string", "minLength": 1 },
                    "sha256": { "type": "string", "minLength": 1 }
                  }
                },
                "checkpoint_scope_admitted": {
                  "type": "boolean",
                  "description": "Echo of the request's provenance.checkpoint_scope_admitted stamp (v0.3.28): whether the planner admitted a checkpoint-covering pack scope with --allow-checkpoint-in-scope. Optional so echoes of pre-v0.3.28 requests stay valid."
                },
                "base_files": {
                  "type": "object",
                  "additionalProperties": {"type": "string", "minLength": 1},
                  "description": "Echo of the request's provenance.base_files stamp (v0.4.23) — the base-drift map, per-file sha256 (hex) of the write forecast's committed bytes at pack time, keyed by repo-relative path; {} for an empty (read-only) forecast. Optional so echoes of pre-v0.4.23 requests (which carry no key) stay valid; the block is echoed verbatim, so the key rides through exactly when the request carried it, and the echo shape must admit it because additionalProperties is false here. Mirrors the request schema's definition (request-manifest.schema.json)."
                },
                "checkpoint_waived": {
                  "type": "string",
                  "enum": ["read-only"],
                  "description": "Echo of the request's provenance.checkpoint_waived stamp (v0.4.9): present when the request waived the per-session checkpoint for the empty-forecast (read-only) shape. Optional — the block is echoed verbatim, so the key rides through exactly when the request carried it; the echo shape must admit it because additionalProperties is false here."
                },
                "packed_at": {
                  "type": "string",
                  "minLength": 1,
                  "description": "Echo of the request's provenance.packed_at stamp (v0.4.30) — the pack instant, ISO 8601 UTC with offset at seconds precision; its date equals the session id's date. Optional so echoes of pre-v0.4.30 requests (which carry no key) stay valid; the block is echoed verbatim, so the key rides through exactly when the request carried it, and the echo shape must admit it because additionalProperties is false here. Mirrors the request schema's definition (request-manifest.schema.json)."
                },
                "model_identity": {
                  "type": "string",
                  "minLength": 1,
                  "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*:[a-z0-9]+(?:[.-][a-z0-9]+)*$",
                  "description": "SELF-REPORTED AND UNVERIFIABLE TODAY: the worker states its own model identity; no mechanism attests it. Recorded for longitudinal aggregation, read with that caveat. Format, pinned since v0.4.42 so the value aggregates instead of splitting into free-text spellings: `<vendor>:<model>` — lowercase throughout, spaces rendered as hyphens, no parenthetical, no `self-reported` suffix (the whole field is self-reported by definition), and the literal `unknown` as the model token when the session cannot see its exact model string. Examples: `anthropic:claude-fable-5.1`, `anthropic:unknown`. The pattern refuses anything else — a free-text spelling with capitals, spaces, a parenthetical or a suffix is a lint error, not a variant."
                }
              }
            }
          }
        },
        "self_reported": {
          "type": "object",
          "additionalProperties": false,
          "required": ["assumptions", "judgment_calls", "budget_pressure", "includes_missing", "compaction_occurred"],
          "description": "Worker-authored stream. Honest empties are meaningful ([] = none arose); the lint checks shape only, never content.",
          "properties": {
            "assumptions": {
              "type": "array",
              "items": { "type": "string", "minLength": 1 },
              "description": "Assumptions the session proceeded on without confirmation (the recoverable-risk posture of TARBALL.md section 3.3 / 5.9.1), one per entry."
            },
            "judgment_calls": {
              "type": "array",
              "items": { "type": "string", "minLength": 1 },
              "description": "Decisions the worker made that the planner should be able to find without reading the diff — design choices, tie-breaks, interpretations."
            },
            "budget_pressure": {
              "type": "string",
              "enum": ["none", "tight", "bailed"],
              "description": "The session's own read of its context budget: comfortable throughout, felt the AGENT.md section 11.3 pressure without bailing, or this response is a bailout."
            },
            "includes_missing": {
              "type": "array",
              "items": { "type": "string", "minLength": 1 },
              "description": "What the session wanted but the request did not ship — packing signal for the planner, one entry per miss. Two entry forms, both strings in one array (the shape is unchanged since v0.3.8): a repo-relative path for a file the session needed in context/ (e.g. `bin/bale_config.py`), or a line opening `decision:` for a ruling the brief did not carry and the session had to assume or ask for (e.g. `decision: whether [layout] is project-layer only`). The marker is the literal `decision:` prefix; everything after it is prose."
            },
            "docs_read": {
              "type": "array",
              "items": { "type": "string", "minLength": 1 },
              "description": "Optional (v0.4.24): the docs and sections the session actually read, one doc or doc-section reference per entry (e.g. 'TARBALL.md sections 1, 2, 5, 7'). Self-report, weighted like everything else in this stream — the lint checks shape only, never content, and no mechanism attests the reading happened. Additive and OPTIONAL, so every pre-v0.4.24 manifest keeps validating and omission means the session reported nothing, never that it read nothing."
            },
            "compaction_occurred": {
              "type": "object",
              "additionalProperties": false,
              "required": ["occurred"],
              "description": "Whether the runtime compacted mid-session (AGENT.md section 11.6). When true, disclosure_ref points at where the disclosure lives.",
              "properties": {
                "occurred": { "type": "boolean" },
                "disclosure_ref": {
                  "type": ["string", "null"],
                  "description": "Where the compaction disclosure was recorded (e.g. 'notes.md' or a chat pointer); null when occurred is false."
                }
              }
            },
            "forecast_departures": {
              "type": "array",
              "description": "The worker's own structured account of judgment past the ask (v0.4.2, ADR-0015, ratified — additive and OPTIONAL, so every pre-epoch manifest stays valid and omission means the session declares no departures). One entry per changes[] path the worker shipped outside the session's write forecast: path plus why, the structured twin of the notes.md enumeration (which remains the human-facing account and the apply-walkthrough input; this field is the aggregable one). Apply persists the feedback block verbatim into telemetry, so `bale stats` cross-checks these declarations against the mechanically admitted overridden_paths — an admitted path with no declared departure is the ADR-0014 audit smell, computed instead of eyeballed.",
              "items": {
                "type": "object",
                "additionalProperties": false,
                "required": ["path", "why"],
                "properties": {
                  "path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "The repo-relative changes[] path shipped outside the forecast."
                  },
                  "why": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Why the goal required this path — the argument the drift makes for itself."
                  }
                }
              }
            },
            "light_blocks": {
              "type": "integer",
              "minimum": 0,
              "description": "Optional (v0.4.34): the number of light question blocks (TARBALL.md section 5.10) the worker emitted this session — the chat-carried ask tier, which opens no exchange record, so this count is the only place the tier becomes visible to stats. Self-report, like everything in this stream; the lint checks shape only. Additive and OPTIONAL, so every earlier manifest keeps validating, and the crafter's skeleton seeds nothing: omission means the session reported no count, never that it emitted no block — a worker who emitted a block writes the number."
            },
            "paste_carried_rounds": {
              "type": "integer",
              "minimum": 0,
              "description": "Optional (v0.4.34): the number of exchange rounds (TARBALL.md section 5.9.2) whose record traveled by paste block rather than by tarball — the courier the operator chose at carry time — so telemetry stops reading a real round as zero where no clarification tarball was applied. Self-report, like everything in this stream; the lint checks shape only. Additive and OPTIONAL, so every earlier manifest keeps validating, and the crafter's skeleton seeds nothing: omission means the session reported no count, never that no round was paste-carried."
            }
          }
        }
      }
    }
  }
}
"""

DIAGNOSTICS_SCHEMA_JSON = r"""
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/anthropics/bale/schemas/diagnostics.schema.json",
  "title": "bale bailout diagnostics",
  "description": "Shape of response-NNN/diagnostics.json (bailout responses only) per TARBALL.md section 5.8. INTENTIONALLY LOOSE: additionalProperties is true at the top level so future fields can be added without breaking earlier aggregation across sessions. The required keys below are the universal envelope; the values inside (tool_calls_summary keys, what_would_save_next_time strings) are deliberately freeform.",
  "type": "object",
  "additionalProperties": true,
  "required": [
    "session_id",
    "bail_trigger",
    "bail_narrative",
    "context_loaded",
    "exploration_paths",
    "tool_calls_summary",
    "what_would_save_next_time"
  ],
  "properties": {
    "session_id": {
      "type": "string",
      "minLength": 1,
      "description": "The bailing session's ID. Matches the manifest's session_id field."
    },
    "bail_trigger": {
      "type": "string",
      "enum": [
        "reading-path-inflation",
        "mid-build-budget-panic",
        "other"
      ],
      "description": "Per AGENT.md section 11.3. The first two are worker-detected; 'other' covers architect-requested bailouts with specifics in bail_narrative."
    },
    "bail_narrative": {
      "type": "string",
      "minLength": 1,
      "description": "One paragraph: what was noticed, when, why bailing beat pushing through. Searchable across sessions when bail_trigger's enum is too coarse."
    },
    "context_loaded": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": true,
        "required": ["path", "verdict", "note"],
        "properties": {
          "path": { "type": "string", "minLength": 1 },
          "verdict": {
            "type": "string",
            "enum": ["necessary", "wasted", "partial"]
          },
          "note": { "type": "string" }
        }
      }
    },
    "exploration_paths": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": true,
        "required": ["what", "verdict", "note"],
        "properties": {
          "what": { "type": "string", "minLength": 1 },
          "verdict": {
            "type": "string",
            "enum": ["productive", "dead_end", "inconclusive"]
          },
          "note": { "type": "string" }
        }
      }
    },
    "tool_calls_summary": {
      "type": "object",
      "description": "Map of tool name to call count. Keys are freeform tool names; values are non-negative counts.",
      "additionalProperties": {
        "type": "integer",
        "minimum": 0
      }
    },
    "what_would_save_next_time": {
      "type": "array",
      "items": { "type": "string", "minLength": 1 },
      "description": "Concrete prescriptions for the next session. Overlaps with handoff.md's 'What I learned' by design."
    }
  }
}
"""


# ---------------------------------------------------------------------------
# Minimal JSON-Schema validator.
#
# Implements exactly the keyword subset the two schemas above use:
#   type (string or list), required, properties, additionalProperties
#   (boolean or schema), enum, minLength, minimum, items, and — since
#   v0.4.42 — pattern (an unanchored search, as in JSON Schema; the
#   schema anchors a whole-string match) and oneOf (exactly one branch
#   accepts; zero names each branch's first failure, two or more is an
#   error too). The same subset lives in bin/bale_validate.py and the
#   two move together.
# Collects every violation rather than stopping at the first, matching
# the lint's never-first-failure-only output contract.
# ---------------------------------------------------------------------------

def _type_matches(value, type_name: str) -> bool:
    """True when value matches a JSON-Schema primitive type name.

    bool is a subclass of int in Python, so 'integer' and 'number'
    explicitly exclude it — JSON booleans are not JSON numbers.
    """
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "null":
        return value is None
    return False  # unknown type name in schema: treat as non-match, loudly wrong


def _json_type_name(value) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if value is None:
        return "null"
    return type(value).__name__


def schema_validate(instance, schema: dict, loc: str = "$") -> list[str]:
    """Validate instance against the supported schema subset.

    Returns a list of human-readable violation strings ("<loc>: <what>");
    empty list means valid. Never raises on instance content.
    """
    errors: list[str] = []
    _schema_walk(instance, schema, loc, errors)
    return errors


def _schema_walk(instance, schema: dict, loc: str, errors: list[str]) -> None:
    # -- type --
    declared = schema.get("type")
    if declared is not None:
        allowed = declared if isinstance(declared, list) else [declared]
        if not any(_type_matches(instance, t) for t in allowed):
            errors.append(
                f"{loc}: expected type {' or '.join(allowed)}, "
                f"got {_json_type_name(instance)}"
            )
            return  # deeper keywords assume the right type; stop this branch

    # -- enum --
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(
            f"{loc}: value {json.dumps(instance)} not in enum "
            f"{json.dumps(schema['enum'])}"
        )

    # -- string keywords --
    if isinstance(instance, str) and "minLength" in schema:
        if len(instance) < schema["minLength"]:
            errors.append(
                f"{loc}: string shorter than minLength "
                f"{schema['minLength']} (got length {len(instance)})"
            )
    if isinstance(instance, str) and "pattern" in schema:
        if re.search(schema["pattern"], instance) is None:
            errors.append(
                f"{loc}: value {json.dumps(instance)} does not match "
                f"pattern {schema['pattern']}"
            )

    # -- oneOf: exactly one branch accepts --
    if "oneOf" in schema:
        matched = 0
        first_failures: list[str] = []
        for i, branch in enumerate(schema["oneOf"]):
            branch_errors: list[str] = []
            _schema_walk(instance, branch, loc, branch_errors)
            if not branch_errors:
                matched += 1
            else:
                first_failures.append(f"branch {i}: {branch_errors[0]}")
        if matched == 0:
            errors.append(f"{loc}: matches none of the oneOf branches — "
                          + "; ".join(first_failures))
        elif matched > 1:
            errors.append(f"{loc}: matches {matched} oneOf branches, "
                          f"expected exactly one")

    # -- numeric keywords --
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(
                f"{loc}: {instance} below minimum {schema['minimum']}"
            )

    # -- object keywords --
    if isinstance(instance, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{loc}: missing required property '{key}'")
        addl = schema.get("additionalProperties", True)
        for key, value in instance.items():
            child_loc = f"{loc}.{key}"
            if key in props:
                _schema_walk(value, props[key], child_loc, errors)
            elif addl is False:
                errors.append(f"{loc}: additional property '{key}' not allowed")
            elif isinstance(addl, dict):
                _schema_walk(value, addl, child_loc, errors)
            # addl is True: unconstrained, accept

    # -- array keywords --
    if isinstance(instance, list) and "items" in schema:
        for i, item in enumerate(instance):
            _schema_walk(item, schema["items"], f"{loc}[{i}]", errors)


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

def finding(code: str, path, expected, got, message: str, *,
            severity: str = "error") -> dict:
    """One named failure: stable code + path + expected + got + prose.

    `severity` is "error" (a finding: counts against `ok`, exit 1) or
    "warning" (reported, never gating — the runner routes it to the
    report's warnings[] instead of findings[]). Every check before v0.4.30
    filed errors only; the tier exists for the docs_read prefix case,
    where the self-report is advisory and a refusal would be
    disproportionate.
    """
    return {
        "code": code,
        "path": str(path),
        "expected": expected,
        "got": got,
        "message": message,
        "severity": severity,
    }


def warning(code: str, path, expected, got, message: str, *,
            headline: str | None = None) -> dict:
    """A warning-tier finding (see `finding`).

    `headline`, when given, is the short subject the runner puts on the
    check's own [WARN] line (e.g. naming README.md) — so a check whose
    subject word must appear only when it warns keeps that word out of
    its registry description, which the [PASS] line prints.
    """
    w = finding(code, path, expected, got, message, severity="warning")
    if headline is not None:
        w["headline"] = headline
    return w


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_unsafe_relpath(path_str: str) -> bool:
    """True when a changes[].path can't be safely joined under files/.

    Full path-safety (.git/.bale exclusion, .baleignore) is bale's
    pre-flight job; this lint rejects only what would make its own
    mirror lookup dangerous or meaningless.
    """
    if path_str.startswith("/") or path_str.startswith("\\"):
        return True
    parts = path_str.replace("\\", "/").split("/")
    return ".." in parts or "" == path_str


def _list_mirror_files(files_root: Path) -> list[str]:
    if not files_root.is_dir():
        return []
    return sorted(
        p.relative_to(files_root).as_posix()
        for p in files_root.rglob("*")
        if p.is_file()
    )


# ---------------------------------------------------------------------------
# Checks. Each takes the shared context dict and returns a findings list.
#
# The registry at the bottom of this section is the extension surface:
# session B (feedback block, provenance stamping) adds rows here, it
# does not rewrite the runner.
# ---------------------------------------------------------------------------

def check_manifest_parse(ctx: dict) -> list[dict]:
    """manifest.json exists and parses as JSON (TARBALL.md §5.1: required)."""
    rdir: Path = ctx["rdir"]
    mpath = rdir / "manifest.json"
    if not mpath.is_file():
        return [finding(
            "MANIFEST_MISSING", "manifest.json",
            "manifest.json present in the response directory", "absent",
            "TARBALL.md section 5.1 lists manifest.json as required",
        )]
    try:
        ctx["manifest"] = json.loads(mpath.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return [finding(
            "MANIFEST_UNPARSEABLE", "manifest.json",
            "valid UTF-8 JSON", f"parse error: {exc}",
            "manifest.json did not parse; every downstream check is skipped",
        )]
    if not isinstance(ctx["manifest"], dict):
        got = _json_type_name(ctx["manifest"])
        ctx["manifest"] = None
        return [finding(
            "MANIFEST_UNPARSEABLE", "manifest.json",
            "a JSON object at the top level", got,
            "manifest.json parsed but is not an object; downstream checks skipped",
        )]
    return []


def check_manifest_schema(ctx: dict) -> list[dict]:
    """Manifest validates against response-manifest.schema.json."""
    manifest = ctx["manifest"]
    out = []
    for err in schema_validate(manifest, ctx["manifest_schema"]):
        loc, _, what = err.partition(": ")
        out.append(finding(
            "SCHEMA_VIOLATION", f"manifest.json:{loc}",
            "conformance to response-manifest.schema.json", what,
            f"schema violation at {loc}: {what}",
        ))
    kind = manifest.get("response_kind", "normal")
    ctx["kind"] = kind if kind in VALID_KINDS else None  # enum error already filed
    return out


def check_required_artifacts(ctx: dict) -> list[dict]:
    """apply.sh and validation.sh exist (§5.1: required on every kind)."""
    out = []
    for name in ("apply.sh", "validation.sh"):
        if not (ctx["rdir"] / name).is_file():
            out.append(finding(
                "ARTIFACT_MISSING", name,
                f"{name} present (a no-op script when there is nothing to do)",
                "absent",
                f"TARBALL.md section 5.1 lists {name} as required for every "
                "response kind, including bailout (5.6.1) and clarification (5.9.2)",
            ))
    return out


def check_changes_mirror(ctx: dict) -> list[dict]:
    """changes[] <-> files/ correspondence, both directions, hashes recomputed.

    Covers TARBALL.md §5.2 (field rules per action), §5.2.1 (computed,
    never transcribed — the lint recomputes from bytes and never trusts
    the manifest), and §10.1's both-directions mirror bullet. Runs for
    the normal kind only; bailout/clarification file surfaces belong to
    check_kind_shape.
    """
    if ctx["kind"] != "normal":
        return []
    manifest = ctx["manifest"]
    changes = manifest.get("changes")
    if not isinstance(changes, list):
        return []  # schema check already filed the type violation
    rdir: Path = ctx["rdir"]
    files_root = rdir / "files"
    out: list[dict] = []

    entries = [c for c in changes if isinstance(c, dict)]

    # Duplicate paths make the mirror correspondence ambiguous.
    dupes = [p for p, n in Counter(
        c.get("path") for c in entries if isinstance(c.get("path"), str)
    ).items() if n > 1]
    for p in sorted(dupes):
        out.append(finding(
            "DUPLICATE_PATH", p,
            "each path appearing in changes[] at most once", f"{p} appears more than once",
            "duplicate changes[] entries make the files/ <-> changes[] "
            "correspondence of section 10.1 ambiguous",
        ))

    declared_present: set[str] = set()   # created/modified paths
    declared_deleted: set[str] = set()

    for i, ch in enumerate(entries):
        path_str = ch.get("path")
        action = ch.get("action")
        if not isinstance(path_str, str) or action not in ("created", "modified", "deleted"):
            continue  # schema check already filed these
        if _is_unsafe_relpath(path_str):
            out.append(finding(
                "PATH_UNSAFE", path_str,
                "a repo-relative path with no traversal", path_str,
                f"changes[{i}].path cannot be safely resolved under files/; "
                "full path-safety remains bale's pre-flight, but the mirror "
                "check needs a joinable path",
            ))
            continue

        if action == "deleted":
            declared_deleted.add(path_str)
            # §5.2: deleted entries have size_bytes 0, sha256 null, no files/ member.
            if (files_root / path_str).exists():
                out.append(finding(
                    "DELETED_IN_FILES", path_str,
                    "no files/ entry for a deleted path (removal happens in apply.sh)",
                    f"files/{path_str} exists",
                    f"changes[{i}] is action=deleted but the path is present "
                    "under files/ (TARBALL.md section 5.2)",
                ))
            if ch.get("size_bytes") != 0:
                out.append(finding(
                    "DELETED_SIZE_NONZERO", path_str,
                    "size_bytes: 0", repr(ch.get("size_bytes")),
                    f"changes[{i}] is action=deleted; section 5.2 fixes "
                    "size_bytes at 0",
                ))
            if ch.get("sha256") is not None:
                out.append(finding(
                    "DELETED_SHA_NOT_NULL", path_str,
                    "sha256: null", repr(ch.get("sha256")),
                    f"changes[{i}] is action=deleted; section 5.2 fixes "
                    "sha256 at null",
                ))
            continue

        # created / modified
        declared_present.add(path_str)
        fpath = files_root / path_str
        if not fpath.is_file():
            out.append(finding(
                "MIRROR_MISSING", path_str,
                f"files/{path_str} present", "absent",
                f"changes[{i}] declares action={action} but the files/ "
                "mirror has no such file (section 10.1, declared-but-absent)",
            ))
            continue
        if not isinstance(ch.get("sha256"), str):
            out.append(finding(
                "SHA256_NOT_STRING", path_str,
                "a sha256 hex string for created/modified entries",
                repr(ch.get("sha256")),
                f"changes[{i}] is action={action}; section 5.2 requires a "
                "computed sha256 string (null is reserved for deleted)",
            ))
        else:
            actual_sha = _sha256_of(fpath)
            if ch["sha256"] != actual_sha:
                out.append(finding(
                    "SHA256_MISMATCH", path_str,
                    f"sha256 {actual_sha} (recomputed from files/{path_str})",
                    ch["sha256"],
                    f"changes[{i}].sha256 disagrees with the bytes under "
                    "files/ — hashes are computed, never transcribed "
                    "(section 5.2.1); a remembered hash is an invented hash "
                    "(AGENT.md section 11.6)",
                ))
        actual_size = fpath.stat().st_size
        if ch.get("size_bytes") != actual_size:
            out.append(finding(
                "SIZE_MISMATCH", path_str,
                f"size_bytes {actual_size} (measured from files/{path_str})",
                repr(ch.get("size_bytes")),
                f"changes[{i}].size_bytes disagrees with the file on disk "
                "(section 5.2.1)",
            ))

    # Reverse direction: nothing under files/ may be undeclared (§10.1).
    for rel in ctx["mirror_files"]:
        if rel not in declared_present and rel not in declared_deleted:
            out.append(finding(
                "MIRROR_UNDECLARED", rel,
                "a matching created/modified entry in changes[]", "no entry",
                f"files/{rel} exists but changes[] never declares it "
                "(section 10.1, undeclared file)",
            ))
    return out


def check_claims_subset(ctx: dict) -> list[dict]:
    """set(claims) ⊆ set(validation_will_run), matched verbatim (§5.3, §10.1)."""
    manifest = ctx["manifest"]
    claims = manifest.get("claims")
    will_run = manifest.get("validation_will_run")
    if not isinstance(claims, dict) or not isinstance(will_run, list):
        return []  # schema check already filed the type violations
    out = []
    will_run_set = {w for w in will_run if isinstance(w, str)}
    for key in claims:
        if key not in will_run_set:
            out.append(finding(
                "CLAIMS_UNPAIRABLE", f"claims.{key}",
                "a verbatim match in validation_will_run (same characters, same spacing)",
                f"no entry equal to {key!r}",
                "section 5.3: a claims key with no verbatim "
                "validation_will_run match is unpairable — the tell of a "
                "renamed or paraphrased check; the fix is the key, not a "
                "new entry",
            ))
    return out


# Mirror of bin/bale_validate.py's CLAIM_VALUES (TARBALL.md section 5.3
# carries the vocabulary table). Deliberately duplicated rather than
# imported: this lint is a standalone second implementation of the
# WRITTEN contract, never a bale import (see module docstring), and it
# runs inside request tarballs where no bale install is reachable.
# The embedded schema cannot carry this enum for the bare-string form —
# the subset validator has no oneOf, and the schema's own claims
# description says the bare-string enum is "enforced in Python" — so
# without this mirror a bare-string value outside the vocabulary lints
# clean and refuses at apply. The object form's `value` enum stays the
# schema's (manifest-schema files it); this mirror never re-files it.
CLAIM_VALUES = ("pass", "fail", "untested", "unknown")


def check_claims_value(ctx: dict) -> list[dict]:
    """Every bare-string claims value is in the claim vocabulary (§5.3).

    Only the bare-string form is judged here. The annotated object form
    ({"value": ..., "claim_basis": ...}) is pinned by the embedded
    schema's plain enum and filed by manifest-schema, and a value of any
    other JSON type is a schema type violation — both are skipped so no
    violation is filed twice. Its own registry row (not a manifest-schema
    or claims-subset finding) on purpose: the feedback block's
    schema_valid and claims_subset keep meaning exactly what their
    derivations say, schema conformance and the subset rule.
    """
    claims = ctx["manifest"].get("claims")
    if not isinstance(claims, dict):
        return []  # schema check already filed the type violation
    out = []
    for key, value in claims.items():
        if not isinstance(value, str) or value in CLAIM_VALUES:
            continue
        out.append(finding(
            "CLAIMS_VALUE", f"manifest.json:$.claims.{key}",
            f"one of {list(CLAIM_VALUES)}", repr(value),
            f"claims[{key!r}] = {value!r} is outside the claim vocabulary "
            "(TARBALL.md section 5.3) — bale's apply refuses it "
            "(bin/bale_validate.py CLAIM_VALUES); the embedded schema "
            "cannot see a bare-string value, so this check is its only "
            "pre-pack catch",
        ))
    return out


def _empty_surface_findings(manifest: dict, kind: str, section: str) -> list[dict]:
    """The empty change surfaces bailout (§5.6.2) and clarification (§5.9.2) share."""
    out = []
    expectations = (
        ("changes", list, []),
        ("deferred", list, []),
        ("validation_will_run", list, []),
        ("claims", dict, {}),
    )
    for field, typ, empty in expectations:
        value = manifest.get(field)
        if isinstance(value, typ) and value != empty:
            out.append(finding(
                "KIND_EMPTY_SURFACE", f"manifest.json:$.{field}",
                f"{field} empty on a {kind} response",
                f"{len(value)} entr{'y' if len(value) == 1 else 'ies'}",
                f"TARBALL.md {section} requires {field} to be empty when "
                f"response_kind is '{kind}'",
            ))
    return out


def _files_surface_finding(ctx: dict, kind: str, section: str) -> list[dict]:
    if ctx["mirror_files"]:
        return [finding(
            "KIND_FILES_PRESENT", "files/",
            f"files/ absent or empty on a {kind} response",
            f"{len(ctx['mirror_files'])} file(s) under files/",
            f"TARBALL.md {section}: a {kind} response ships no file changes",
        )]
    return []


def check_kind_shape(ctx: dict) -> list[dict]:
    """Per-kind shape rules: §5.6.1/§5.6.2 (bailout), §5.9.2 (clarification),
    and the questions-block placement rule for every kind.

    §5.9.2 reads 'Forbidden (or empty) on every other response kind', so an
    empty questions array on a non-clarification kind passes; a non-empty
    one fails. (The schema file's description was aligned to this wording
    in session B1 — the doc is the contract of record, and the lint
    implements TARBALL.md.)
    """
    manifest = ctx["manifest"]
    kind = ctx["kind"]
    rdir: Path = ctx["rdir"]
    if kind is None:
        return []  # invalid enum value; schema check filed it, shape undefined
    out: list[dict] = []
    questions = manifest.get("questions")

    if kind in ("normal", "bailout"):
        if isinstance(questions, list) and len(questions) > 0:
            out.append(finding(
                "QUESTIONS_FORBIDDEN", "manifest.json:$.questions",
                f"no non-empty questions[] on a {kind} response",
                f"{len(questions)} question(s)",
                "TARBALL.md section 5.9.2: questions[] is required on "
                "clarification responses and forbidden (or empty) on every "
                "other kind",
            ))

    if kind == "bailout":
        out.extend(_empty_surface_findings(manifest, kind, "section 5.6.2"))
        out.extend(_files_surface_finding(ctx, kind, "section 5.6.1"))
        if not (rdir / "handoff.md").is_file():
            out.append(finding(
                "ARTIFACT_MISSING", "handoff.md",
                "handoff.md present", "absent",
                "TARBALL.md section 5.6.1: handoff.md is required in bailout "
                "responses",
            ))
        if (rdir / "README.md").is_file():
            out.append(finding(
                "README_FORBIDDEN", "README.md",
                "no README.md in a bailout response", "README.md present",
                "TARBALL.md section 5.6.1: README.md is absent in bailouts — "
                "handoff.md carries the forward-looking content",
            ))
        out.extend(_check_diagnostics(ctx))

    if kind == "clarification":
        out.extend(_empty_surface_findings(manifest, kind, "section 5.9.2"))
        out.extend(_files_surface_finding(ctx, kind, "section 5.9.2"))
        if (rdir / "README.md").is_file():
            out.append(finding(
                "README_FORBIDDEN", "README.md",
                "no README.md in a clarification response", "README.md present",
                "TARBALL.md section 5.9.2: README.md is absent on a "
                "clarification — the questions[] block is the payload and "
                "notes.md is the optional prose channel",
            ))
        if not (isinstance(questions, list) and len(questions) > 0):
            out.append(finding(
                "QUESTIONS_REQUIRED", "manifest.json:$.questions",
                "a non-empty questions[] block",
                "absent" if questions is None else repr(questions),
                "TARBALL.md section 5.9.2: questions[] is required and "
                "non-empty on a clarification response — it is the payload",
            ))
    return out


def _check_diagnostics(ctx: dict) -> list[dict]:
    """diagnostics.json: required in bailouts, parses, schema-validates (§5.8)."""
    dpath = ctx["rdir"] / "diagnostics.json"
    if not dpath.is_file():
        return [finding(
            "ARTIFACT_MISSING", "diagnostics.json",
            "diagnostics.json present", "absent",
            "TARBALL.md section 5.6.1: diagnostics.json is required in "
            "bailout responses",
        )]
    try:
        diag = json.loads(dpath.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return [finding(
            "DIAGNOSTICS_UNPARSEABLE", "diagnostics.json",
            "valid UTF-8 JSON", f"parse error: {exc}",
            "diagnostics.json did not parse",
        )]
    out = []
    for err in schema_validate(diag, ctx["diagnostics_schema"]):
        loc, _, what = err.partition(": ")
        out.append(finding(
            "DIAGNOSTICS_SCHEMA_VIOLATION", f"diagnostics.json:{loc}",
            "conformance to diagnostics.schema.json", what,
            f"schema violation at {loc}: {what}",
        ))
    return out


# Session B1 checks: generated-artifact deny list, retired next-prompt.md,
# and the feedback-block verification.

# Mirror of bale's apply pre-flight deny list (TARBALL.md section 5.1
# carries the builder-side rule). Deliberately duplicated
# rather than imported: this lint is a standalone second implementation
# of the WRITTEN contract, never a bale import (see module docstring).
GENERATED_ARTIFACT_DIRS = frozenset({
    "__pycache__", "node_modules", "dist", "build",
})
GENERATED_ARTIFACT_FILE_SUFFIXES = (".pyc", ".pyo")


def check_generated_artifacts(ctx: dict) -> list[dict]:
    """No changes[] path names a generated artifact (TARBALL.md §5.1).

    A path offends when any NON-FINAL component is one of the deny-list
    directory names, or its basename ends in .pyc/.pyo. A source file
    merely named like one (`scripts/build`, `pyc_utils.py`) passes —
    the conservative side of the line, matching bale's apply pre-flight,
    so the worker catches the rejection pre-pack.
    """
    manifest = ctx["manifest"]
    changes = manifest.get("changes")
    if not isinstance(changes, list):
        return []  # schema check already filed the type violation
    out = []
    for i, ch in enumerate(changes):
        p = ch.get("path") if isinstance(ch, dict) else None
        if not isinstance(p, str) or not p:
            continue  # schema check already filed these
        parts = p.replace("\\", "/").split("/")
        offends = any(part in GENERATED_ARTIFACT_DIRS for part in parts[:-1])
        if not offends and parts:
            offends = any(parts[-1].endswith(sfx)
                          for sfx in GENERATED_ARTIFACT_FILE_SUFFIXES)
        if offends:
            out.append(finding(
                "GENERATED_ARTIFACT", p,
                "no generated-artifact paths in changes[] (no "
                "__pycache__/node_modules/dist/build directory component, "
                "no *.pyc/*.pyo basename)", p,
                f"changes[{i}] names a generated artifact — files/ carries "
                "source, never toolchain products (TARBALL.md section 5.1); "
                "bale's apply pre-flight rejects this tarball",
            ))
    return out


def check_next_prompt_retired(ctx: dict) -> list[dict]:
    """No next-prompt.md in the response (retired, TARBALL.md §5.5)."""
    if (ctx["rdir"] / "next-prompt.md").is_file():
        return [finding(
            "NEXT_PROMPT_RETIRED", "next-prompt.md",
            "no next-prompt.md (retired as of "
            "2026-07-06-retire-next-prompt-006)", "next-prompt.md present",
            "TARBALL.md section 5.5: responses do not ship next-prompt.md; "
            "follow-up suggestions go in the Proposals section of notes.md "
            "(section 5.4.1)",
        )]
    return []


# ---------------------------------------------------------------------------
# v0.4.30: the request's own layout and clock, guarded at the
# self-check. TARBALL.md §3.1: a request path context/<p> is the repo
# path <p>; nothing in a response carries the prefix. TARBALL.md §1:
# every date bale mints is UTC, and a session dates what it writes from
# the session id, never from the date its chat shows.
# ---------------------------------------------------------------------------

CONTEXT_PREFIX = "context/"


def _carries_context_prefix(path_str: str) -> bool:
    """True when a repo-relative path was written tarball-relative —
    `context/<p>` or bare `context` — the §3.1 mapping applied backwards."""
    norm = path_str.replace("\\", "/")
    return norm == "context" or norm.startswith(CONTEXT_PREFIX)


def _context_prefixed_tokens(entry: str) -> list[str]:
    """The whitespace-delimited tokens of a free-text docs_read entry
    that begin with the context/ prefix (surrounding punctuation
    stripped, so `(context/bin/bale)` and `context/docs/X,` both count)."""
    out = []
    for raw in entry.split():
        tok = raw.strip("()[]{}<>'\"`,;:")
        if tok.startswith(CONTEXT_PREFIX):
            out.append(tok)
    return out


def check_context_prefix(ctx: dict) -> list[dict]:
    """No changes[] path and no docs_read entry carries the tarball-layout
    context/ prefix (TARBALL.md §3.1).

    A changes[] path is a finding: `files/` mirrors the repo root, so a
    path shipped as context/<p> lands at <repo>/context/<p> — a wrong
    place, silently, and against the wrong forecast entry. A
    feedback.self_reported.docs_read entry is a warning: the self-report
    is advisory, but the stats read side sees two spellings of one path,
    so it is named rather than let through.
    """
    manifest = ctx["manifest"]
    out = []
    changes = manifest.get("changes")
    if isinstance(changes, list):
        for i, ch in enumerate(changes):
            p = ch.get("path") if isinstance(ch, dict) else None
            if not isinstance(p, str) or not p:
                continue  # schema check already filed these
            if _carries_context_prefix(p):
                stripped = p.replace("\\", "/")[len(CONTEXT_PREFIX):] \
                    if p.replace("\\", "/").startswith(CONTEXT_PREFIX) \
                    else ""
                out.append(finding(
                    "CONTEXT_PREFIXED_PATH", p,
                    "a repo-relative path (a request path context/<p> is "
                    "the repo path <p>; the prefix is tarball layout)",
                    p,
                    f"changes[{i}] carries the request tarball's context/ "
                    f"prefix — files/ mirrors the repo root, so bale would "
                    f"land it at the wrong place (TARBALL.md section 3.1)"
                    + (f"; the repo path is {stripped!r}" if stripped
                       else ""),
                ))
    fb = manifest.get("feedback")
    sr = fb.get("self_reported") if isinstance(fb, dict) else None
    docs_read = sr.get("docs_read") if isinstance(sr, dict) else None
    if isinstance(docs_read, list):
        for i, entry in enumerate(docs_read):
            if not isinstance(entry, str):
                continue  # schema check already filed it
            toks = _context_prefixed_tokens(entry)
            if toks:
                out.append(warning(
                    "CONTEXT_PREFIXED_DOCS_READ",
                    f"manifest.json:$.feedback.self_reported.docs_read[{i}]",
                    "doc references written repo-relative (no context/ "
                    "prefix)", entry,
                    f"docs_read[{i}] names {', '.join(repr(t) for t in toks)} "
                    f"with the request tarball's context/ prefix — the "
                    f"prefix is tarball layout, and the stats read side "
                    f"would see two spellings of one path (TARBALL.md "
                    f"section 3.1); strip it to the repo path",
                ))
    return out


def check_docs_read_stub(ctx: dict) -> list[dict]:
    """A shipped feedback.self_reported.docs_read that is exactly []
    is a warning: most likely the crafter's stub, shipped unfilled.

    tools/craft_response.py seeds `docs_read: []` so the optional field
    has scaffold presence. The schema reads an omitted docs_read as
    "reported nothing", but a present [] claims the session read
    nothing — which, from an untouched stub, is a false datum rather
    than an honest empty. The lint cannot tell a real empty from an
    unfilled seed, so it names every present [] and lets the worker
    choose: fill it, or delete the key. Omission stays silent. Warning
    tier (the CONTEXT_PREFIXED_DOCS_READ tier): the self-report is
    advisory, so it is named, never gating.
    """
    fb = ctx["manifest"].get("feedback")
    sr = fb.get("self_reported") if isinstance(fb, dict) else None
    if not isinstance(sr, dict) or "docs_read" not in sr:
        return []
    if sr["docs_read"] != []:
        return []  # filled, or a type violation the schema check filed
    return [warning(
        "DOCS_READ_EMPTY_STUB",
        "manifest.json:$.feedback.self_reported.docs_read",
        "the docs and sections this session read, or the key omitted",
        "[]",
        "docs_read is present and empty — the crafter's stub shipped "
        "unfilled, and a present [] records that nothing was read; fill it "
        "or delete the key (omission means reported nothing)",
    )]


class CheckSkipped(Exception):
    """Raised by a check that cannot run on this invocation — the runner
    reports it as [SKIP] with the reason, never as a silent [PASS]."""


# The request manifest (--request) is the lint's only view of the
# request: the two checks below read it, and without the flag they
# report [SKIP] naming the flag rather than passing vacuously.
REQUEST_FLAG_SKIP = "no --request given (the request's manifest.json)"


def path_in_forecast(path: str, scope: list[str]) -> bool:
    """True when `path` lies inside the write forecast `scope`.

    TARBALL.md §3.2's path semantics: an entry equal to the path covers
    it, and a directory entry covers its whole subtree, matched on whole
    path components (`tools` covers `tools/a.py`, never `toolsmith.py`).
    A trailing slash is tolerated and a whole-tree entry (`.`) covers
    everything. Restated independently of tools/craft_response.py's
    predicate of the same name (the lint imports nothing), and pinned
    to it behaviorally by the two suites' shared cases.
    """
    for entry in scope:
        norm = entry.rstrip("/")
        if norm in ("", "."):
            return True
        if path == norm or path.startswith(norm + "/"):
            return True
    return False


def _self_reported(manifest: dict) -> dict | None:
    fb = manifest.get("feedback")
    sr = fb.get("self_reported") if isinstance(fb, dict) else None
    return sr if isinstance(sr, dict) else None


def check_forecast_departures(ctx: dict) -> list[dict]:
    """With --request: every changes[] path outside the request's
    resolved_scope carries a feedback.self_reported.forecast_departures
    entry naming it.

    The request's resolved_scope is the session's write forecast
    (TARBALL.md §3.2); a path outside it is drift that bale's apply
    refuses unless the operator admits it, and TARBALL.md §5.4 asks the
    worker to enumerate each such path in notes.md and record it in
    forecast_departures. Warning tier: the path may be legitimate drift
    the operator admits at apply — bale's own-forecast gate is the
    enforcement, and this check only makes an undeclared departure
    visible before packing. An entry's `why` is the schema's to judge
    (minLength 1), so a crafter-seeded stub left unfilled is a schema
    finding, not this check's.

    The converse (v0.4.44): a declared entry that is not a departure —
    its path inside resolved_scope, or naming no changes[] path — warns
    FORECAST_DEPARTURE_NOT_A_DEPARTURE at the entry's own path, same
    tier, because it asks the operator to admit something that needs no
    admission (or does not ship).
    """
    request = ctx.get("request")
    if request is None:
        raise CheckSkipped(REQUEST_FLAG_SKIP)
    scope = request.get("resolved_scope")
    if not (isinstance(scope, list)
            and all(isinstance(e, str) for e in scope)):
        raise CheckSkipped("the request carries no resolved_scope list "
                           "(a pack predating the key)")
    changes = ctx["manifest"].get("changes")
    if not isinstance(changes, list):
        return []  # the schema check filed it
    sr = _self_reported(ctx["manifest"]) or {}
    declared_raw = sr.get("forecast_departures")
    declared = {d.get("path") for d in declared_raw
                if isinstance(d, dict)} if isinstance(declared_raw,
                                                      list) else set()
    out = []
    for i, entry in enumerate(changes):
        path = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(path, str) or not path:
            continue  # the schema check filed it
        if path_in_forecast(path, scope) or path in declared:
            continue
        out.append(warning(
            "FORECAST_DEPARTURE_UNDECLARED",
            f"manifest.json:$.changes[{i}].path",
            "a path inside resolved_scope, or a "
            "feedback.self_reported.forecast_departures entry naming it",
            path,
            f"{path} lies outside the request's resolved_scope "
            f"{scope!r} and no forecast_departures entry names it — add "
            f"{{\"path\": {path!r}, \"why\": ...}} to "
            "feedback.self_reported.forecast_departures and enumerate it "
            "in notes.md so the operator can admit it at apply "
            "(TARBALL.md 5.4)",
            headline=f"{path} has no forecast_departures entry",
        ))
    # The declared side (v0.4.44, the registry rider): an entry that
    # declares a departure which is not one — its path inside the
    # forecast, or naming no changes[] path at all. Same warning tier:
    # a spurious declaration misleads the operator's admission at apply
    # (they would be asked to admit a path that needs no admission, or
    # does not ship), but it breaks nothing bale enforces.
    change_paths = {e.get("path") for e in changes if isinstance(e, dict)}
    for j, d in enumerate(declared_raw if isinstance(declared_raw, list)
                          else []):
        dpath = d.get("path") if isinstance(d, dict) else None
        if not isinstance(dpath, str) or not dpath:
            continue  # the schema check filed it
        where = (f"manifest.json:$.feedback.self_reported"
                 f".forecast_departures[{j}].path")
        if dpath not in change_paths:
            out.append(warning(
                "FORECAST_DEPARTURE_NOT_A_DEPARTURE", where,
                "a changes[] path outside resolved_scope",
                dpath,
                f"forecast_departures declares {dpath}, but no changes[] "
                f"entry has that path — a departure is a path this "
                f"response ships; drop the entry, or correct its path to "
                f"the changes[] path it meant (TARBALL.md 5.4)",
                headline=f"{dpath} is declared but ships in no changes[] "
                         f"entry",
            ))
        elif path_in_forecast(dpath, scope):
            out.append(warning(
                "FORECAST_DEPARTURE_NOT_A_DEPARTURE", where,
                "a changes[] path outside resolved_scope",
                dpath,
                f"forecast_departures declares {dpath}, but it lies inside "
                f"the request's resolved_scope {scope!r} — it needs no "
                f"admission at apply; drop the entry (and its notes.md "
                f"enumeration) (TARBALL.md 5.4)",
                headline=f"{dpath} is declared but lies inside the "
                         f"forecast",
            ))
    return out


README_DOC_NAME = "README.md"


def check_readme_in_docs_read(ctx: dict) -> list[dict]:
    """With --request: when the request shipped a brief (its `readme`
    key non-null, TARBALL.md §3.2), some docs_read entry names
    README.md.

    The key exists so a worker learns a brief ships, and AGENT.md's
    reading order puts the brief before any building. The lint cannot
    attest the reading happened — docs_read is self-report — but a
    docs_read that omits the brief, or no docs_read at all, makes a
    skipped brief visible in telemetry. An entry names README.md when
    the file name appears in it (`README.md`, `README.md (the brief)`).
    Warning tier, never a finding: warnings never flip the exit code.
    """
    request = ctx.get("request")
    if request is None:
        raise CheckSkipped(REQUEST_FLAG_SKIP)
    if request.get("readme") is None:
        return []  # no brief shipped (or a pack predating the key)
    sr = _self_reported(ctx["manifest"]) or {}
    docs_read = sr.get("docs_read")
    entries = docs_read if isinstance(docs_read, list) else []
    if any(isinstance(e, str) and README_DOC_NAME in e for e in entries):
        return []
    got = ("docs_read absent" if docs_read is None
           else json.dumps(docs_read))
    return [warning(
        "README_NOT_IN_DOCS_READ",
        "manifest.json:$.feedback.self_reported.docs_read",
        f"an entry naming {README_DOC_NAME} (the request's readme key is "
        "non-null: a brief shipped)",
        got,
        f"the request shipped a brief ({README_DOC_NAME}, per its readme "
        f"key) and no docs_read entry names {README_DOC_NAME} — if the "
        "brief was read, list it; if not, read it before shipping "
        "(AGENT.md's reading order puts it before any building)",
        headline=f"a brief shipped and docs_read does not name "
                 f"{README_DOC_NAME}",
    )]


# DOCS.md §5's standard ADR header line, `- **Date:** YYYY-MM-DD`; the
# recognizer is content-keyed and path-agnostic, because no one ADR home
# holds across projects: they place ADRs under claude/context/adr/,
# adr/, or decisions/, and any .md the response authors with this header
# is a dated artifact whether or not it is an ADR by path.
ADR_DATE_HEADER = re.compile(r"^\s*-\s+\*\*Date:\*\*\s+(\d{4}-\d{2}-\d{2})\b")
ADR_HEADER_WINDOW = 20  # lines scanned for the Date: header
# Any line that opens with a date — a landing note appended by the
# ratification flip, the one dated line a sanctioned ADR modification may
# add (DOCS.md §5). Mirrors DATED in tools/craft_response.py's ADR
# doc-assertion, restated here so the lint stays standalone.
DATED_LINE = re.compile(r"^(?:[-*]\s*)?(\d{4}-\d{2}-\d{2})[:\s]")


def _iso_date_or_none(text: str):
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def check_dated_artifacts(ctx: dict) -> list[dict]:
    """Every dated artifact the response authors is dated from the session
    id, never from the chat's clock (TARBALL.md §1).

    Scope: created and modified .md entries in changes[] whose files/
    copy carries DOCS.md §5's `- **Date:** YYYY-MM-DD` header within
    its first 20 lines. A created one must carry the sid's date
    exactly. A modified one keeps its original header (DOCS.md §5
    confines a modification to the two sanctioned diff shapes, which
    the crafter's ADR doc-assertion proves by reverse transform), so the
    lint never judges it — it flags only a dated line whose date is
    LATER than the sid's date, which is wrong under every clock. An
    earlier-but-re-dated line is deliberately outside this check's
    reach: the lint has no base bytes, and the doc-assertion is the
    gate that catches it.
    """
    manifest = ctx["manifest"]
    sid = manifest.get("session_id")
    sid_date = _iso_date_or_none(sid[:10]) if isinstance(sid, str) else None
    if sid_date is None:
        return [warning(
            "SID_DATE_UNPARSEABLE", "manifest.json:$.session_id",
            "a session id opening with an ISO date (YYYY-MM-DD-<slug>-NNN, "
            "TARBALL.md section 1)", repr(sid),
            "the session id's date could not be read, so the "
            "dated-artifacts check did not run (bale's apply refuses a "
            "session id that does not match the locked session anyway)",
        )]
    changes = manifest.get("changes")
    if not isinstance(changes, list):
        return []
    files_root: Path = ctx["rdir"] / "files"
    out = []
    for i, ch in enumerate(changes):
        if not isinstance(ch, dict):
            continue
        p, action = ch.get("path"), ch.get("action")
        if (not isinstance(p, str) or not p or action not in
                ("created", "modified") or not p.lower().endswith(".md")):
            continue
        if _is_unsafe_relpath(p):
            continue  # changes-mirror filed it
        fpath = files_root / p
        if not fpath.is_file():
            continue  # changes-mirror filed the absent mirror file
        try:
            lines = fpath.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue  # not a text artifact this check can read
        header_date = None
        for ln in lines[:ADR_HEADER_WINDOW]:
            m = ADR_DATE_HEADER.match(ln)
            if m:
                header_date = m.group(1)
                break
        if header_date is None:
            continue  # not a dated artifact
        if action == "created":
            if header_date != sid_date.isoformat():
                out.append(finding(
                    "WRONG_CLOCK_DATE", p,
                    f"- **Date:** {sid_date.isoformat()} (the session id's "
                    f"date)", f"- **Date:** {header_date}",
                    f"changes[{i}] is a created dated artifact whose Date: "
                    f"line is not the session id's date — session ids and "
                    f"every bale timestamp are UTC and may run a day ahead "
                    f"of the date the chat shows; date what you write from "
                    f"the session id, never from the chat (TARBALL.md "
                    f"section 1)",
                ))
            continue
        # modified: only a date from the future is wrong under every clock
        for lineno, ln in enumerate(lines, start=1):
            m = DATED_LINE.match(ln.strip())
            if not m:
                continue
            d = _iso_date_or_none(m.group(1))
            if d is not None and d > sid_date:
                out.append(finding(
                    "WRONG_CLOCK_DATE", f"{p}:{lineno}",
                    f"no dated line later than {sid_date.isoformat()} (the "
                    f"session id's date)", ln.strip(),
                    f"changes[{i}] is a modified dated artifact carrying a "
                    f"line dated after the session id's date — a date from "
                    f"the future is wrong under every clock; date what you "
                    f"write from the session id (TARBALL.md section 1)",
                ))
    return out


def _recompute_mechanical(manifest: dict, findings: list[dict]) -> dict:
    """The lint-computable feedback.mechanical values, derived from this
    run's manifest and accumulated findings.

    One derivation, two consumers: check_feedback_block compares a
    shipped block against it, and --emit-feedback-mechanical serializes
    it — so the flag can only ever print this lint run's own
    computations, never a transcription. The two optional members the
    schema admits (linkage, provenance) are not lint-computable, so they
    are deliberately NOT emitted here: provenance is seeded by the
    crafter's --request (tools/craft_response.py echoes the request's
    provenance verbatim, and the worker fills model_identity), and
    linkage the worker adds by hand when it applies.
    """
    mirror_findings = [f for f in findings
                       if f.get("check") == "changes-mirror"]
    return {
        "response_kind": manifest.get("response_kind", "normal"),
        "schema_valid": not any(
            f.get("check") == "manifest-schema" for f in findings),
        "mirror_agreement": {
            "changes_to_files": not any(
                f.get("code") != "MIRROR_UNDECLARED"
                for f in mirror_findings),
            "files_to_changes": not any(
                f.get("code") == "MIRROR_UNDECLARED"
                for f in mirror_findings),
        },
        "claims_subset": not any(
            f.get("check") == "claims-subset" for f in findings),
    }


def check_feedback_block(ctx: dict) -> list[dict]:
    """feedback.mechanical agrees with this lint's own recomputation.

    Shape is the schema check's job (the feedback block is in
    response-manifest.schema.json); this check verifies the four
    lint-computable values against what the earlier checks actually
    found in THIS run — a disagreement is the tell of a hand-filled or
    stale block (e.g. carried across an edit, or across a compaction,
    AGENT.md section 11.6). Absent block = nothing to verify: the
    field is optional in B1, apply persists it verbatim, and B2 builds
    the telemetry record on it. linkage and provenance are
    self-reported placement/echo data the lint cannot verify, so they
    are schema-checked only.

    Runs last in the registry so ctx["findings"] (the shared list the
    runner accumulates into) already holds every earlier check's
    findings.
    """
    manifest = ctx["manifest"]
    fb = manifest.get("feedback")
    if not isinstance(fb, dict):
        return []  # absent, or schema check already filed the type violation
    mech = fb.get("mechanical")
    if not isinstance(mech, dict):
        return []  # schema check already filed it
    prior = ctx.get("findings", [])
    out = []

    def _mismatch(field: str, expected, got) -> dict:
        return finding(
            "FEEDBACK_MECHANICAL_MISMATCH",
            f"manifest.json:$.feedback.mechanical.{field}",
            f"{expected!r} (recomputed by this lint run)", repr(got),
            f"feedback.mechanical.{field} disagrees with what this lint "
            "run found — mechanical values are computed, never "
            "transcribed; refresh the block by re-running the lint "
            "against the current response directory",
        )

    # The expected values come from the same derivation
    # --emit-feedback-mechanical serializes (_recompute_mechanical), so
    # the paste-ready emission and this verification cannot disagree.
    # Semantics unchanged: schema_valid fails on any manifest-schema
    # finding; mirror_agreement splits by direction (files_to_changes
    # fails on MIRROR_UNDECLARED, changes_to_files on every other
    # changes-mirror finding; kinds that ship no files/ are vacuously
    # true in both directions); claims_subset fails on any
    # claims-subset finding.
    expected = _recompute_mechanical(manifest, prior)

    got_kind = mech.get("response_kind")
    if isinstance(got_kind, str) and got_kind != expected["response_kind"]:
        out.append(_mismatch("response_kind", expected["response_kind"],
                             got_kind))

    got_sv = mech.get("schema_valid")
    if isinstance(got_sv, bool) and got_sv != expected["schema_valid"]:
        out.append(_mismatch("schema_valid", expected["schema_valid"],
                             got_sv))

    ma = mech.get("mirror_agreement")
    if isinstance(ma, dict):
        for direction in ("changes_to_files", "files_to_changes"):
            got_dir = ma.get(direction)
            want = expected["mirror_agreement"][direction]
            if isinstance(got_dir, bool) and got_dir != want:
                out.append(_mismatch(f"mirror_agreement.{direction}",
                                     want, got_dir))

    got_cs = mech.get("claims_subset")
    if isinstance(got_cs, bool) and got_cs != expected["claims_subset"]:
        out.append(_mismatch("claims_subset", expected["claims_subset"],
                             got_cs))

    return out


# The check registry. Session B adds rows (feedback block, provenance
# stamping), it does not restructure the runner. Order matters only in
# that manifest-parse gates everything after it, and that feedback-block
# runs last (it reads the shared findings list the earlier checks fed).
CHECKS: tuple[tuple[str, str, object], ...] = (
    ("manifest-parse",
     "manifest.json exists and parses (TARBALL.md 5.1)",
     check_manifest_parse),
    ("manifest-schema",
     "manifest validates against response-manifest.schema.json",
     check_manifest_schema),
    ("required-artifacts",
     "apply.sh and validation.sh present (TARBALL.md 5.1)",
     check_required_artifacts),
    ("changes-mirror",
     "changes[] <-> files/ both directions; sizes and sha256s recomputed "
     "(TARBALL.md 5.2, 5.2.1, 10.1)",
     check_changes_mirror),
    ("claims-subset",
     "set(claims) is a verbatim subset of validation_will_run "
     "(TARBALL.md 5.3, 10.1)",
     check_claims_subset),
    ("claims-value",
     "every bare-string claims value is pass|fail|untested|unknown "
     "(TARBALL.md 5.3; mirrors bin/bale_validate.py CLAIM_VALUES)",
     check_claims_value),
    ("kind-shape",
     "response-kind shape rules: bailout 5.6.1/5.6.2, clarification 5.9.2, "
     "questions placement",
     check_kind_shape),
    ("generated-artifacts",
     "no changes[] path names a generated artifact (TARBALL.md 5.1 deny "
     "list)",
     check_generated_artifacts),
    ("next-prompt-retired",
     "no next-prompt.md in the response (retired, TARBALL.md 5.5)",
     check_next_prompt_retired),
    ("context-prefix",
     "no changes[] path or docs_read entry carries the request tarball's "
     "context/ prefix (TARBALL.md 3.1)",
     check_context_prefix),
    ("docs-read-stub",
     "a present feedback.self_reported.docs_read is not the unfilled [] "
     "stub (warning tier)",
     check_docs_read_stub),
    ("dated-artifacts",
     "dated artifacts the response authors are dated from the session id "
     "(TARBALL.md 1)",
     check_dated_artifacts),
    # These two descriptions deliberately avoid their subject words
    # (forecast_departures, README.md): the description rides on the
    # [PASS] line, and the pinned outcome is silence — the words appear
    # on the lint's output only when the check warns, carried by the
    # warning's headline and message. (The held first attempt's
    # descriptions named them, so a clean run printed them on [PASS].)
    ("forecast-departures",
     "with --request: every changes[] path outside resolved_scope is "
     "declared as a departure (TARBALL.md 5.4; warning tier)",
     check_forecast_departures),
    ("readme-in-docs-read",
     "with --request: a brief the request shipped is listed among the "
     "docs read (warning tier)",
     check_readme_in_docs_read),
    ("feedback-block",
     "feedback.mechanical agrees with this run's recomputed results "
     "(response_kind, schema_valid, mirror_agreement, claims_subset)",
     check_feedback_block),
)


# ---------------------------------------------------------------------------
# Runner and reporting
# ---------------------------------------------------------------------------

def lint_response_dir(rdir: Path, manifest_schema: dict,
                      diagnostics_schema: dict,
                      request: dict | None = None) -> dict:
    """Run every check; return the full report dict.

    `request` is the parsed request manifest.json from --request, or
    None; the checks that read it report [SKIP] without it.
    """
    checks_report = []
    findings: list[dict] = []
    warnings: list[dict] = []
    ctx = {
        "rdir": rdir,
        "manifest": None,
        "kind": None,
        "manifest_schema": manifest_schema,
        "diagnostics_schema": diagnostics_schema,
        "mirror_files": _list_mirror_files(rdir / "files"),
        # The same list object the runner extends below — later checks
        # (feedback-block) read earlier checks' findings through it.
        "findings": findings,
        "request": request,
    }
    for check_id, description, fn in CHECKS:
        if check_id != "manifest-parse" and ctx["manifest"] is None:
            checks_report.append({
                "id": check_id, "status": "skip",
                "detail": "manifest.json unavailable",
            })
            continue
        try:
            got = fn(ctx)
        except CheckSkipped as skip:
            checks_report.append({
                "id": check_id, "status": "skip", "detail": str(skip),
            })
            continue
        for f in got:
            f["check"] = check_id
            f.setdefault("severity", "error")
        errors = [f for f in got if f["severity"] != "warning"]
        warns = [f for f in got if f["severity"] == "warning"]
        findings.extend(errors)
        warnings.extend(warns)
        if errors:
            status, detail = "fail", f"{len(errors)} finding(s)"
            if warns:
                detail += f", {len(warns)} warning(s)"
        elif warns:
            # The [WARN] line says what the warning is about on its own:
            # the warnings' headlines when they carry one (e.g. naming
            # README.md), else the check's description.
            heads = list(dict.fromkeys(
                w["headline"] for w in warns if w.get("headline")))
            status, detail = "warn", (
                f"{len(warns)} warning(s): "
                + ("; ".join(heads) if heads else description))
        else:
            status, detail = "pass", description
        checks_report.append({
            "id": check_id, "status": status, "detail": detail,
        })
    return {
        "ok": not findings,
        "response_dir": str(rdir),
        "response_kind": (
            ctx["manifest"].get("response_kind", "normal")
            if isinstance(ctx["manifest"], dict) else None
        ),
        "checks": checks_report,
        "findings": findings,
        "finding_count": len(findings),
        # The warning tier (v0.4.30): named, never gating.
        "warnings": warnings,
        "warning_count": len(warnings),
        # The paste-ready feedback.mechanical payload, from the same
        # derivation check_feedback_block verifies against. None when
        # the manifest never parsed — there is nothing honest to emit.
        # (feedback-block findings can't perturb this: the derivation
        # reads only manifest-schema / changes-mirror / claims-subset
        # findings, so post-check computation equals mid-run.)
        "feedback_mechanical": (
            _recompute_mechanical(ctx["manifest"], findings)
            if isinstance(ctx["manifest"], dict) else None
        ),
    }


def render_human(report: dict, stream) -> None:
    print(f"response-lint: {report['response_dir']} "
          f"(response_kind={report['response_kind']!r})", file=stream)
    for chk in report["checks"]:
        tag = {"pass": "[PASS]", "fail": "[FAIL]", "skip": "[SKIP]",
               "warn": "[WARN]"}[chk["status"]]
        print(f"{tag} {chk['id']} — {chk['detail']}", file=stream)
    for f in report["findings"]:
        print(f"  - {f['code']} {f['path']}: {f['message']}", file=stream)
        print(f"      expected: {f['expected']}", file=stream)
        print(f"      got:      {f['got']}", file=stream)
    for w in report.get("warnings", []):
        print(f"  ~ {w['code']} {w['path']}: {w['message']}", file=stream)
        print(f"      expected: {w['expected']}", file=stream)
        print(f"      got:      {w['got']}", file=stream)
    verdict = "CLEAN" if report["ok"] else f"FAIL — {report['finding_count']} finding(s)"
    if report.get("warning_count"):
        verdict += f" ({report['warning_count']} warning(s), non-gating)"
    print(f"result: {verdict}", file=stream)


def _load_schemas(schema_dir: Path | None) -> tuple[dict, dict]:
    if schema_dir is not None:
        m = json.loads((schema_dir / "response-manifest.schema.json")
                       .read_text(encoding="utf-8"))
        d = json.loads((schema_dir / "diagnostics.schema.json")
                       .read_text(encoding="utf-8"))
        return m, d
    return (json.loads(RESPONSE_MANIFEST_SCHEMA_JSON),
            json.loads(DIAGNOSTICS_SCHEMA_JSON))


def _load_request(path: Path) -> dict | str:
    """The --request manifest as a dict, or an error message.

    Argument hygiene only — the file must exist and parse as a JSON
    object. Its keys are read defensively by the two checks that use it
    (a missing resolved_scope skips, a missing or null readme is
    silent), so an older request never errors here.
    """
    if not path.is_file():
        return f"--request: file not found: {path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return f"--request: could not read {path}: {exc}"
    except json.JSONDecodeError as exc:
        return f"--request: {path} is not valid JSON: {exc}"
    if not isinstance(data, dict):
        return (f"--request: {path} is not a JSON object (got "
                f"{type(data).__name__}) — expected a request manifest.json")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="response_lint.py",
        description="Mechanical TARBALL.md section 10.1 self-check for a "
                    "bale response directory. Exit 0 clean, 1 with every "
                    "failure named, 2 on lint error; under "
                    "--emit-feedback-mechanical, 0 whenever the object was "
                    "written.",
    )
    parser.add_argument("response_dir", help="path to the response-NNN directory")
    parser.add_argument("--json", action="store_true",
                        help="emit one JSON report line on stdout; "
                             "human-readable findings go to stderr")
    parser.add_argument("--emit-feedback-mechanical", action="store_true",
                        help="print the paste-ready feedback.mechanical "
                             "object (this run's own computed values) on "
                             "stdout; human-readable findings go to stderr. "
                             "Exits 0 whenever the object was written, "
                             "findings or not (1 only when nothing could be "
                             "emitted). Mutually exclusive with --json")
    parser.add_argument("--request", default=None, metavar="FILE",
                        help="the request's manifest.json: enables the two "
                             "request-reading warnings — a changes[] path "
                             "outside its resolved_scope with no "
                             "forecast_departures entry, and a shipped "
                             "brief (readme non-null) that docs_read does "
                             "not name README.md. Without it both checks "
                             "report [SKIP]")
    parser.add_argument("--schema-dir", default=None,
                        help="directory holding response-manifest.schema.json "
                             "and diagnostics.schema.json to override the "
                             "embedded copies")
    args = parser.parse_args(argv)

    if args.json and args.emit_feedback_mechanical:
        print("response_lint: error: --json and --emit-feedback-mechanical "
              "both claim stdout — pass one", file=sys.stderr)
        return EXIT_ERROR

    rdir = Path(args.response_dir)
    if not rdir.is_dir():
        print(f"response_lint: error: not a directory: {rdir}", file=sys.stderr)
        return EXIT_ERROR
    try:
        schemas = _load_schemas(Path(args.schema_dir) if args.schema_dir else None)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"response_lint: error: cannot load schemas from "
              f"{args.schema_dir}: {exc}", file=sys.stderr)
        return EXIT_ERROR

    request = None
    if args.request is not None:
        request = _load_request(Path(args.request))
        if isinstance(request, str):
            print(f"response_lint: error: {request}", file=sys.stderr)
            return EXIT_ERROR

    try:
        report = lint_response_dir(rdir, *schemas, request=request)
    except OSError as exc:
        print(f"response_lint: error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.emit_feedback_mechanical:
        # Stdout carries only the paste-ready object — the values this
        # run computed, never a transcription (TARBALL.md 5.2.2). The
        # feedback-block mismatch check is unchanged and still guards a
        # stale paste on the next run.
        #
        # Exit code: 0 whenever the object was written, findings or not.
        # The emitter's job is the emission, and its typical input — a
        # crafter-seeded block whose four placeholders are that run's
        # only findings — is exactly what it exists to refresh; exiting 1
        # there broke `emit && paste` chains. The findings still print to
        # stderr, the emitted values still reflect them, and the plain
        # re-run after the paste is the verdict (TARBALL.md 5.2.2). When
        # nothing could be emitted (manifest.json unavailable) there is
        # nothing to paste, so it exits 1 and a chain stops.
        mech = report["feedback_mechanical"]
        if mech is None:
            print("response_lint: cannot emit feedback.mechanical — "
                  "manifest.json unavailable (see findings)",
                  file=sys.stderr)
            render_human(report, sys.stderr)
            return EXIT_FINDINGS
        print(json.dumps(mech, indent=2))
        render_human(report, sys.stderr)
        if not report["ok"]:
            print(f"response_lint: emitted despite "
                  f"{report['finding_count']} finding(s) — exit 0 means the "
                  "object was written; re-run without "
                  "--emit-feedback-mechanical after pasting for the "
                  "verdict", file=sys.stderr)
        return EXIT_CLEAN
    elif args.json:
        print(json.dumps(report, separators=(",", ":"), sort_keys=True))
        render_human(report, sys.stderr)
    else:
        render_human(report, sys.stdout)
    return EXIT_CLEAN if report["ok"] else EXIT_FINDINGS


if __name__ == "__main__":
    sys.exit(main())
