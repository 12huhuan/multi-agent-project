import { useState, useEffect } from "react";
import { Search, TrendingUp, Target, DollarSign, Star, Loader2 } from "lucide-react";
import { API_BASE } from "../lib/utils";
import { taskStore } from "../lib/TaskStore";

export default function SelectionPage() {
  const [category, setCategory] = useState("");
  const [keywords, setKeywords] = useState("");
  const [budget, setBudget] = useState("$5000-$15000");
  const [strengths, setStrengths] = useState("");
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState("");
  const [report, setReport] = useState<any>(null);

  useEffect(() => {
    loadRunningTask();
  }, []);

  const loadRunningTask = () => {
    const running = taskStore.getAll().find(
      (t) => t.type === "listing" && (t.status === "running" || t.status === "awaiting_review")
    );
    if (running) {
      setLoading(true);
      setProgress(running.current_step || "");
      taskStore.subscribe(() => {
        const t = taskStore.get(running.id);
        if (t) {
          setProgress(t.current_step || "");
          if (t.status === "awaiting_review" || t.status === "completed") {
            setLoading(false);
            setReport(t.result);
          }
        }
      });
    }
  };

  const startAnalysis = async () => {
    if (!category.trim()) return;
    setLoading(true);
    setReport(null);
    try {
      const res = await fetch(`${API_BASE}/selection/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category: category.trim(),
          keywords: keywords.split(",").map(k => k.trim()).filter(Boolean),
          seller_budget: budget,
          seller_strengths: strengths.split(",").map(s => s.trim()).filter(Boolean),
        }),
      });
      const data = await res.json();
      const tid = data.task_id;
      taskStore.add({ id: tid, type: "review", status: "running" });
      poll(tid);
    } catch (e) {
      setLoading(false);
    }
  };

  const poll = async (tid: string) => {
    for (let i = 0; i < 30; i++) {
      await new Promise(r => setTimeout(r, 2000));
      const res = await fetch(`${API_BASE}/selection/${tid}/status`);
      const s = await res.json();
      setProgress(s.current_step || "");
      if (s.status === "awaiting_review" || s.status === "completed") {
        const rr = await fetch(`${API_BASE}/selection/${tid}/result`);
        setReport(await rr.json());
        setLoading(false);
        return;
      }
      if (s.status === "failed") { setLoading(false); return; }
    }
    setLoading(false);
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">智能选品</h1>

      <div className="bg-white rounded-lg border p-4">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-sm font-medium text-gray-600">品类 *</label>
            <input value={category} onChange={e => setCategory(e.target.value)}
              placeholder="Kitchen Gadgets" className="w-full border rounded px-3 py-2 mt-1 text-sm"/>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-600">关键词 (逗号分隔)</label>
            <input value={keywords} onChange={e => setKeywords(e.target.value)}
              placeholder="silicone, organizer, smart" className="w-full border rounded px-3 py-2 mt-1 text-sm"/>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-600">预算</label>
            <input value={budget} onChange={e => setBudget(e.target.value)}
              className="w-full border rounded px-3 py-2 mt-1 text-sm"/>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-600">优势 (逗号分隔)</label>
            <input value={strengths} onChange={e => setStrengths(e.target.value)}
              placeholder="sourcing, design, logistics" className="w-full border rounded px-3 py-2 mt-1 text-sm"/>
          </div>
        </div>
        <button onClick={startAnalysis} disabled={loading}
          className="mt-3 flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded hover:bg-emerald-700 disabled:opacity-50 text-sm">
          {loading ? <Loader2 size={16} className="animate-spin"/> : <TrendingUp size={16}/>}
          开始选品分析
        </button>
        {progress && <div className="mt-2 flex items-center gap-2 text-sm text-emerald-600"><Loader2 size={14} className="animate-spin"/>{progress}</div>}
      </div>

      {report && (
        <div className="space-y-4">
          <div className="bg-white rounded-lg border p-4">
            <h2 className="font-medium text-lg">Top Pick: {report.top_pick}</h2>
            <p className="text-sm text-gray-600 mt-1">{report.category_overview}</p>
          </div>
          <div className="grid gap-3">
            {(report.scored_products || []).map((p: any, i: number) => (
              <div key={i} className="bg-white rounded-lg border p-4 flex items-center gap-4">
                <div className="flex-1">
                  <h3 className="font-medium">{p.product_name}</h3>
                  <div className="flex gap-2 mt-1">
                    <span className={`text-xs px-2 py-0.5 rounded ${p.verdict === 'strong_buy' ? 'bg-green-100 text-green-700' : p.verdict === 'buy' ? 'bg-blue-100 text-blue-700' : p.verdict === 'consider' ? 'bg-yellow-100 text-yellow-700' : 'bg-gray-100 text-gray-600'}`}>{p.verdict || 'consider'}</span>
                    <span className="text-xs text-gray-500">Score: {p.overall_score?.toFixed(1)}</span>
                  </div>
                </div>
                <div className="flex gap-3 text-xs text-gray-500">
                  <span title="Competition"><Target size={14}/> {p.competition_score?.toFixed(1)}</span>
                  <span title="Margin"><DollarSign size={14}/> {p.margin_score?.toFixed(1)}</span>
                  <span title="Trend"><TrendingUp size={14}/> {p.trend_score?.toFixed(1)}</span>
                  <span title="Risk"><Star size={14}/> {p.risk_score?.toFixed(1)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
