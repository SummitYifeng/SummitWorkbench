# SWB Workbench next-version product specification

This specification freezes the user-facing scope for Phase 1 of `ONEDRIVE-WORKBENCH-IMPLEMENTATION-PLAN.md`. The current product remains unchanged until the new build is delivered.

## Main flows

Three input entry points: **记点什么** for unstructured notes and journal shortcuts; **导入会议** for transcript import and explicit processing; **存入文档／产物** for full-text Markdown/text artifacts. Project editing and existing-content editing remain contextual actions.

Review cards expose three independent destinations, all unchecked by default: **沉淀知识**, **更新项目**, **创建飞书任务**. The user previews the exact content and project diff, then submits the selected actions once. Knowledge approval is independent of task approval. Per-destination completion is durable and retryable without repeating successful external actions.

## Workspace and synchronization

The user selects a normal local folder or OneDrive folder. SWB creates or connects a compatible workspace and keeps its identity independent of the path. OneDrive's client owns synchronization; SWB does not claim that local file writes reached the cloud. The user checks OneDrive before handing the workspace to another Mac. App configuration, account authorization, keys, cache, and locks remain local to each Mac.

## Confirmed behavior

- Every version of formal knowledge requires explicit approval, including hand-written notes, artifacts, and project content changes.
- Opening lists, saving raw input, and previewing existing artifacts do not call a model. Model use starts only after an explicit organize/process action.
- Full artifact text is retained. A summary does not replace it or silently update project status.
- Meeting transcripts, references, inbox items, drafts, and auxiliary operation state are never retrieval corpus.
- A changed approved version requires approval again. Automatic activity counters do not modify approved semantic content.
- The portable contract is initialized with the workspace and is usable without SummitKnowledge. Incompatible contract versions are rejected.
- Feishu application credentials are embedded at build time under the existing `RELEASING.md` handling rules; each person still completes their own authorization.

## Outside Phase 1

OneDrive library creation, business sample population, two-Mac handoff testing, and production SummitKnowledge indexing are later phases. Phase 1 uses isolated local fixtures, provider substitutes, and a local arm64 package only.
