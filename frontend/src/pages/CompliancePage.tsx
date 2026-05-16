import { useState } from "react";
import { Shield, AlertTriangle, Check, Loader2 } from "lucide-react";
import { API_BASE } from "../lib/utils";

export default function CompliancePage() {
  const [title, setTitle] = useState("");
  const [bullets, setBullets] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [features, setFeatures] = useState("");
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<any>(null);

  const startReview = async () => {
    if (!title.trim()) return;
    setLoading(true);
    setReport(null);
    try {
      const res = await fetch(`${API_BASE}/compliance/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title.trim(),
          bullet_points: bullets.split("\n").filter(Boolean),
          description, category,
          product_features: features.split(",").map(f => f.trim()).filter(Boolean),
        }),
      });
      const data = await res.json();
      poll(data.task_id);
    } catch { setLoading(false); }
  };

  const poll = async (tid: string) => {
    for (let i = 0; i < 20; i++) {
      await new Promise(r => setTimeout(r, 2000));
      const res = await fetch(`${API_BASE}/compliance/${tid}/status`);
      const s = await res.json();
      if (s.status === "awaiting_review" || s.status === "completed") {
        const rr = await fetch(`${API_BASE}/compliance/${tid}/result`);
        setReport(await rr.json());
        setLoading(false);
        return;
      }
    }
    setLoading(false);
  };

  const verdictColor: Record<string, string> = {
    pass: "bg-green-100 text-green-800 border-green-300",
    warning: "bg-yellow-100 text-yellow-800 border-yellow-300",
    violation: "bg-red-100 text-red-800 border-red-300",
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">合规审查</h1>

      <div className="bg-white rounded-lg border p-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <label className="text-sm font-medium text-gray-600">Listing 标题 *</label>
            <input value={title} onChange={e => setTitle(e.target.value)}
              placeholder="Product title..." className="w-full border rounded px-3 py-2 mt-1 text-sm"/>
          </div>
          <div className="col-span-2">
            <label className="text-sm font-medium text-gray-600">Bullet Points (一行一个)</label>
            <textarea value={bullets} onChange={e => setBullets(e.target.value)} rows={5}
              placeholder="Feature 1&#10;Feature 2&#10;..." className="w-full border rounded px-3 py-2 mt-1 text-sm"/>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-600">类目</label>
            <input value={category} onChange={e => setCategory(e.target.value)}
              className="w-full border rounded px-3 py-2 mt-1 text-sm"/>
          </div>
          <div>
            <label className="text-sm font-medium text-gray-600">产品特性 (逗号分隔)</label>
            <input value={features} onChange={e => setFeatures(e.target.value)}
              className="w-full border rounded px-3 py-2 mt-1 text-sm"/>
          </div>
        </div>
        <button onClick={startReview} disabled={loading}
          className="mt-3 flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded hover:bg-orange-700 disabled:opacity-50 text-sm">
          {loading ? <Loader2 size={16} className="animate-spin"/> : <Shield size={16}/>}
          开始合规审查
        </button>
      </div>

      {report && (
        <div className="space-y-4">
          <div className={`rounded-lg border-2 p-4 ${verdictColor[report.verdict] || verdictColor.pass}`}>
            <div className="flex items-center gap-2">
              <Shield size={20}/>
              <span className="font-bold text-lg uppercase">{report.verdict}</span>
              <span className="text-sm">Risk: {report.risk_level} | Issues: {report.total_issues}</span>
            </div>
            <p className="text-sm mt-2">{report.summary}</p>
          </div>

          {report.critical_items?.length > 0 && (
            <div className="bg-red-50 rounded-lg border border-red-200 p-4">
              <h3 className="font-medium text-red-800 flex items-center gap-2"><AlertTriangle size={16}/>严重问题</h3>
              <ul className="mt-2 space-y-1">
                {report.critical_items.map((item: string, i: number) => (
                  <li key={i} className="text-sm text-red-700">{item}</li>
                ))}
              </ul>
            </div>
          )}

          {report.action_items?.length > 0 && (
            <div className="bg-white rounded-lg border p-4">
              <h3 className="font-medium flex items-center gap-2"><Check size={16} className="text-green-600"/>修改建议</h3>
              <ul className="mt-2 space-y-1">
                {report.action_items.map((item: string, i: number) => (
                  <li key={i} className="text-sm text-gray-700">• {item}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
