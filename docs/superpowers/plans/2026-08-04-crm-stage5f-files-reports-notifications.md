# CRM Stage 5F Files, Reports and Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans, superpowers:test-driven-development and superpowers:systematic-debugging task-by-task.

**Goal:** 在独立 Frappe CRM 数据库中完成联系人私有文件、Demo Artifact、可信报告发布、下载审计和收件人隔离通知，并保持前端默认 Adapter 为 Mock。

**Architecture:** 主文件使用 Frappe Private File；业务元数据使用 `CRM Contact File` / `CRM Demo Artifact`，访问记录使用 append-only `CRM File Access Audit`，通知使用 `CRM Notification Event`。文件服务在写入前执行归属、数量、大小、魔数 MIME 和恶意内容扫描；所有下载按当前会话重新计算 scope。报告只以服务端 canonical Request/Evaluation/Test Run/Selection 生成带文本层和水印的 PDF，客户端上传字节不作为权威内容。通知事件与业务写入同事务，实时推送才在提交后执行。

**Tech Stack:** Frappe Framework 15.116.1、ERPNext 15.118.3、MariaDB 10.6、Python 3.11、Frappe Private File、wkhtmltopdf、Docker Compose、FrappeTestCase、PowerShell HTTP acceptance。

## Global Constraints

- 不创建 ERP Project、Task、Quality Inspection、Asset、Sales Order、Delivery Note、库存或会计单据。
- 不信任客户端文件名、扩展名、MIME、作者、收件人、时间、Artifact 版本或 PDF 正文。
- Contact File 与 Demo Artifact 必须是 private；原始 Frappe `File.file_url` 不作为未授权直链暴露。
- 下载是带审计副作用的授权命令，是通用 GET 只读规则的窄例外；业务实体仍不被下载修改。
- `External Demo Test Report PDF` 只能通过 `releaseDemoTestReport` 生成；`saveDemoArtifact` 必须拒绝该类型。
- Artifact version 在 Evaluation 行锁内分配，并有数据库复合唯一约束 `(evaluation_id, artifact_type, artifact_version)`。
- 通知只从服务端业务事件产生；Frappe 模式不得使用客户端 `createNotifyingApi` 演示员工106通知。
- 前端仍保持 `VITE_API_ADAPTER=mock`，直到后续独立 Adapter/E2E Gate 全部通过。

---

### Task 1: Freeze Stage 5F schemas, limits and authorization contracts

- [x] Write RED schema tests for four DocTypes, server naming, private File links, append-only audit, notification fields and composite Artifact uniqueness.
- [x] Write RED scope tests for Contact File, Demo Artifact and recipient-only Notification list/detail behavior.
- [x] Add exact DocTypes, DocPerm/query hooks, lock whitelist and idempotent composite index installation; migrate twice.
- [x] Add frozen file limits/MIME allowlist and scanner interface with fail-closed production behavior.

### Task 2: Implement Contact File upload/download/delete

- [x] Write RED tests for multipart ownership, count/size caps, magic-byte MIME, malicious content, private storage and server uploadedBy/time.
- [x] Write RED tests for IDOR denial, successful/denied access audit, scoped list and soft metadata deletion without orphaning authorization.
- [x] Implement Contact File service and `/api/v1/contact_files.py` metadata plus raw binary endpoints.
- [x] Verify no unauthorized raw `File` URL can bypass the service scope decision.

### Task 3: Implement Demo Artifact storage and atomic versions

- [x] Write RED tests for Request DOCX eligibility, submitted-stage visibility, role scope and rejection of external-report uploads through the generic endpoint.
- [x] Write RED concurrent allocation tests proving unique, strictly increasing versions and private File persistence.
- [x] Implement save/list/download services and `/api/v1/demo_artifacts.py`; bind every Artifact to canonical Request/Evaluation account scope.
- [x] Verify restart persistence and exact download audit behavior.

### Task 4: Generate and release authoritative external report PDF

- [x] Write RED tests for report selection validation, readiness/stage gates, row-lock CAS and immutable Released state.
- [x] Write RED tests proving client PDF bytes/metrics are ignored, generated PDF has searchable text, server watermark and canonical-data hash.
- [x] Generate PDF from canonical server context, allocate Artifact version atomically and update Evaluation in one savepoint.
- [x] Write recipient notification events in the same transaction and inject failures to prove Artifact/Evaluation/Notification rollback together.

### Task 5: Implement persistent recipient-scoped notifications

- [x] Freeze frontend notification DTO/API signatures for ISO timestamps, stable recipient User IDs, pagination, mark-read and mark-all-read.
- [x] Write RED server tests for cross-session delivery, recipient-only list/read mutation, Manager non-wildcard behavior and server actor/time.
- [x] Implement notification event/list/read APIs and attach events to approved business transitions without client-controlled recipient fields.
- [x] Disable `createNotifyingApi` whenever the Frappe adapter is selected; retain existing Mock behavior only in Mock mode.

### Task 6: Build and close Stage 5F

- [x] Rebuild verified App ZIP/image, migrate twice and require full App textual `OK`.
- [x] Run authenticated multipart/raw-download/report/notification HTTP acceptance across Sales/Engineer/Manager; exact cleanup in `finally`.
- [x] Run concurrency, rollback, private-file restart persistence, IDOR and audit checks.
- [x] Re-run package/Compose contracts and frontend typecheck/full tests/build; default adapter remains Mock.
- [x] Verify health/ports, no ERP business rows, no temp identities, old Docker project/volumes untouched.
- [x] Record every choice/failure/fix/result in repo audit and mirror Desktop copy with SHA-256 equality.

## Stage 5F Acceptance Gate

1. All uploaded bytes are private, bounded, magic-validated, scanned and account-scoped; every download reauthorizes and audits.
2. Artifact versions are database-serialized and unique; generic upload cannot create an external report.
3. Released PDF is generated from canonical server data, has text and watermark, and cannot be altered by client bytes.
4. Notification events persist across users/sessions, expose ISO server time and stable recipient IDs, and only the recipient can mutate read state.
5. Full Frappe, authenticated HTTP, concurrency, rollback, repeated migrate, restart persistence and frontend regression pass while frontend stays Mock.
