import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  api,
  CaseDetail,
  PolicyFile,
  PortfolioItem,
  Template,
  UploadPolicyResult,
} from "./api";
import BpmnViewer from "./BpmnViewer";
import CalendarPanel from "./CalendarPanel";

const statusLabel: Record<string, string> = {
  running: "进行中",
  completed: "已完成",
  rejected: "已驳回",
};

export default function App() {
  const [items, setItems] = useState<PortfolioItem[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [departments, setDepartments] = useState<Array<{ id: string; name: string }>>([]);
  const [selected, setSelected] = useState<CaseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"timeline" | "bpmn" | "report" | "plan">("timeline");
  const [evalInfo, setEvalInfo] = useState("");
  const [showSubmit, setShowSubmit] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [deletePreset, setDeletePreset] = useState<string[]>([]);
  const [supplementFor, setSupplementFor] = useState<PortfolioItem | null>(null);
  const [calKey, setCalKey] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [p, t, d] = await Promise.all([
        api.portfolio(),
        api.templates(),
        api.departments(),
      ]);
      setItems(p.items);
      setTemplates(t);
      setDepartments(d.departments || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
      setCalKey((k) => k + 1);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function openCase(id: string) {
    setError("");
    try {
      const detail = await api.caseDetail(id);
      setSelected(detail);
      setTab(detail.case.fields?.generated ? "plan" : "timeline");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function runEval() {
    try {
      const r = await api.eval();
      setEvalInfo(
        `金标准评测：${r.correct}/${r.total}，准确率 ${(r.accuracy * 100).toFixed(1)}%`
      );
    } catch (e) {
      setEvalInfo(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="page">
      <header className="top">
        <div>
          <p className="brand">OA 审批 AI Agent</p>
          <h1>项目群清单</h1>
          <p className="sub">
            按每次申报生成审批路径 · 读材料、对制度、查当地限制 · 改制度 PDF 会影响日历并行容量
          </p>
        </div>
        <div className="actions">
          <button type="button" className="ghost" onClick={() => void load()}>
            刷新
          </button>
          <button type="button" className="ghost" onClick={() => void runEval()}>
            运行评测
          </button>
          <button type="button" className="ghost" onClick={() => setShowUpload(true)}>
            上传制度
          </button>
          <button
            type="button"
            className="ghost danger"
            onClick={() => {
              setDeletePreset([]);
              setShowDelete(true);
            }}
          >
            删除项目
          </button>
          <button type="button" className="primary" onClick={() => setShowSubmit(true)}>
            提交申报
          </button>
        </div>
      </header>

      {evalInfo ? <p className="banner">{evalInfo}</p> : null}
      {error ? <p className="error">{error}</p> : null}

      <CalendarPanel refreshKey={calKey} onOpenCase={(id) => void openCase(id)} />

      <section className="panel">
        <div className="panel-head">
          <h2>审批项目列表</h2>
          <span>{loading ? "加载中…" : `共 ${items.length} 条`}</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>单据名称</th>
                <th>类型</th>
                <th>级别</th>
                <th>申请部门</th>
                <th>当前节点</th>
                <th>下一步时间线</th>
                <th>停滞原因</th>
                <th>预计时间</th>
                <th>累计时长</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.case_id} onClick={() => void openCase(row.case_id)}>
                  <td className="link">{row.title}</td>
                  <td>{row.category}</td>
                  <td>{row.level}</td>
                  <td>{row.dept}</td>
                  <td>
                    {row.current_node_name}
                    <small>{row.current_role}</small>
                  </td>
                  <td className="next">{row.next_summary}</td>
                  <td className="stall">
                    {row.stall_reason ? (
                      <span className={`pill stall-${row.stall_code || "other"}`}>
                        {row.stall_reason}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    {row.planned_start} ~ {row.planned_end}
                  </td>
                  <td>{row.duration_days} 天</td>
                  <td>
                    <span className={`pill ${row.status}`}>
                      {statusLabel[row.status] || row.status}
                    </span>
                  </td>
                  <td className="ops">
                    <button
                      type="button"
                      className="ghost compact"
                      disabled={row.status !== "running"}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSupplementFor(row);
                      }}
                    >
                      材料补充
                    </button>
                    <button
                      type="button"
                      className="ghost compact danger"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeletePreset([row.case_id]);
                        setShowDelete(true);
                      }}
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {selected ? (
        <aside className="drawer">
          <div className="drawer-head">
            <div>
              <h2>{selected.case.title}</h2>
              <p>
                {selected.case.case_id} · {selected.case.category} ·{" "}
                {selected.case.dept} · {selected.case.applicant}
                {selected.case.amount > 0 ? ` · ¥${selected.case.amount}` : ""}
              </p>
            </div>
            <button type="button" className="ghost" onClick={() => setSelected(null)}>
              关闭
            </button>
          </div>
          <p className="next-line">{selected.next_summary}</p>
          {selected.stall_reason ? (
            <p className="stall-line">{selected.stall_reason}</p>
          ) : null}
          {selected.department_load ? (
            <p className="load-line">
              当前部门 {selected.department_load.name}：{selected.department_load.load}/
              {selected.department_load.parallel_limit} 单并行
              {selected.delay_days ? `，额外延迟 ${selected.delay_days} 个工作日` : ""}
            </p>
          ) : null}
          <div className="tabs">
            {(
              [
                ["plan", "生成方案"],
                ["timeline", "时间线"],
                ["bpmn", "BPMN"],
                ["report", "分析报告"],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                type="button"
                className={tab === k ? "active" : ""}
                onClick={() => setTab(k)}
              >
                {label}
              </button>
            ))}
          </div>
          {tab === "plan" ? <GeneratedPlan detail={selected} /> : null}
          {tab === "timeline" ? (
            <ol className="timeline">
              {selected.timeline.map((step) => (
                <li key={step.node_id} className={step.status}>
                  <strong>{step.node_name}</strong>
                  <span>{step.role}</span>
                  <p>{step.summary}</p>
                </li>
              ))}
            </ol>
          ) : null}
          {tab === "bpmn" ? <BpmnViewer xml={selected.bpmn_xml} /> : null}
          {tab === "report" ? (
            <div className="report">
              <pre>{selected.report}</pre>
              {selected.citations?.length ? (
                <>
                  <h3>制度引用</h3>
                  <ul>
                    {selected.citations.map((c, i) => (
                      <li key={i}>
                        <em>{c.source}</em>
                        <p>{c.text}</p>
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
            </div>
          ) : null}
        </aside>
      ) : null}

      {showUpload ? (
        <UploadPolicyModal
          onClose={() => setShowUpload(false)}
          onDone={async () => {
            await load();
          }}
        />
      ) : null}

      {showSubmit ? (
        <SubmitModal
          templates={templates}
          departments={departments}
          onClose={() => setShowSubmit(false)}
          onDone={async (detail) => {
            setShowSubmit(false);
            await load();
            setSelected(detail);
            setTab(detail.case.fields?.generated ? "plan" : "timeline");
          }}
        />
      ) : null}

      {showDelete ? (
        <DeleteProjectsModal
          items={items}
          presetIds={deletePreset}
          onClose={() => setShowDelete(false)}
          onDone={async (deletedIds) => {
            setShowDelete(false);
            if (selected && deletedIds.includes(selected.case.case_id)) {
              setSelected(null);
            }
            await load();
          }}
        />
      ) : null}

      {supplementFor ? (
        <SupplementModal
          item={supplementFor}
          onClose={() => setSupplementFor(null)}
          onDone={async (detail) => {
            setSupplementFor(null);
            await load();
            setSelected(detail);
            setTab(detail.case.fields?.generated ? "plan" : "timeline");
          }}
        />
      ) : null}
    </div>
  );
}

function asStringList(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.map((x) => String(x));
}

function GeneratedPlan({ detail }: { detail: CaseDetail }) {
  const f = detail.case.fields || {};
  const agents = asStringList(f.agents);
  const equipment = asStringList(f.equipment);
  const missing = asStringList(f.missing_docs);
  const files = asStringList(f.source_files);
  const hits = Array.isArray(f.policy_hits)
    ? (f.policy_hits as Array<{ source?: string; text?: string }>)
    : [];
  const findings = Array.isArray(f.compliance)
    ? (f.compliance as Array<{ topic?: string; city?: string; summary?: string }>)
    : [];
  const web = Array.isArray(f.web_hits)
    ? (f.web_hits as Array<{ title?: string; snippet?: string; query?: string }>)
    : [];
  return (
    <div className="gen-plan">
      <p className="hint">本单路径由智能体根据申报材料生成，不是提交人自选的写死模板。</p>
      {agents.length ? <p>参与智能体：{agents.join("、")}</p> : <p className="hint">本单为库存案例，未走申报生成。</p>}
      <ul>
        <li>类型：{detail.case.category}</li>
        <li>金额：¥{detail.case.amount}</li>
        <li>部门：{detail.case.dept}</li>
        {typeof f.city === "string" && f.city ? <li>城市：{String(f.city)}</li> : null}
        {equipment.length ? <li>设备：{equipment.join("、")}</li> : null}
        {files.length ? <li>申报文件：{files.join("、")}</li> : null}
      </ul>
      {typeof f.plan_note === "string" && f.plan_note ? <p>{f.plan_note}</p> : null}
      {missing.length ? <p className="stall-line">缺件卡住：{missing.join("、")}</p> : null}
      {findings.map((item, i) => (
        <div key={i} className="finding">
          <strong>
            {item.topic}
            {item.city ? ` · ${item.city}` : ""}
          </strong>
          <p>{item.summary}</p>
        </div>
      ))}
      {web.length ? (
        <>
          <h3>联网查询</h3>
          <ul>
            {web.map((h, i) => (
              <li key={i}>
                <em>{h.title || h.query}</em>
                <p>{h.snippet}</p>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {hits.length ? (
        <>
          <h3>对应制度片段</h3>
          <ul>
            {hits.map((h, i) => (
              <li key={i}>
                <em>{h.source}</em>
                <p>{h.text}</p>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

function SubmitModal({
  templates,
  departments,
  onClose,
  onDone,
}: {
  templates: Template[];
  departments: Array<{ id: string; name: string }>;
  onClose: () => void;
  onDone: (d: CaseDetail) => void | Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    setBusy(true);
    setErr("");
    try {
      const detail = await api.submitPack(fd);
      await onDone(detail);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form
        className="modal modal-wide"
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => void onSubmit(e)}
      >
        <h2>提交申报（智能体生成路径）</h2>
        <p className="hint">
          上传立项申报书（PDF 或 TXT）。系统读取材料后按本单生成审批路径；标题、部门、金额可留空，由智能体抽取。
        </p>
        <label className="drop">
          申报文件（PDF / TXT，可多选）
          <input name="files" type="file" multiple accept=".pdf,.txt,application/pdf,text/plain" />
        </label>
        <label>
          申报正文（可留空，已上传文件时不必再填）
          <textarea name="body_text" rows={6} placeholder="也可粘贴正文，与上传文件一并提交" />
        </label>
        <label>
          标题（可留空，由智能体抽取）
          <input name="title" placeholder="可选" />
        </label>
        <label>
          申请人（可留空）
          <input name="applicant" placeholder="可选" />
        </label>
        <label>
          部门（可留空）
          <select name="dept" defaultValue="">
            <option value="">由智能体识别</option>
            {departments.map((d) => (
              <option key={d.id} value={d.name}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        {templates.length ? (
          <p className="hint">制度库模板只作底稿；每一单会生成自己的路径。</p>
        ) : null}
        {err ? <p className="error">{err}</p> : null}
        <div className="actions">
          <button type="button" className="ghost" onClick={onClose}>
            取消
          </button>
          <button type="submit" className="primary" disabled={busy}>
            {busy ? "智能体处理中…" : "读取材料并生成流程"}
          </button>
        </div>
      </form>
    </div>
  );
}

function DeleteProjectsModal({
  items,
  presetIds,
  onClose,
  onDone,
}: {
  items: PortfolioItem[];
  presetIds: string[];
  onClose: () => void;
  onDone: (deletedIds: string[]) => void | Promise<void>;
}) {
  const [picked, setPicked] = useState<Set<string>>(() => new Set(presetIds));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [confirming, setConfirming] = useState(false);

  const selectedItems = items.filter((row) => picked.has(row.case_id));

  function toggle(id: string) {
    setConfirming(false);
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setConfirming(false);
    if (picked.size === items.length) {
      setPicked(new Set());
    } else {
      setPicked(new Set(items.map((row) => row.case_id)));
    }
  }

  async function doDelete() {
    if (!selectedItems.length) {
      setErr("请先勾选要删除的项目");
      return;
    }
    if (!confirming) {
      setConfirming(true);
      setErr("");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      const result = await api.deleteCases(selectedItems.map((row) => row.case_id));
      await onDone(result.deleted || []);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
      setConfirming(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <h2>删除审批项目</h2>
        <p className="hint">勾选后删除，不可恢复。会同时去掉该单生成的流程底稿。</p>
        {items.length ? (
          <div className="delete-list">
            <label className="delete-row head">
              <input
                type="checkbox"
                checked={items.length > 0 && picked.size === items.length}
                onChange={toggleAll}
              />
              <span>全选（{picked.size}/{items.length}）</span>
            </label>
            {items.map((row) => (
              <label key={row.case_id} className={`delete-row${picked.has(row.case_id) ? " on" : ""}`}>
                <input
                  type="checkbox"
                  checked={picked.has(row.case_id)}
                  onChange={() => toggle(row.case_id)}
                />
                <span className="delete-title">{row.title}</span>
                <small>
                  {row.category} · {row.dept} · {statusLabel[row.status] || row.status}
                </small>
              </label>
            ))}
          </div>
        ) : (
          <p className="hint">当前没有可删除的项目。</p>
        )}
        {confirming && selectedItems.length ? (
          <p className="stall-line">
            将永久删除 {selectedItems.length} 个项目
            {selectedItems.length === 1 ? `「${selectedItems[0].title}」` : ""}，此操作不可恢复。
          </p>
        ) : null}
        {err ? <p className="error">{err}</p> : null}
        <div className="actions">
          <button type="button" className="ghost" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button
            type="button"
            className="danger-fill"
            disabled={busy || !items.length || !picked.size}
            onClick={() => void doDelete()}
          >
            {busy ? "删除中…" : confirming ? "确认删除" : "删除所选"}
          </button>
        </div>
      </div>
    </div>
  );
}

function SupplementModal({
  item,
  onClose,
  onDone,
}: {
  item: PortfolioItem;
  onClose: () => void;
  onDone: (d: CaseDetail) => void | Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    if (![...fd.getAll("files")].some((x) => x instanceof File && x.size > 0)) {
      setErr("请选择要补充的文件");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      const detail = await api.supplement(item.case_id, fd);
      await onDone(detail);
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form
        className="modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => void onSubmit(e)}
      >
        <h2>材料补充</h2>
        <p className="hint">
          为「{item.title}」补充附件。按清单所列缺件上传对应许可或报备材料后，系统会重新审查；文件名含缺件关键词即可解除卡住。
        </p>
        {item.stall_reason ? <p className="stall-line">{item.stall_reason}</p> : null}
        <label className="drop">
          补充文件（PDF / TXT，可多选）
          <input name="files" type="file" multiple accept=".pdf,.txt,application/pdf,text/plain" />
        </label>
        {err ? <p className="error">{err}</p> : null}
        <div className="actions">
          <button type="button" className="ghost" onClick={onClose}>
            取消
          </button>
          <button type="submit" className="primary" disabled={busy}>
            {busy ? "审查中…" : "提交补充材料"}
          </button>
        </div>
      </form>
    </div>
  );
}

function formatSize(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function UploadPolicyModal({
  onClose,
  onDone,
}: {
  onClose: () => void;
  onDone: () => void | Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<UploadPolicyResult | null>(null);
  const [policies, setPolicies] = useState<PolicyFile[]>([]);

  useEffect(() => {
    void api.policies().then(setPolicies).catch(() => undefined);
  }, []);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!file) {
      setErr("请先选择一份 PDF");
      return;
    }
    setBusy(true);
    setErr("");
    setResult(null);
    try {
      const uploaded = await api.uploadPolicy(file);
      setResult(uploaded);
      setPolicies(await api.policies());
      await onDone();
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : String(ex));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form
        className="modal modal-wide"
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => void onSubmit(e)}
      >
        <h2>上传规章制度 PDF</h2>
        <p className="hint">
          上传或改一处制度即可验证：例如写入「研发部建议并行工作数为1」，学习完成后刷新日历，该部门并行上限会变。提交申报时智能体会按材料生成路径，不再套写死模板。
        </p>
        <label className="drop">
          <input
            type="file"
            accept="application/pdf,.pdf"
            onChange={(e) => {
              setFile(e.target.files?.[0] || null);
              setResult(null);
              setErr("");
            }}
          />
          {file ? (
            <span>
              已选择：{file.name}（{formatSize(file.size)}）
            </span>
          ) : (
            <span>点击选择 PDF，或把文件拖到此处</span>
          )}
        </label>
        {err ? <p className="error">{err}</p> : null}
        {result ? (
          <div className="upload-ok">
            <p>
              已入库《{result.filename}》，切块 {result.chunks} 段。
            </p>
            {result.learning ? (
              <>
                <p>{result.learning.notes}</p>
                <p>参与智能体：{result.learning.agents.join("、")}</p>
                <ul>
                  {result.learning.functions.map((f) => (
                    <li key={f.name}>
                      {f.action === "created" ? "新建" : f.action === "updated" ? "更新" : "沿用"}{" "}
                      {f.name}（{f.category}）
                    </li>
                  ))}
                </ul>
              </>
            ) : result.template ? (
              <p>
                已抽取模板「{result.template.name}」（{result.template.category}
                ），共 {result.template.nodes?.length ?? 0} 个节点。可关闭后点击「模拟提交」使用。
              </p>
            ) : (
              <p>文件已保存，但未能抽出流程模板。</p>
            )}
          </div>
        ) : null}
        {policies.length ? (
          <div className="policy-list">
            <h3>已有制度</h3>
            <ul>
              {policies.map((p) => (
                <li key={p.filename}>
                  {p.filename}
                  <small>{formatSize(p.size)}</small>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <div className="actions">
          <button type="button" className="ghost" onClick={onClose}>
            {result ? "完成" : "取消"}
          </button>
          <button type="submit" className="primary" disabled={busy || !file}>
            {busy ? "解析中…" : "上传并学习"}
          </button>
        </div>
      </form>
    </div>
  );
}
