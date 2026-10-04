import { useEffect, useMemo, useState } from "react";
import { api, CalendarPayload, DeptLoad } from "./api";

const WEEK = ["日", "一", "二", "三", "四", "五", "六"];
const LEVEL: Record<string, string> = {
  idle: "空闲",
  busy: "忙碌",
  saturated: "饱和",
  future: "未到",
};

function monthStr(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function iso(d: Date) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export default function CalendarPanel({
  onOpenCase,
  refreshKey = 0,
}: {
  onOpenCase: (id: string) => void;
  refreshKey?: number;
}) {
  const today = useMemo(() => new Date(), []);
  const [cursor, setCursor] = useState(() => new Date(today.getFullYear(), today.getMonth(), 1));
  const [picked, setPicked] = useState(iso(today));
  const [data, setData] = useState<CalendarPayload | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    const m = monthStr(cursor);
    void api
      .calendar(m, picked)
      .then((payload) => {
        setErr("");
        setData(payload);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [cursor, picked, refreshKey]);

  const cells = useMemo(() => {
    const y = cursor.getFullYear();
    const m = cursor.getMonth();
    const first = new Date(y, m, 1);
    const pad = first.getDay();
    const last = new Date(y, m + 1, 0).getDate();
    const out: Array<{ label: number | ""; iso?: string }> = [];
    for (let i = 0; i < pad; i++) out.push({ label: "" });
    for (let d = 1; d <= last; d++) {
      out.push({ label: d, iso: `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}` });
    }
    return out;
  }, [cursor]);

  const todayIso = iso(today);

  function clickDay(dayIso: string) {
    if (dayIso > todayIso) return;
    setPicked(dayIso);
  }

  const depts: DeptLoad[] = data?.selected.departments || [];

  return (
    <section className="panel calendar-panel">
      <div className="panel-head">
        <h2>部门忙闲日历</h2>
        <span>点击今日及以前日期，查看各部门是否空闲 / 忙碌 / 饱和</span>
      </div>
      <div className="cal-body">
        <div>
          <div className="cal-nav">
            <button
              type="button"
              className="ghost"
              onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}
            >
              上月
            </button>
            <strong>
              {cursor.getFullYear()} 年 {cursor.getMonth() + 1} 月
            </strong>
            <button
              type="button"
              className="ghost"
              onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}
            >
              下月
            </button>
          </div>
          <div className="cal-grid">
            {WEEK.map((w) => (
              <div key={w} className="cal-week">
                {w}
              </div>
            ))}
            {cells.map((c, i) => {
              if (!c.iso) return <div key={i} className="cal-cell empty" />;
              const level = data?.days[c.iso] || "idle";
              const future = c.iso > todayIso;
              return (
                <button
                  key={c.iso}
                  type="button"
                  disabled={future}
                  className={`cal-cell ${level} ${picked === c.iso ? "picked" : ""}`}
                  onClick={() => clickDay(c.iso!)}
                >
                  {c.label}
                </button>
              );
            })}
          </div>
          <p className="legend">
            <i className="idle" /> 空闲
            <i className="busy" /> 忙碌
            <i className="saturated" /> 饱和
          </p>
        </div>
        <div className="dept-loads">
          <h3>
            {picked} 各部门负荷
            {data ? `（整体 ${LEVEL[data.selected.overall] || data.selected.overall}）` : ""}
          </h3>
          {err ? <p className="error">{err}</p> : null}
          <ul>
            {depts.map((d) => (
              <li key={d.id} className={d.level}>
                <div>
                  <strong>{d.name}</strong>
                  <span>
                    {LEVEL[d.level]} · {d.load}/{d.parallel_limit} 单并行
                    {d.delay_days ? ` · 延迟 ${d.delay_days} 日` : ""}
                  </span>
                </div>
                {d.cases.length ? (
                  <p>
                    {d.cases.map((c) => (
                      <button
                        key={c.case_id}
                        type="button"
                        className="linkish"
                        onClick={() => onOpenCase(c.case_id)}
                      >
                        {c.title}
                      </button>
                    ))}
                  </p>
                ) : (
                  <p className="muted">当日无占用</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
