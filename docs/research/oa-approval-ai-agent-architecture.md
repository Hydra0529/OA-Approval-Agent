# OA 审批 AI Agent：架构路线对比（研究笔记）

> 范围：公司 OA 审批场景的流程监控、多日流程建模（BPMN + 报告）、PDF 制度知识学习（无微调）、用 AI 能力替代/模拟规则型 BPM。  
> 约束：云端开源/开放权重 LLM（DeepSeek / Qwen 等），不 fine-tune。  
> 日期：2026-08-04

---

## 推荐结论（先读）

| 阶段 | 选哪条 | 原因 |
|------|--------|------|
| **2–4 周 MVP** | **A2 混合：轻量规则/状态机 + LLM + RAG** | 审批合规不能全靠 LLM；SLA/下一节点可用确定性表 + LLM 解释 |
| **有历史事件日志后** | **叠加 A3 流程挖掘** | BPMN/瓶颈/周期用 pm4py 从日志发现，LLM 只写报告 |
| **勿作 MVP 主路径** | **纯 A1 RAG Agent 替代 BPM** | 可演示，但路由/权限/审计不可靠 |
| **可选并行** | **A4 文档上传优先** | 无 OA API 时快速落地；正式集成再接 webhook |

---

## 四条架构路线

### A1 — RAG + LLM Agent（文档驱动的“软工作流”）

**做法**  
- PDF 制度/流程说明 → 切块 → 向量库 RAG。  
- Agent（工具调用）读当前单据上下文，检索政策，输出：下一节点、预估耗时、风险点、自然语言说明。  
- 可选：让 LLM 生成 BPMN XML / Mermaid，前端用 bpmn-js 渲染。

