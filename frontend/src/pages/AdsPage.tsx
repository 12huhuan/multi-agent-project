import { useState, useEffect } from "react";
import { TrendingUp, TrendingDown, DollarSign, Target, Zap, BarChart3, Loader2, AlertTriangle } from "lucide-react";
import { API_BASE } from "../lib/utils";

export default function AdsPage() {
  const [dashboard, setDashboard] = useState<any>(null);
  const [analysis, setAnalysis] = useState<any>(null);
  const [bidResult, setBidResult] = useState<any>(null);
  const [budgetResult, setBudgetResult] = useState<any>(null);
  const [fullResult, setFullResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<"dashboard" | "analysis" | "bids" | "budget">("dashboard");

  useEffect(() => { fetchDashboard(); }, []);

  const fetchDashboard = async () => {
    const res = await fetch(`${API_BASE}/ads/dashboard`);
    if (res.ok) setDashboard(await res.json());
  };

  const runAnalysis = async () => {
    setLoading(true);
    const res = await fetch(`${API_BASE}/ads/analyze`, { method: "POST" });
    if (res.ok) setAnalysis(await res.json());
    setLoading(false);
  };

  const runBidOpt = async () => {
    setLoading(true);
    const res = await fetch(`${API_BASE}/ads/optimize-bids`, { method: "POST" });
    if (res.ok) setBidResult(await res.json());
    setLoading(false);
  };

  const runBudget = async () => {
    setLoading(true);
    const res = await fetch(`${API_BASE}/ads/allocate-budget`, { method: "POST" });
    if (res.ok) setBudgetResult(await res.json());
    setLoading(false);
  };

  const runFull = async () => {
    setLoading(true);
    const res = await fetch(`${API_BASE}/ads/full-optimize`, { method: "POST" });
    if (res.ok) setFullResult(await res.json());
    setLoading(false);
  };

  const healthColor = (status: string) =>
    status === "healthy" ? "text-green-600 bg-green-50" :
    status === "warning" ? "text-yellow-600 bg-yellow-50" :
    "text-red-600 bg-red-50";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">广告管理</h1>
        <button onClick={runFull} disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded hover:bg-orange-700 disabled:opacity-50 text-sm">
          {loading ? <Loader2 size={16} className="animate-spin"/> : <Zap size={16}/>}
          一键全优化
        </button>
      </div>

      {/* KPI Cards */}
      {dashboard?.overview && (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          {[
            { label: "广告花费", value: `$${dashboard.overview.total_spend}`, icon: DollarSign, color: "text-blue-600" },
            { label: "销售额", value: `$${dashboard.overview.total_sales}`, icon: TrendingUp, color: "text-green-600" },
            { label: "订单数", value: dashboard.overview.total_orders, icon: BarChart3, color: "text-purple-600" },
            { label: "ACOS", value: `${dashboard.overview.overall_acos}%`, icon: Target, color: dashboard.overview.overall_acos > 30 ? "text-red-600" : "text-green-600" },
            { label: "ROAS", value: `${dashboard.overview.overall_roas}x`, icon: Zap, color: dashboard.overview.overall_roas > 3 ? "text-green-600" : "text-yellow-600" },
          ].map((kpi, i) => (
            <div key={i} className="bg-white rounded-lg border p-4">
              <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
                <kpi.icon size={14} className={kpi.color} />{kpi.label}
              </div>
              <div className="text-xl font-bold">{kpi.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2 border-b pb-2">
        {[
          ["dashboard", "概览"], ["analysis", "效果分析"], ["bids", "竞价优化"], ["budget", "预算分配"],
        ].map(([key, label]) => (
          <button key={key} onClick={() => setTab(key as any)}
            className={`px-3 py-1.5 text-sm rounded-t ${tab === key ? "bg-white border-x border-t font-medium text-orange-600" : "text-gray-500 hover:text-gray-700"}`}>
            {label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {tab === "dashboard" && dashboard && (
        <div className="space-y-3">
          {dashboard.campaigns.map((c: any) => (
            <div key={c.id} className="bg-white rounded-lg border p-4 flex items-center gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm">{c.name}</span>
                  <span className={`text-xs px-1.5 py-0.5 rounded ${c.status === "active" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>{c.status}</span>
                </div>
                <div className="flex gap-4 mt-1 text-xs text-gray-500">
                  <span>花费: ${c.spend}</span>
                  <span>销售: ${c.sales}</span>
                  <span>订单: {c.orders}</span>
                  <span>ACOS: {c.acos}%</span>
                  <span>ROAS: {c.roas}x</span>
                  <span>CTR: {c.ctr}%</span>
                </div>
              </div>
              <div className={`text-sm font-bold px-3 py-1 rounded ${c.acos > 40 ? "bg-red-50 text-red-600" : c.acos > 25 ? "bg-yellow-50 text-yellow-600" : "bg-green-50 text-green-600"}`}>
                {c.acos > 40 ? "需优化" : c.acos > 25 ? "监控中" : "健康"}
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "analysis" && (
        <div className="space-y-3">
          <button onClick={runAnalysis} disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm">
            {loading ? <Loader2 size={14} className="animate-spin"/> : <BarChart3 size={14}/>} 运行分析
          </button>
          {analysis && (
            <div>
              <div className="grid grid-cols-4 gap-2 mb-3 text-sm">
                <span>总花费: <b>${analysis.total_spend}</b></span>
                <span>总销售: <b>${analysis.total_sales}</b></span>
                <span>ACOS: <b className={analysis.overall_acos > 30 ? "text-red-600" : "text-green-600"}>{analysis.overall_acos}%</b></span>
                <span>ROAS: <b>{analysis.overall_roas}x</b></span>
              </div>
              {analysis.campaign_insights?.map((ins: any, i: number) => (
                <div key={i} className="bg-white rounded-lg border p-3 mb-2">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium">{ins.campaign_name}</span>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${healthColor(ins.status)}`}>{ins.status}</span>
                    <span className="text-xs text-gray-500">建议: {ins.suggested_bid_adjustment}</span>
                  </div>
                  {ins.issues?.length > 0 && (
                    <div className="text-xs text-red-600 mt-1">
                      {ins.issues.map((issue: string, j: number) => (
                        <div key={j} className="flex items-center gap-1"><AlertTriangle size={10}/>{issue}</div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "bids" && (
        <div className="space-y-3">
          <button onClick={runBidOpt} disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm">
            {loading ? <Loader2 size={14} className="animate-spin"/> : <Target size={14}/>} 优化竞价
          </button>
          {bidResult && (
            <div>
              <p className="text-sm text-gray-600 mb-2">预计节约: <b className="text-green-600">${bidResult.total_estimated_savings}</b> — {bidResult.summary}</p>
              {bidResult.suggestions?.map((s: any, i: number) => (
                <div key={i} className="bg-white rounded-lg border p-3 mb-2 flex items-center gap-3">
                  <div className="flex-1">
                    <div className="text-sm font-medium">{s.keyword}</div>
                    <div className="text-xs text-gray-500">{s.reason}</div>
                  </div>
                  <div className="text-right text-xs">
                    <div>${s.current_bid} → <span className="font-bold">${s.suggested_bid}</span></div>
                    <span className={`px-1.5 py-0.5 rounded ${
                      s.action === "pause" ? "bg-red-100 text-red-700" :
                      s.action === "decrease" ? "bg-yellow-100 text-yellow-700" :
                      s.action === "increase" ? "bg-green-100 text-green-700" : "bg-gray-100"
                    }`}>{s.action}</span>
                  </div>
                </div>
              ))}
              {bidResult.keywords_to_pause?.length > 0 && (
                <div className="bg-red-50 border border-red-200 rounded p-3 text-sm">
                  <span className="font-medium text-red-700">建议暂停:</span>
                  <span className="text-red-600"> {bidResult.keywords_to_pause.join(", ")}</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {tab === "budget" && (
        <div className="space-y-3">
          <button onClick={runBudget} disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm">
            {loading ? <Loader2 size={14} className="animate-spin"/> : <DollarSign size={14}/>} 分配预算
          </button>
          {budgetResult && (
            <div>
              <p className="text-sm text-gray-600 mb-2">总预算: $500 → 已分配: <b>${budgetResult.total_allocated}</b></p>
              {budgetResult.allocations?.map((a: any, i: number) => (
                <div key={i} className="bg-white rounded-lg border p-3 mb-2 flex items-center gap-3">
                  <div className="flex-1 text-sm font-medium">{a.campaign_name}</div>
                  <div className="text-xs text-gray-500">{a.reason}</div>
                  <div className="text-right text-xs">
                    <div>${a.current_budget} → <span className="font-bold">${a.suggested_budget}</span></div>
                    <span className={a.change_percent > 0 ? "text-green-600" : a.change_percent < 0 ? "text-red-600" : "text-gray-500"}>
                      {a.change_percent > 0 ? "+" : ""}{a.change_percent}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Full Optimization Result */}
      {fullResult && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <div className="flex items-center gap-2 text-green-700 font-medium">
            <Zap size={16}/> {fullResult.summary}
          </div>
        </div>
      )}
    </div>
  );
}
