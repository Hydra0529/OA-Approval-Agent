export type PortfolioItem = {
  case_id: string;
  title: string;
  category: string;
  level: string;
  dept: string;
  applicant: string;
  current_role: string;
  current_node_name: string;
  next_summary: string;
  planned_start: string;
  planned_end: string;
  actual_start: string;
  actual_end: string | null;
  duration_days: number;
  status: string;
  template_id: string;
  stall_code?: string;
  stall_reason?: string;
  delay_days?: number;
  load_level?: string;
};

export type TimelineStep = {
  date: string;
  node_id: string;
  node_name: string;
  role: string;
  status: "done" | "current" | "planned";
  summary: string;
};

export type CaseDetail = {
  case: {
    case_id: string;
    title: string;
    template_id: string;
    category: string;
    amount: number;
    dept: string;
    applicant: string;
    status: string;
    stall_code?: string;
    stall_note?: string;
    fields: Record<string, unknown>;
  };
  timeline: TimelineStep[];
  next_summary: string;
  bpmn_xml: string;
  report: string;
  citations: Array<{ source: string; text: string }>;
  stall_reason?: string;
  delay_days?: number;
  department_load?: {
    name: string;
    load: number;
    parallel_limit: number;
    level: string;
    delay_days: number;
  };
};

export type Template = {
  id: string;
  name: string;
  category: string;
  nodes?: Array<{ id: string; name: string; role: string; sla_days: number }>;
};

export type PolicyFile = {
  filename: string;
  size: number;
};

export type LearnedFunction = {
  name: string;
  category: string;
  action: "created" | "updated" | "unchanged";
  summary: string;
  version: string;
};

export type UploadPolicyResult = {
  filename: string;
  size: number;
  chunks: number;
  template: Template | null;
  learning?: {
    agents: string[];
    functions: LearnedFunction[];
    notes: string;
  };
};

export type DeptLoad = {
  id: string;
  name: string;
  parallel_limit: number;
  load: number;
  level: "idle" | "busy" | "saturated";
  delay_days: number;
  cases: Array<{ case_id: string; title: string }>;
};

export type CalendarPayload = {
  today: string;
  month: string;
  days: Record<string, string>;
  selected: {
    date: string;
    overall: string;
    departments: DeptLoad[];
  };
  legend: Record<string, string>;
};

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(_errorMessage(res.status, text));
  }
  return res.json() as Promise<T>;
}

function _errorMessage(status: number, text: string): string {
  const trimmed = (text || "").trim();
  if (trimmed.startsWith("{")) {
    try {
      const body = JSON.parse(trimmed) as { detail?: unknown; message?: string };
      if (typeof body.detail === "string") return body.detail;
      if (typeof body.message === "string") return body.message;
    } catch {
      /* fall through */
    }
  }
  if (trimmed.includes("Internal Server Error")) {
    return `服务暂时失败（${status}），请点刷新重试`;
  }
  return trimmed.slice(0, 200) || `请求失败（${status}）`;
}

export const api = {
  portfolio: () =>
    request<{ items: PortfolioItem[]; total: number }>("/api/portfolio"),
  caseDetail: (id: string) => request<CaseDetail>(`/api/cases/${id}`),
  templates: () => request<Template[]>("/api/templates"),
  submit: (body: {
    title: string;
    template_id: string;
    amount: number;
    dept: string;
    applicant: string;
    fields?: Record<string, unknown>;
  }) =>
    request<CaseDetail>("/api/cases/submit", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  submitPack: async (fd: FormData) => {
    const res = await fetch("/api/cases/submit-pack", {
      method: "POST",
      body: fd,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(_errorMessage(res.status, text));
    }
    return res.json() as Promise<CaseDetail>;
  },
  supplement: async (caseId: string, fd: FormData) => {
    const res = await fetch(`/api/cases/${encodeURIComponent(caseId)}/supplement`, {
      method: "POST",
      body: fd,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(_errorMessage(res.status, text));
    }
    return res.json() as Promise<CaseDetail>;
  },
  deleteCases: (caseIds: string[]) =>
    request<{ deleted: string[]; missing?: string[] }>("/api/cases/delete", {
      method: "POST",
      body: JSON.stringify({ case_ids: caseIds }),
    }),
  eval: () =>
    request<{ total: number; correct: number; accuracy: number }>("/api/eval/run"),
  health: () =>
    request<{ ok: boolean; llm_enabled: boolean; templates: number; cases: number }>(
      "/api/health"
    ),
  policies: () => request<PolicyFile[]>("/api/policies"),
  uploadPolicy: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("/api/policies/upload?extract=true&approve=true", {
      method: "POST",
      body: fd,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || res.statusText);
    }
    return res.json() as Promise<UploadPolicyResult>;
  },
  calendar: (month: string, dateStr: string) =>
    request<CalendarPayload>(
      `/api/calendar?month=${encodeURIComponent(month)}&date_str=${encodeURIComponent(dateStr)}`
    ),
  departments: () =>
    request<{ departments: Array<{ id: string; name: string; parallel_limit: number }> }>(
      "/api/departments"
    ),
};
