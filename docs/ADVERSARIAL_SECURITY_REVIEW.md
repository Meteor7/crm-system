# 对抗性安全审查报告 — semiconductor-crm (QIHENG Demo CRM)

**审查日期：** 2026-08-06（第一轮）+ 2026-08-06（第二轮深审）
**审查范围：** Vue 3 + TypeScript 前端（`src/`）与 Frappe/Python 后端（`backend/apps/rayher_crm/`）
**审查方法：** 代码审计（鉴权、注入、文件处理、并发、信息泄露、业务逻辑）+ 测试套件验证

> 第二轮聚焦第一轮未充分覆盖的面：生产适配器 frappe-adapter、通知系统滥用/提权向量、客户端 DOCX 生成（zip/XXE）、改密端点、线索转换、评估状态机、商机关联 CRUD、booking→installed_tool 转换、DocType 级权限。

---

## 总体评价

**整体安全成熟度高，工程纪律优秀。** 这是我审查过的同类 CRM 实现中安全实践最扎实的之一。绝大多数常见漏洞类别（SQL 注入、XSS、mass assignment、信息泄露、CSRF、文件上传/下载）都已系统性防御。前端 553 个测试 / 85 个文件全部通过，`vue-tsc` 类型检查通过。

### 突出的安全亮点

| 类别 | 实践 |
|------|------|
| **SQL 注入** | 所有用户输入通过 `%s` 参数化绑定；`conditions_for_doctype` 仅返回硬编码 SQL 片段，用户值经 `frappe.db.escape`；`lock_document`/`_lock_relation` 的 doctype 来自白名单 `frozenset`，不接受用户输入 |
| **文件上传** | magic bytes 校验、DOCX zip-bomb 防护（条目数/解压大小上限）、路径穿越防护（拒绝绝对路径/`..`/加密位）、ClamAV INSTREAM 扫描、**fail-closed**（扫描器不可用即拒绝）、扩展名/MIME/内容三者一致性校验 |
| **受控文档交付** | 服务端 SHA-256 完整性校验、私有文件关联验证、个性化水印（含用户全名/ID/时间/access_id）、审计日志、`no-store, nosniff` 头 |
| **Demo 报告** | 明确拒绝客户端字节（`del client_file`）、服务端权威渲染、canonical hash、`_remove_generated_file` 的路径穿越防护、HTML 全程 `html.escape` |
| **鉴权/授权** | 80 个 `@frappe.whitelist` 仅 health 端点 `allow_guest`；`api_endpoint` 装饰器统一捕获异常，**不泄露堆栈**；三层模型：角色唯一性 → capability → 行级 scope |
| **行级安全 (scope.py)** | `permission_query_conditions` + `has_permission` 双重钩子，Engineer 仅见已分配账户，Manager 见全部 |
| **并发** | 乐观锁（`expectedModified` 校验）+ 悲观锁（`SELECT ... FOR UPDATE`）+ savepoint/rollback；Demo→Evaluation 幂等创建（双重 `doc.evaluation` 检查） |
| **金额** | 拒绝 float/bool，强制 `Decimal`，DECIMAL(20,2) 边界与两位小数校验，无精度丢失 |
| **Mass Assignment** | 服务层逐字段构建 dict（`_validate_account_input` 等），不直接灌入 `frappe.get_doc(payload)` |
| **前端 XSS** | 全仓无 `v-html`/`innerHTML`/`eval`/`new Function`/`document.write` |
| **密钥管理** | 仓库启用 git-crypt；`.env*` 未被 git 跟踪；无硬编码密钥/口令；`install_roles` 明确"不创建用户或凭据" |
| **Session** | `enforce_browser_session_cookie` 去除 sid 的 max_age/expires（会话级 cookie） |
| **危险模式** | 全仓无 `eval`/`exec`/`subprocess`/`pickle`/`shell=True`/`os.system` |

---

## 发现的问题

### 🟠 [中] F-1：受控文件与 Demo 产物下载缺失 `no-store` 缓存头

**位置：**
- `backend/.../api/v1/contact_files.py:download_file`
- `backend/.../api/v1/demo_artifacts.py:download_artifact`

**描述：** `no-store, private` + `Pragma: no-cache` + `X-Content-Type-Options: nosniff` 头**仅**对受控文档生效（通过 `frappe.local.response.controlled_document_delivery = True` + `apply_delivery_headers` 钩子）。但同样承载敏感客户数据的 contact files 下载，以及 Demo Request DOCX / 外部测试报告 PDF 下载，都**未设置**该标志位，因此不会获得防缓存头。

