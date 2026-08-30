# Controlled Document 水印预览与下载设计

> 日期：2026-08-05  
> 状态：用户授权按推荐方案直接设计并落地  
> 范围：Mushi 受控 PDF 的真实预览、下载、鉴权和审计；不更新其他 Stage。

## 1. 当前缺口

Frappe 的 `list_controlled_documents` 只返回文件名，不返回二进制端点或私有文件 URL。前端已有的 PDF 区域只是元数据示意页；当 `fileUrl` 缺失时，下载按钮只产生提示。直接暴露 Frappe 私有 File URL 会绕过独立的受控文档鉴权、水印与审计，因此不能作为修复方案。

## 2. 服务端交付模型

- 增加预览与下载两个明确的 GET 二进制端点，分别返回 `inline` 与 `attachment` PDF。
- 每次请求重新解析 `frappe.session.user`、唯一 CRM 角色、`account:view` capability、文档存在性、Released 状态与 Direct access；前端传入的姓名、角色或文件路径均不可信。
- 从 `CRM Controlled Document.private_file` 解析并读取 Frappe 私有 File，校验关联关系、PDF 魔数、非空内容及配置的大小上限。
- 用 Frappe 现有 `get_pdf` 为源 PDF 每种页面尺寸生成水印层，再用 bench 环境现有 `pypdf` 合并并扁平写入每页；不新增 Python 依赖。
- 水印在每页斜向重复显示：当前用户姓名、员工账号、Document ID、上海时间、唯一 Download ID、`CONTROLLED COPY`。
- 每次预览或下载生成不同的访问 ID。允许和拒绝均写入 append-only `CRM File Access Audit`，动作区分 `ControlledPreview` 与 `ControlledDownload`；日志不保存文件内容、Cookie 或 Session ID。
- 只返回生成后的 PDF，绝不返回源私有文件 URL、File name 主键或未加水印字节。

## 3. 前端交互

- `CrmApi` 增加 `previewControlledDocument(documentId)` 和 `downloadControlledDocument(documentId)`，均返回现有 `BinaryDownload`。
- Frappe adapter 使用 `credentials: same-origin` 获取原始 Blob；预览创建受控 object URL，并在文档切换、失败和组件卸载时释放。
- 真实预览使用浏览器 PDF `<object>`/`iframe`，下载按钮通过现有 `downloadBlob` 保存服务端返回文件。
- 显示预览加载、错误、重试和下载中状态；不把 API URL直接赋给 DOM，避免绕过错误处理与会话边界。
- Frappe 模式的 Manager 与 Sales/Engineer 一样进入 Mushi 文档库；Mock 模式保留原 Manager 审批演示。

## 4. 安全与失败处理

- Guest、无唯一 CRM 角色、无 capability、非 Direct、非 Released、文件关联异常和无效 PDF 均 fail closed。
- 水印生成失败时不得回退到原文件；返回冻结公开错误码并记录拒绝/失败审计。
- `Content-Disposition` 文件名由服务端生成并净化；预览和下载均设置 `Content-Type: application/pdf`、`Cache-Control: no-store, private`、`X-Content-Type-Options: nosniff`。
- 不在客户端缓存 Blob 到 localStorage/IndexedDB；仅存在于当前页面内存。

## 5. 验收

- 后端测试覆盖权限、私有文件读取、每页水印文本、唯一访问 ID、inline/attachment、允许/拒绝审计及生成失败不泄漏原文。
- 前端测试覆盖 Frappe Manager 文档库、真实预览 Blob、下载 Blob、状态与 object URL 回收；Mock Manager 审批演示不回归。
- 部署后程序化读取生成 PDF，证明每页包含用户标识、Document ID、Download ID 与 `CONTROLLED COPY`；证明输出字节不同于源文件且源私有 URL未出现在列表 DTO。
- 全量前后端测试、Frappe 构建、Docker 健康、HTTP ping 与 `allow_tests=false` 均通过后才可收口。

## 6. 非目标

- 不创建通用文档管理系统或审批引擎。
- 不修改 Mushi 原始 PDF。
- 不部署 Ubuntu Staging，不更新 B1 或其他 Stage。
- 不执行 commit、reset、stash、clean 或 Docker volume 删除。
