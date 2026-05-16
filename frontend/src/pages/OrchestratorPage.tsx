import { useState, useEffect } from "react";
import { Play, Zap, List, RefreshCw, Loader2 } from "lucide-react";
import { API_BASE } from "../lib/utils";
import { taskStore } from "../lib/TaskStore";

export default function OrchestratorPage() {
  const [logs, setLogs] = useState<any[]>([]);
  const [running, setRunning] = useState(false);
  const [lastResult, setLastResult] = useState<any>(null);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [progress, setProgress] = useState("");

  useEffect(() => {
    fetchLogs();
  }, []);

  const fetchLogs = async () => {
    try {
      const res = await fetch(`${API_BASE}/orchestrator/logs`);
      if (res.ok) setLogs(await res.json());
    } catch {}
  };

  const runOrchestrator = async (action: string = "auto") => {
    setRunning(true);
    setLastResult(null);
    setProgress("starting...");

    try {
      const res = await fetch(`${API_BASE}/orchestrator/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, context: {} }),
      });
      const data = await res.json();
      const tid = data.task_id;
      setActiveTaskId(tid);

      // 用 TaskStore 后台轮询
      taskStore.add({ id: tid, type: "social" as any, status: "running" });

      // 直接轮询 status
      const poll = setInterval(async () => {
        try {
          const sres = await fetch(`${API_BASE}/orchestrator/${tid}/status`);
          const s = await sres.json();
          setProgress(`${s.progress || s.status} (${s.completed_steps || 0} steps)`);

          if (s.status === "completed") {
            clearInterval(poll);
            const rres = await fetch(`${API_BASE}/orchestrator/${tid}/result`);
            if (rres.ok) {
              const r = await rres.json();
              setLastResult(r);
            }
            setRunning(false);
            setProgress("");
            fetchLogs();
          } else if (s.status === "failed") {
            clearInterval(poll);
            setRunning(false);
            setProgress("failed: " + (s.error || ""));
          }
        } catch {
          // 重试
        }
      }, 3000);
    } catch {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">调度中心</h1>

      <div className="flex gap-3 flex-wrap">
        <button onClick={() => runOrchestrator("auto")} disabled={running}
          className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50 text-sm">
          {running ? <Loader2 size={16} className="animate-spin"/> : <Zap size={16}/>}
          自动调度 (Auto)
        </button>
        <button onClick={() => runOrchestrator("select_product")} disabled={running}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded hover:bg-emerald-700 disabled:opacity-50 text-sm">选品分析</button>
        <button onClick={() => runOrchestrator("run_listing")} disabled={running}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-sm">Listing</button>
        <button onClick={() => runOrchestrator("check_compliance")} disabled={running}
          className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded hover:bg-orange-700 disabled:opacity-50 text-sm">合规审查</button>
        <button onClick={() => runOrchestrator("generate_social")} disabled={running}
          className="flex items-center gap-2 px-4 py-2 bg-pink-600 text-white rounded hover:bg-pink-700 disabled:opacity-50 text-sm">社媒内容</button>
        <button onClick={() => runOrchestrator("monitor_reviews")} disabled={running}
          className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 text-sm">评论监控</button>
        <button onClick={fetchLogs} className="ml-auto flex items-center gap-1 px-3 py-1 text-xs text-gray-500 hover:text-gray-700 border rounded">
          <RefreshCw size={12}/>刷新
        </button>
      </div>

      {running && (
        <div className="bg-purple-50 border border-purple-200 rounded p-3 text-sm text-purple-700 flex items-center gap-2">
          <Loader2 size={16} className="animate-spin"/>
          全流程运行中 — {progress} — 页面可切换，任务不中断
        </div>
      )}

      {lastResult && (
        <div className="bg-white rounded-lg border p-4">
          <h3 className="font-medium text-sm mb-2">调度结果: {lastResult.summary}</h3>
          {(lastResult.decisions || []).map((d: any, i: number) => (
            <div key={i} className="mb-3 border rounded-lg overflow-hidden">
              <div className="flex items-center gap-2 p-3 bg-gray-50 text-xs">
                <span className={`px-1.5 py-0.5 rounded font-medium ${d.status==='done' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                  {d.status || '?'}
                </span>
                <span className="font-medium">{d.action}</span>
                <span className="text-gray-500">— {d.reason}</span>
              </div>
              {d.result && <div className="p-3 text-xs text-gray-700 border-t">{d.result}</div>}
              {d.data && Object.keys(d.data).length > 0 && (
                <div className="p-3 border-t bg-gray-50/50 text-xs">
                  {d.action==='select_product' && d.data.scored_products && (
                    <div>
                      <div className="font-medium mb-1">{d.data.top_pick} ({d.data.product_count} products)</div>
                      {d.data.scored_products.slice(0,5).map((p:any,j:number)=>(
                        <div key={j} className="flex justify-between"><span>{p.product_name}</span><span className="text-gray-500">score: {p.overall_score?.toFixed(1)} | {p.verdict}</span></div>
                      ))}
                    </div>
                  )}
                  {d.action==='run_listing' && d.data.best_title && (
                    <div><div className="font-medium">Best Title:</div><div className="text-gray-600">{d.data.best_title}</div></div>
                  )}
                  {d.action==='check_compliance' && (
                    <div><span className={`font-medium ${d.data.verdict==='pass'?'text-green-700':'text-red-700'}`}>{d.data.verdict?.toUpperCase()}</span><span className="ml-2">{d.data.total_issues} issues</span>{d.data.critical_items?.slice(0,3).map((c:string,j:number)=><div key={j} className="text-red-600">- {c}</div>)}</div>
                  )}
                  {d.action==='generate_social' && d.data.posts && (
                    <div>{d.data.posts.map((p:any,j:number)=><div key={j}>[{p.platform}] score {p.quality_score} — {p.copy?.slice(0,80)}...</div>)}</div>
                  )}
                  {d.action==='monitor_reviews' && (
                    <div><span>{d.data.total_scraped} reviews, </span><span className="text-red-600">{d.data.alert_count} alerts</span>{d.data.alerts?.map((a:any,j:number)=><div key={j} className="text-red-600">- [{a.alert_level}] {a.content?.slice(0,60)}</div>)}</div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {logs.length > 0 && (
        <div className="bg-white rounded-lg border">
          <div className="p-3 border-b flex items-center gap-2"><List size={14}/><span className="text-sm font-medium">历史日志</span></div>
          <div className="divide-y max-h-96 overflow-auto">
            {logs.map((log: any) => (
              <div key={log.id} className="p-3 text-xs">
                <span className="text-gray-400 mr-2">#{log.id}</span>
                <span className="font-medium">{log.action}</span>
                <span className="text-gray-500 ml-2">— {log.summary}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