```python
# contact_files.py & demo_artifacts.py 的下载端点均缺少：
# frappe.local.response.controlled_document_delivery = True
```

**风险：** 这些响应可被中间代理或共享浏览器缓存留存，导致客户文档/Demo 报告在共享基础设施或公共终端上被后续用户读取。`test_delivery_integration.py` 显式断言受控文档有该头，反证开发者清楚下载默认非 `no-store`——此处是**一致性遗漏**而非有意设计。

**建议：** 为所有二进制下载端点统一设置防缓存头（提取公共 helper）：

```python
# api/v1/_binary_response.py（新增）
def set_binary_download_response(item: dict) -> None:
    frappe.local.response.filename = item["file_name"]
    frappe.local.response.filecontent = item["content"]
    frappe.local.response.type = "download"
    frappe.local.response.content_type = item["mime_type"]
    frappe.local.response.controlled_document_delivery = True  # 触发 after_request 钩子
```

并将三个下载端点统一调用。考虑将该标志位改名为更通用的 `crm_binary_delivery`。

---

### 🟠 [低-中] F-2：Contact File 上传的内存放大（DoS）

**位置：** `backend/.../api/v1/contact_files.py:upload_files`

```python
def upload_files(contactId: str) -> dict:
    request_files = frappe.request.files.getlist("files")
    # ↓ 列表推导先读取"所有"文件的完整内容到内存
    uploads = [{"file_name": ..., "content": item.stream.read(contact_files.MAX_FILE_BYTES + 1)} for item in request_files]
    return success_response(contact_files.upload_contact_files(contactId, uploads))
    # ↑ 这里才检查 len(uploads) > MAX_FILES_PER_REQUEST 和总字节数
```

**描述：** 服务层 `upload_contact_files` 校验 `MAX_FILES_PER_REQUEST=10` 与 `MAX_REQUEST_BYTES=25 MiB`，但 API 层的列表推导**在进入服务层之前**已把请求中的**每个**文件读取最多 ~10 MiB 到内存。攻击者（仅需 Sales 身份）可构造一个含大量文件的 multipart 请求，在服务层拒绝前已耗尽服务器内存。

**缓解因素：** 需认证（Sales 角色）；每个文件上限 ~10 MiB；可能存在上游（gunicorn/nginx/Frappe `max_request_body_size`）请求体限制。

**建议：** 在读取内容**之前**先校验文件数量与累计大小（流式累加）：

```python
def upload_files(contactId: str) -> dict:
    request_files = frappe.request.files.getlist("files")
    if not (1 <= len(request_files) <= contact_files.MAX_FILES_PER_REQUEST):
        raise CrmApiException("VALIDATION_ERROR", "Upload must contain between 1 and 10 files.")
    uploads = []
    running = 0
    for item in request_files:
        content = item.stream.read(contact_files.MAX_FILE_BYTES + 1)
        running += len(content)
        if running > contact_files.MAX_REQUEST_BYTES:
            raise CrmApiException("VALIDATION_ERROR", "Upload exceeds the 25 MiB request limit.")
        uploads.append({"file_name": item.filename, "mime_type": item.mimetype, "content": content})
    return success_response(contact_files.upload_contact_files(contactId, uploads))
```

并确认部署侧的 gunicorn/nginx `client_max_body_size` 已设为合理上限（如 30 MiB）。

---

## 信息级观察（Info）

| ID | 观察 | 说明 |
|----|------|------|
| I-1 | `_document_for_version`（document_access.py）遍历**所有** Controlled Document 寻找版本匹配 | O(n) 扫描，受限于文档总量且需 `account:view` 能力，性能而非安全问题。建议改为按版本字段直接索引查询。 |
| I-2 | Sales 角色对 Customer 返回 `1=1`（scope.py `_customer_condition`） | 销售团队可见全部客户账户，属业务设计。若需更细粒度数据隔离应评审此策略。 |
| I-3 | `bootstrap.get_bootstrap` 向任意已认证 CRM 用户返回全员通讯录（姓名/角色/团队/`bio`） | 用于人员选择器，属设计。注意 `User.bio` 作为"team"字段暴露——确认其不含敏感信息。 |
| I-4 | 前端 mock-adapter（当前唯一适配器）的 `Object.assign` 与 localStorage 操作 | README 已明确声明 mock 适配器仅用于前端 Demo 验收，不代表 Frappe/生产权限/审计。生产必须重实现 `frappe-adapter.ts`。非生产风险。 |
| I-5 | `session_cookie.py` 将 sid 改为会话级（关闭浏览器即登出） | 安全增强，但影响 UX（无持久登录）。确认这是产品预期。 |

