# QIHENG Demo 七页面前端重设计

**日期：** 2026-07-20
**状态：** 用户已确认先完成七个页面
**范围：** 仅前端视觉与交互原型；使用开发模拟数据，不接入 Frappe 后端

## 1. 目标

在现有 QIHENG Demo 配色、AppShell、Vue 3、TypeScript 和组件体系上，完成七个可浏览、可交互且相互关联的业务页面，用于验证新的产品范围、信息架构和管理会议价值。现有客户、拜访、需求、合同等页面与路由保留，但本轮主导航切换到新的七页面工作区。

开发模拟数据只存在于前端数据模块，不写入 `localStorage`，页面不直接读取散落常量。后续接入 Frappe 时以同一页面模型替换数据源，不重新设计页面。

## 2. 七个页面

1. **管理驾驶舱**：销售预测、Demo、设备服务、升级流程、文档合规和管理关注事项。
2. **Opportunity Strategy**：机会选择、Forecast Category、Buying Influence Coverage、Strength、Red Flag、Information Needed 和 Action Plan。
3. **Demo Request**：申请、Wafer Sample、Demo Execution、Test Run、客户确认和商机回写关系。
4. **Installed Tools**：设备列表、序列号、客户 Site、交付里程碑、软件版本、质保和服务状态。
5. **Service Calendar**：团队周排期、Service Work Order、人工负责人、时间冲突、逾期和工作负载。
6. **Procedure Run**：软件升级阶段门、检查项、证据、签字、偏差和回滚状态。
7. **Document Center**：文档目录、Current Version、访问策略、访问申请、水印下载说明和审计记录。

## 3. 信息架构

主导航按业务域分组：

- 管理中心：管理驾驶舱
- 销售与验证：Opportunity Strategy、Demo Request
- 设备与服务：Installed Tools、Service Calendar
- 质量与知识：Procedure Run、Document Center

桌面端保留左侧固定导航和顶部全局搜索；小屏继续使用抽屉式导航。所有页面沿用深海军蓝、青绿、暖白和黄绿色强调色，不引入 Salesforce 配色。

## 4. 页面交互

- 列表型页面支持本地筛选和选择详情。
- Opportunity Strategy 选择不同商机时同步更新关系覆盖、风险与行动。
- Demo Request 选择项目后展示对应 Wafer、Test Run 和验收信息。
- Installed Tools 选择设备后展示生命周期与版本健康度。
- Service Calendar 支持按团队查看周排期并突出冲突或逾期任务。
- Procedure Run 的检查项可在当前会话内切换完成状态，用于演示阶段门。
- Document Center 可按分类筛选；无直接权限的文档显示访问申请状态，不返回真实文件。

## 5. 数据与安全边界

- 模拟记录统一保存在 `src/demo/operations-data.ts`。
- 模拟数据不包含真实员工密码、客户机密、Token 或真实下载链接。
- 文档下载、水印、审批、签字和文件访问仅演示界面状态，不伪装成已完成的安全能力。
- 新页面不改变现有 `CrmApi` 和 Frappe API 契约；后端接入将在页面验收后另行设计。

## 6. 验收标准

- 七个路由均可通过主导航进入，无空白页或占位页。
- 1366px、1440px 和移动窄屏下不出现主要内容遮挡。
- 页面共享统一的指标卡、状态、列表、详情和风险表达方式。
- Opportunity、Demo、设备、工单、流程和文档之间的关联信息可理解。
- 至少验证商机选择、Demo 选择、流程检查项和文档筛选四类交互。
- `pnpm test` 的相关测试、`pnpm typecheck` 和 `pnpm build` 通过。

## 7. 实施优先级调整

用户进一步确认先完成 P0 决策与 P1：核心 Sales CRM、Demo Request/Wafer/Test Run、Controlled Documents MVP 和最小版 Installed Tool。Service Calendar、Procedure Run 和扩展管理分析保留在七页面总体目标中，但不进入第一批交付。
