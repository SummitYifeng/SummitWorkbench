# SWB workspace contract v1 (W0 freeze)

Status: frozen for Phase 1 implementation. This is a repository copy for SWB and future SummitKnowledge (SK) conformance. It does not edit the legacy `_vault/conventions.md`.

## Workspace identity and compatibility

Every workspace root contains `.summit-workbench/manifest.json` and a human-readable `conventions.md`. The manifest uses the existing `workspace_id` UUID as a portable identity; it is never derived from the absolute path.

```json
{
  "format": "summit-workbench-workspace",
  "workspace_id": "00000000-0000-4000-8000-000000000001",
  "contract_version": 1,
  "min_reader_version": 1,
  "min_writer_version": 1
}
```

Unknown required format, malformed identity, `contract_version` above the reader's supported version, or minimum versions above the running app are hard errors. A missing manifest is not an invitation to initialize. Initialization is allowed only in an empty directory. A connected compatible root is accepted without rewriting its identity. Git is not part of this format.

## Portable and local state

Portable business files live at the workspace root using the established directories and page types. `.summit-workbench/` contains portable queue, review, import, and external-action records. It is excluded from retrieval. App secrets, OAuth tokens, absolute machine paths, locks, caches, diagnostics, and embeddings remain under the per-user application support directory and never enter the workspace.

## Approval proof v1

An approved Markdown page carries this frontmatter object:

```yaml
approval:
  version: 1
  content_sha256: 9e9c...
  approved_at: "2026-10-02T12:00:00Z"
  operation_id: "op_0123456789abcdef0123456789abcdef"
```

The SHA-256 input is UTF-8 bytes of compact canonical JSON (`ensure_ascii=false`, sorted object keys, separators `,` and `:`) with exactly two top-level keys: `metadata` and `body`. `metadata` includes present values from this allowlist, with YAML date/datetime values normalized to ISO strings and other values in JSON-native form: `title`, `summary`, `type`, `project`, `projects`, `date`, `status`, `decision`, `decision_status`, `replaces`, `superseded_by`, `source`, `workstream`, `area`, `start_at`, `end_at`, `due_date`, `meeting_date`. For `project-main` only, `status: archived` is canonicalized to `status: active`, because archive/reactivate is a lifecycle action. Keys not on the list, including `approval`, are excluded. `body` is the entire Markdown body after frontmatter, converted from CRLF/CR to LF, with trailing whitespace removed from the end of the document and exactly one final LF. UTF-8 BOM is forbidden. JSON values are not otherwise coerced to strings; arrays preserve order. A missing optional metadata key is omitted, not encoded as null.

Approval is valid only when the page is a formal content type, its status is eligible, its approval version is `1`, the digest is a lowercase 64-hex SHA-256 matching the current canonical content, and `approved_at` and `operation_id` are non-empty strings. Reapproval always issues a new operation ID and timestamp. Any changed body or allowlisted semantic field invalidates the old proof. `activity_at`, `updated_at`, UI metadata, and other non-allowlisted fields do not change the proof. Project lifecycle archival is independent from approval and an archived approved page remains eligible.

## Content and retrieval eligibility

Use established types from `_vault/conventions.md` §3 and §4. Formal content retains its existing Markdown representation. The retrieval allowlist for v1 is `project-main`, `note`, `decision`, `meeting-note`, `long-form-thought`, `work-log`, `thread-doc`, and `weekly-review`, subject to valid approval and status in `active`, `paused`, `archived`, `generated`, `applied`, or `superseded`. A future type is excluded until explicitly added to the shared contract.

Always excluded: `source`, `meeting-transcript`, `inbox`, `project-inbox`, drafts, pending-review content, ignored content, all `.summit-workbench/` state, local brief/weekly display files, and unknown types. An original stays excluded even if it contains an approval object. A derived note may be eligible only as a distinct formal page with provenance links; a transcript is never itself promoted into an eligible page.

References use POSIX paths relative to the workspace root without `.md`. A heading anchor is `path#heading`, with the heading text excluding Markdown `#`; a file reference is just `path`. Only `#` and `##` establish addressable blocks, fenced headings do not count, and heading text must resolve uniquely within a page. SWB must preserve these semantics from legacy §9.1; SK adopts the same frozen rules in Phase 4.

## Shared conformance cases

`tests/fixtures/workspace-v1/` is the shared test vector set. `vectors.json` records canonical approval inputs and expected digests. `qualification.json` records eligible and excluded pages, including an approved archived decision, unapproved journal, changed artifact, and approved original. Both implementations should consume these fixtures without editing their expected values.
