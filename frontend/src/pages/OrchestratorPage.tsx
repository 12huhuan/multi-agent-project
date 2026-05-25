import { useState, useEffect, useCallback, useRef } from "react";
import { Play, Zap, List, RefreshCw, Loader2, Search } from "lucide-react";
import { API_BASE } from "../lib/utils";
import { taskStore } from "../lib/TaskStore";
import type { TaskInfo } from "../lib/TaskStore";
import StepDetailCard from "../components/StepDetailCard";

export default function OrchestratorPage() {
  const [logs, setLogs] = useState<any[]>([]);
  const [category, setCategory] = useState("");
  const [task, setTask] = useState<TaskInfo | null>(null);
  const runningTaskIdRef = useRef<string | null>(null);

  const syncFromStore = useCallback(() => {
    const tid = runningTaskIdRef.current;
    if (!tid) return;
    const stored = taskStore.get(tid);
    if (stored) {
      setTask({ ...stored });
    }
  }, []);

  useEffect(() => {
    const orchestratorTasks = taskStore.getAll().filter(
      (t) => t.type === "orchestrator"
    );
    if (orchestratorTasks.length > 0) {
      const latest = orchestratorTasks[0];
      runningTaskIdRef.current = latest.id;
      setTask({ ...latest });
    }
    fetchLogs();

    const unsub = taskStore.subscribe(syncFromStore);
    return unsub;
  }, [syncFromStore]);

  const fetchLogs = async () => {
    try {
      const res = await fetch(`${API_BASE}/orchestrator/logs`);
      if (res.ok) setLogs(await res.json());
    } catch {}
  };

  const buildContext = () => {
    const ctx: Record<string, any> = {};
    if (category.trim()) {
      ctx.category = category.trim();
    }
    return ctx;
  };

  const runOrchestrator = async (action: string = "auto") => {
    const context = buildContext();

    try {
      const res = await fetch(`${API_BASE}/orchestrator/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, context }),
      });
      const data = await res.json();
      const tid = data.task_id;
      runningTaskIdRef.current = tid;

      taskStore.add({
        id: tid,
        type: "orchestrator",
        status: "running",
        progress: "starting...",
      });
      setTask(taskStore.get(tid) ?? null);
    } catch {
      // network error
    }
  };

  const running = task?.status === "running";
  const lastResult = task?.status === "completed" ? task?.result : null;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">调度中心</h1>

      {/* 品类输入 */}
      <div className="bg-white rounded-lg border p-4">
        <label className="block text-sm font-medium text-slate-700 mb-2">
          目标品类 (输入品类后自动运行全流程)
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="例如: Headphones, Kitchen Gadgets, Yoga Mat..."
            className="flex-1 px-3 py-2 border rounded-lg text-sm focus:outline-none focus:border-purple-400"
            onKeyDown={(e) => { if (e.key === "Enter" && !running) runOrchestrator("auto"); }}
          />
          <button
            onClick={() => runOrchestrator("auto")}
            disabled={running}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 text-sm whitespace-nowrap"
          >
            {running ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
            自动调度 (Auto)
          </button>
        </div>
        <p className="text-xs text-slate-400 mt-2">
          系统将自动完成: 选品 → Listing生成 → 合规审查 → 社媒内容 → 评论监控。
          只需提供品类，其余数据由 AI 自动生成。
        </p>
      </div>

      {/* 单步操作按钮 */}
      <div className="flex gap-3 flex-wrap">
        <button onClick={() => runOrchestrator("select_product")} disabled={running}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded hover:bg-emerald-700 disabled:opacity-50 text-sm">
          <Search size={16} /> 选品分析
        </button>
        <button onClick={() => runOrchestrator("run_listing")} disabled={running}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-sm">
          <Play size={16} /> Listing
        </button>
        <button onClick={() => runOrchestrator("check_compliance")} disabled={running}
          className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded hover:bg-orange-700 disabled:opacity-50 text-sm">
          合规审查
        </button>
        <button onClick={() => runOrchestrator("generate_social")} disabled={running}
          className="flex items-center gap-2 px-4 py-2 bg-pink-600 text-white rounded hover:bg-pink-700 disabled:opacity-50 text-sm">
          社媒内容
        </button>
        <button onClick={() => runOrchestrator("monitor_reviews")} disabled={running}
          className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 text-sm">
          评论监控
        </button>
        <button onClick={fetchLogs} className="ml-auto flex items-center gap-1 px-3 py-1 text-xs text-gray-500 hover:text-gray-700 border rounded">
          <RefreshCw size={12} /> 刷新
        </button>
      </div>

      {running && (
        <div className="bg-purple-50 border border-purple-200 rounded p-3 text-sm text-purple-700 flex items-center gap-2">
          <Loader2 size={16} className="animate-spin" />
          全流程运行中 — {task?.progress || task?.current_step || ""} — 页面可切换，任务不中断
        </div>
      )}

      {task?.status === "failed" && (
        <div className="bg-red-50 border border-red-200 rounded p-3 text-sm text-red-700">
          任务失败: {task.error || "未知错误"}
        </div>
      )}

      {lastResult && (
        <div className="bg-white rounded-lg border p-4">
          <h3 className="font-medium text-sm mb-3">调度结果: {lastResult.summary}</h3>
          {(lastResult.decisions || []).map((d: any, i: number) => (
            <StepDetailCard key={i} step={d} index={i} />
          ))}
        </div>
      )}

      {logs.length > 0 && (
        <div className="bg-white rounded-lg border">
          <div className="p-3 border-b flex items-center gap-2">
            <List size={14} />
            <span className="text-sm font-medium">历史日志 ({logs.length})</span>
          </div>
          <div className="divide-y max-h-96 overflow-auto">
            {logs.map((log: any) => (
              <div key={log.id} className="p-3 text-xs">
                <span className="text-gray-400 mr-2">#{log.id}</span>
                <span className="font-medium">{log.action}</span>
                <span className={`ml-2 px-1.5 py-0.5 rounded text-xs ${
                  log.status === "completed" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                }`}>{log.status}</span>
                <span className="text-gray-500 ml-2">— {log.summary}</span>
                {log.category && <span className="text-gray-400 ml-2">[{log.category}]</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