---

## 验证情况

- ✅ 前端类型检查：`vue-tsc --noEmit` 通过
- ✅ 前端测试：`vitest run` — 85 文件 / 553 用例全部通过
- ✅ git 跟踪检查：`.env*` 未入库（git-crypt 保护）
- ✅ 危险模式扫描：无 `eval`/`exec`/`subprocess`/`pickle`/`shell=True`
- ✅ 硬编码密钥扫描：无
- ⏸️ 后端测试需 Frappe bench 环境，未在本次运行（建议在目标环境执行 `bench run-tests --app rayher_crm`）

---

## 结论

系统安全基线**显著高于行业平均水平**，体现"安全左移"与纵深防御理念。核心漏洞类别已系统性覆盖，文件处理、并发与权限模型尤为出色。两个发现（F-1 缓存头一致性、F-2 上传内存放大）均为中低风险且修复成本低，建议在下一次迭代中处理。**未见可直接利用的高危或严重漏洞。**

审查完成后，建议补充：
1. 修复 F-1、F-2、F-3、F-4
2. 在目标 Frappe 环境运行完整后端测试套件
3. 确认部署侧 nginx/gunicorn 请求体大小限制
4. （可选）引入自动化 SAST（如 Bandit/Semgrep）与依赖扫描到 CI

---

# 第二轮深审附录（2026-08-06）

第二轮对第一轮未深入的子系统做了对抗性深审。**结论：未发现新的高危或严重漏洞；系统的安全模式在各子系统中高度一致。** 新增 3 项低危/信息级观察。

## 第二轮复核通过的子系统

| 子系统 | 复核结论 |
|--------|----------|
| **frappe-adapter.ts**（生产适配器） | 非 GET 请求附带 `X-Frappe-CSRF-Token`；`credentials: same-origin`；错误归一化**不泄露服务端异常文本**；二进制下载的 Content-Disposition 解析安全（按 `/\\` 切分取 basename、剔除控制字符） |
| **通知系统（notifications.py）** | `create_notification` 仅服务端内部调用（非对外端点），recipient 必须是启用且持 CRM 角色的 User；route 校验须以 `/` 开头且非 `//`（防协议相对/开放重定向）；category/source_doctype 白名单校验。route 在所有调用点均为硬编码或服务端生成值，客户端无法注入任意 route |
| **客户端 DOCX 生成（demo-request-docx.ts）** | 模板为受信本地资产；单元格填充用 `textContent`（非 innerHTML），无 XML/XSS 注入；手写 ZIP 解析器仅处理受信模板；产物上传时后端会以 magic bytes + ClamAV + DOCX zip 校验重新视为不可信输入 |
| **改密端点（account.py）** | 仅能修改**当前会话用户**自身口令（`frappe.session.user`，无 user 参数）；`check_password` 校验旧口令；无法用于横向/纵向提权 |
| **线索转换（leads.py:convert_lead）** | savepoint/rollback + 幂等（重试返回既有 ID）；复用账户/联系人/站点均经 `_require_*` 作用域检查；金额 `Decimal` 校验、email 校验；转入账户需调用方可读 |
| **评估状态机（evaluations.py）** | `STATUS_NEXT` 严格转换；Testing 前须双准备完成；Internal Review 前须有 Completed Test Run；Customer Review 前须 report 就绪；test run 数值校验（capture/falsePositive ∈ [0,100]、wph ≥ 0、`math.isfinite`、拒绝 bool）；锁定后二次校验状态 |
| **商机关联 CRUD（opportunities.py）** | 所有操作经 `_require_opportunity` 父级作用域检查 + `_lock_relation` 确认关联归属（防跨商机操纵）；contact 须属于同账户；无 mass assignment |
| **booking→installed_tool 转换** | 锁定前后双重校验状态（须 Confirmed、未转换）；site 须属于 booking 账户；Engineer 重分配守卫；savepoint/rollback |
| **DocType 级权限** | 全部 doctype JSON **无** Guest / "All" 角色授权；行级安全完全由代码层 `permission_query_conditions` + `has_permission` 钩子承担 |