**栈建议**  
- 后端：Python（FastAPI）+ LangGraph agentic RAG（检索仅在需要时触发）  
- 前端：TypeScript + React + [bpmn-js](https://bpmn.io/toolkit/bpmn-js/)  
- 向量库：Qdrant / Chroma（MVP 用 Chroma，多租户/生产用 Qdrant）  
- LLM：DeepSeek OpenAI 兼容 API（`https://api.deepseek.com`，模型如 `deepseek-v4-flash` / `deepseek-v4-pro`）或 Qwen OpenAI 兼容端点；私有化可 vLLM OpenAI 兼容服务  
- PDF：PyMuPDF / pdfplumber + 按章节切块；表格单独结构化

**集成**  
- 主：Webhook（提交/节点变更）推送 case 快照 → Agent 推理 → 写回监控面板。  
- 辅：文档上传（制度 PDF、导出的审批单截图/PDF）。

| Pros | Cons |
|------|------|
| 最快体现“会读制度” | 下一节点/时限易幻觉 |
| 无 OA 深度对接也能 demo | 不能当真替代 BPM 引擎 |
| 与云 LLM 即插即用 | BPMN 由 LLM 生成时语义常不合法 |

**何时选**：售前 demo、知识问答、解释“为什么要这个附件”；**不要**单独承担路由与合规。

---

### A2 — 混合：规则/状态机 + LLM + RAG（推荐 MVP）

**做法**  
- **确定性层**：流程模板（JSON/YAML 或简化 BPMN）：节点、角色、条件（金额、部门、费用类型）、SLA 天数。  
- **LLM 层**：RAG 解释政策；从非结构化描述中抽取字段填规则引擎；生成用户可读进度与风险摘要；异常时提出“建议动作”（人工确认后执行）。  
- **Agent 工具**：`get_case` / `match_template` / `estimate_sla` / `search_policy` / `render_status` — LLM **不得**直接改审批状态，除非经审批人确认的 tool gate。

**栈建议**  
- 同 A1，加：轻量规则引擎（自研 decision table / 或 Drools 级能力视团队而定；MVP 用 Python dict + 条件表达式即可）。  
- 时限：历史中位数/P75 表（无日志时用模板默认 SLA）。  
- 结构化输出：JSON Schema / tool calling（DeepSeek/Qwen 均支持 OpenAI 风格 tools）。

**集成**  
- **优先 Webhook/API**：`case.submitted` / `task.completed` → 更新状态机 → 异步 LLM 解释与监控推送。  
- PDF 上传：只更新知识库与模板草案（LLM 提议规则 diff，人审后入库）。

| Pros | Cons |
|------|------|
| 可审计、可回放 | 需维护模板/规则 |
| 监控准确（下一节点来自引擎） | 初装规则成本 |
| LLM 价值集中在解释与抽取 | “完全取代 BPM”叙事弱，但产品可靠 |

**何时选**：真实试点、要上生产的监控与助手；**2–4 周 MVP 默认选这条**。

---

### A3 — 流程挖掘（Process Mining）+ LLM

**做法**  
- 事件日志（case_id, activity, timestamp, resource, 金额等）→ [pm4py](https://processintelligence.solutions/pm4py/api/api/pm4py.discovery.html) `discover_bpmn_inductive` / DFG / 绩效指标。  
- LLM：把发现结果 + RAG 政策写成分析报告；标注瓶颈、变异路径、合规偏离（对照模板）。  
- 前端：导出 BPMN XML → bpmn-js 展示；热力/耗时叠加注解。

**栈建议**  
- Python：pm4py + pandas；报告生成用同一 LLM 网关。  
- 事件存储：Postgres（event_log 表）或直接 Parquet。  
- 可视化：bpmn-js + 自绘周期统计图。

**集成**  
- **API/Webhook 写事件流**是正道；批量导出 CSV/XES 也可。  
- 纯 PDF 审批单上传：需 OCR/抽取才能变事件，成本高，仅作补充。

| Pros | Cons |
|------|------|
| 多日流程建模有实证基础 | 依赖足够事件日志 |
| BPMN 来自算法而非幻觉 | MVP 期常缺数据 |
| 瓶颈/变异分析强 | 与“制度理解”解耦，需另接 RAG |

**何时选**：客户能提供 ≥ 数周历史日志，或目标是“流程诊断/再造”；与 A2 **叠加**，不替代规则层。

---

### A4 — 文档优先 / 上传驱动（无 OA API 时的落地形态）

**做法**  
- 用户上传：制度 PDF + 审批单导出 PDF/Excel。  
- 管道：解析 → 结构化 case →（可选）匹配模板 → RAG 问答 + 进度估计。  
- 后续再接 OA webhook，复用同一领域模型。

**栈**：同 A2，入口换成 multipart 上传与定时拉取文件夹。

| Pros | Cons |
|------|------|
| 绕过 IT 对接周期 | 实时性差、字段不全 |
| 适合 PoC | 难做准确 SLA |

**何时选**：对接排期长、先要业务侧可见成果；正式监控仍应迁到 webhook。

---

## 技术栈速查（可执行默认）

| 层 | 选择 | 备注 |
|----|------|------|
| 语言 | **Python** 服务 + **TS** 前端 | 挖掘/RAG 在 Python；UI/BPMN 在 TS |
| Agent | LangGraph（或轻量自研 tool loop） | 官方 agentic-RAG 模式可参考 LangChain 文档 |
| RAG | LlamaIndex 或自研 ingest | PDF → chunk → embed → retrieve |
| Vector | Chroma（demo）/ Qdrant（prod） | |
| BPMN | pm4py 发现 + bpmn-js 展示 | LLM 只辅助标注，不主生成拓扑 |
| LLM | DeepSeek API 或 Qwen 兼容 API；可选 vLLM 自托管 | 换 `base_url` + `model` 即可 |
| OA | Webhook 入站 + 可选 REST 回写评论/抄送 | 写操作需人工确认门闩 |

**LLM 选型提示**  
- Demo/成本：DeepSeek `deepseek-v4-flash`。  
- 长报告/复杂抽取：`deepseek-v4-pro` 或 Qwen 旗舰兼容模型。  
- 内网：vLLM 提供 OpenAI 兼容 `/v1/chat/completions`，应用层零改。

---

## 数据准备策略（合成 OA + PDF 知识库）

### 1) 合成事件日志（支撑监控 + 挖掘）

生成 3–5 条主流程，例如：费用报销、采购申请、请假、合同审批、用章。

每条 case 字段：

```text
case_id, process_type, amount, dept, applicant_level,
activity, actor_role, timestamp, outcome, comment
```

生成规则（可脚本化）：

1. 用模板定义合法路径与分支（金额阈值、部门会签）。  
2. 节点间耗时用对数正态/截断正态采样（工作日 9–18 点）。  
3. 注入 10–20% 变异：驳回重提、加签、超时。  
4. 导出：`events.csv`（挖掘）+ `cases.json`（监控 API）。

规模建议 MVP：每流程 200–500 cases，合计 ~1k–2k 轨迹。

### 2) PDF 知识库

- 5–15 份：制度摘要、审批权限表、SLA 说明、附件清单、FAQ。  
- 切块：标题层级优先；表格转 Markdown/JSON；块 metadata：`doc_id, section, process_type, effective_date`。  
- 每块附 **人工金标准 Q&A 20–50 条** 做检索/回答回归（非微调，仅评测）。

### 3) 流程模板（给 A2）

从制度手工或 LLM 辅助抽出 YAML，例如：

```yaml
id: expense_v1
nodes: [submit, dept_manager, finance, cashier, end]
transitions:
  - from: submit
    to: dept_manager
  - from: dept_manager
    to: finance
    when: amount > 0
  - from: finance
    to: cashier
    when: amount >= 5000   # 示例阈值
sla_days: { dept_manager: 1, finance: 2, cashier: 1 }
```

LLM 可生成草案，**必须人审后**再生效。

---

## OA 集成模式

| 模式 | 用途 | 建议 |
|------|------|------|
| **Webhook / 事件 API** | 实时监控、下一节点、SLA 倒计时 | 生产默认；payload 含 case_id + 当前节点 + 关键字段 |
| **REST 拉取** | OA 无推送时轮询任务中心 | 补救方案；注意限流 |
| **文档上传** | PoC、制度入库、无 API | 并行入口，勿作唯一生产路径 |
| **回写 OA** | 评论/提醒/抄送 | 只做建议+确认；禁止 Agent 静默改路由 |

最小 webhook 契约示例：

```json
{
  "event": "case.submitted",
  "case_id": "EXP-2026-00142",
  "process_type": "expense",
  "fields": { "amount": 6800, "dept": "R&D" },
  "current_node": "submit",
  "submitted_at": "2026-08-04T09:00:00+08:00"
}
```

系统响应（监控服务）：

```json
{
  "next_node": "dept_manager",
  "eta_days": 1.2,
  "confidence": "high",
  "basis": "template:expense_v1",
  "policy_refs": ["finance-policy#3.2"],
  "narrative": "金额超过 5000，财务节点预计 2 个工作日…"
}
```

---

## MVP 范围（2–4 周）

### Week 1 — 骨架与数据

- 合成 3 流程事件日志 + 8–10 份 PDF 入库。  
- FastAPI：`POST /webhooks/oa`、`POST /kb/upload`、`GET /cases/{id}/monitor`。  
- 前端：案件列表 + 进度时间线（先不做完美 BPMN）。

### Week 2 — A2 核心

- YAML 流程模板 + 规则匹配下一节点/SLA。  
- RAG：政策问答与“依据引用”。  
- LLM：生成监控叙述（强制引用 template + policy chunks）。

### Week 3 — 建模与可视化

- pm4py：按 process_type 发现 BPMN + 平均/ P75 耗时。  
- bpmn-js 只读展示；报告 PDF/Markdown（瓶颈 Top3、变异路径）。  
- 评测集：节点预测准确率、SLA 误差、RAG 引用命中。

### Week 4（可选）— 打磨与试点

- 接一个真实 OA 沙箱 webhook 或继续 mock。  
- 人工确认门闩、审计日志、多租户隔离（若需要）。  
- Demo 脚本：提交 → 监控卡片 → BPMN → 报告一键生成。

**MVP 明确不做**：微调、全自动改签/驳回、完整 Camunda 级引擎替换、复杂组织架构同步。

---

## 选型决策树（一句话）

```text
有事件日志且要诊断瓶颈？ → A2 + A3
要上生产监控/合规？     → A2（规则为准，LLM 为辅）
只有 PDF、要两周出彩？   → A4 + A1（解释层），规则用手写最小模板
想“AI 取代 BPM”叙事？   → 对外讲 A1，对内仍落 A2 门闩
```

---

## 主要来源

1. DeepSeek API（OpenAI/Anthropic 兼容）：https://api-docs.deepseek.com/  
2. Qwen OpenAI 兼容：https://docs.qwencloud.com/api-reference/toolkitframework/openai-compatible/overview  
3. pm4py BPMN discovery：https://processintelligence.solutions/pm4py/api/api/pm4py.discovery.html  
4. bpmn-js：https://bpmn.io/toolkit/bpmn-js/  
5. LangGraph agentic RAG：https://docs.langchain.com/oss/python/langgraph/agentic-rag  

---

## 落地行动清单（下一迭代可直接开工）

1. 定 3 条示范流程 + YAML 模板。  
2. 脚本生成合成日志与配套制度 PDF。  
3. 搭 LLM 网关（DeepSeek/Qwen，统一 OpenAI SDK）。  
4. 实现 A2 监控 API + RAG 解释。  
5. 第 3 周挂上 pm4py → bpmn-js。  
6. 用金标准集卡节点预测与引用质量，再谈是否加深 Agent 自治。