## 第二轮新增发现

### 🟡 [低] F-3：列表端点 N+1 查询放大（性能 DoS）

**位置：** 各 `list_*` 服务（`accounts.py`、`contacts.py`、`leads.py`、`demo_requests.py`、`evaluations.py`、`visits.py`、`opportunities.py` 等）

**描述：** 列表端点先 `SELECT ... name ... LIMIT/OFFSET` 取行，再对每行执行 `_serialize(frappe.get_doc(..., row.name))`；而每个 `_serialize` 内部又多次调用 `frappe.db.get_value`（账户名、segment、short_name 等）。以 `pageSize=200`（`MAX_PAGE_SIZE`）计，单次列表请求可触发 **数百至上千次** DB 查询。叠加 `page` 参数仅校验为正整数而**无上限**（如 `page=10^12` 产生巨量 OFFSET），已认证用户可放大 DB 负载。

**风险：** 低。需认证；属可用性/性能而非机密性。但多用户并发可形成慢查询放大。

**建议：**
- 序列化所需关联字段改用 `JOIN`/批量 `get_values` 一次性取出，消除 N+1；
- 对 `page` 设置合理上限（如 ≤ 1000）或强制 `keyset pagination`。

---

### 🟡 [低] F-4：上传文件名校验未拦截 CRLF（潜在响应头注入，纵深防御）

**位置：** `services/file_security.py:validate_and_scan`

**描述：** 文件名校验拦截 `("/", "\\", "\0")` 并要求等于 `basename`，但**未拦截** `\r`/`\n`。该文件名随后经 `frappe.local.response.filename` 流向下载端点的 `Content-Disposition` 头。是否可利用**取决于 Frappe 内核是否对该值做清洗/引号转义**——若 Frappe 未清洗且直接拼入头，含 CRLF 的文件名可能导致 HTTP 响应拆分/头注入。

**风险：** 低。实际可利用性依赖 Frappe 版本的头清洗行为；且攻击者需先具备上传权限（Sales）。属纵深防御缺口。

**建议：** 在 `validate_and_scan` 的禁用字符集中补充控制字符：
```python
if any(char in normalized for char in ("/", "\\", "\0") or ord(char) < 0x20):
    raise CrmApiException("VALIDATION_ERROR", "File name is invalid.")
```

---

### ⚪ [信息] F-5：serial 唯一性为 SELECT-then-INSERT（轻微 TOCTOU）

**位置：** `services/installed_tools.py:_unique_serial`

**描述：** 序列号唯一性靠 `SELECT ... LIMIT 1` 检查后 `insert`，若 doctype 无 DB 级唯一索引，两个并发转换请求可同时通过检查并各自插入重复 serial。

**风险：** 信息级。属数据完整性而非安全；需认证 + `deal:write`。

**建议：** 在 `CRM Installed Tool.serial` 上添加 DB 级唯一索引（`setup/indexes.py`），将唯一性下沉到数据库层。

---

### ⚪ [信息] 其他复核确认项

- **无对外端点可注入任意通知 recipient/route**（`create_notification` 仅服务端调用）。
- **`update_password` 无横向提权**（仅作用于 `frappe.session.user`）。
- **`weighted_decimal_string` / `aggregate_by_currency`** 使用 `Decimal` 且校验 `MAX_DECIMAL_20_2` 边界，无溢出。
- **密码策略**：min 8 + 含字母 + 含数字；无 max 上限/常见口令字典检查（Frappe 后端 bcrypt 截断 72 字节，影响有限）。
- **无 SSRF/LFI**：wkhtmltopdf 渲染的 HTML 全部服务端构造且 `html.escape`；ClamdScanner 仅连 env 配置的 clamav 主机。
- **`change_password` 无独立速率限制**，但 Frappe 有账户级登录锁定；改密处验证的是自身旧口令，不构成对他人账户的暴力破解面。

## 第二轮总结

第二轮深审覆盖了第一轮未触及的全部主要子系统，再次确认了**纵深防御的一致性与高成熟度**。未发现可提权或越权的业务逻辑漏洞。新增 3 项（F-3 性能放大、F-4 CRLF 纵深防御、F-5 serial TOCTOU）均为低危/信息级，修复成本低。**两轮审查合计未发现高危或严重漏洞。**
