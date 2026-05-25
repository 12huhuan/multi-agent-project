import { useState, useEffect, useCallback, useRef } from "react";
import { Play, Zap, List, RefreshCw, Loader2, Search, MessageCircle, ChevronDown, ChevronUp } from "lucide-react";
import { API_BASE } from "../lib/utils";
import { taskStore } from "../lib/TaskStore";
import type { TaskInfo } from "../lib/TaskStore";
import StepDetailCard from "../components/StepDetailCard";

const CHAIN_NAMES: Record<string, string> = {
  selection_listing: "选品上架链",
  marketing: "营销推广链",
  aftersales: "售后监控链",
  full_pipeline: "全链路调度",
  clarify: "需要更多信息",
};

export default function OrchestratorPage() {
  const [logs, setLogs] = useState<any[]>([]);
  const [nlInput, setNlInput] = useState("");
  const [category, setCategory] = useState("");
  const [task, setTask] = useState<TaskInfo | null>(null);
  const [routerTask, setRouterTask] = useState<any>(null);
  const [expandResult, setExpandResult] = useState(false);
  const runningTaskIdRef = useRef<string | null>(null);
  const routerPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

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
    return () => {
      unsub();
      if (routerPollRef.current) clearInterval(routerPollRef.current);
    };
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

  // ── 自然语言路由 ──────────────────────────────

  const runNlRouter = async () => {
    const message = nlInput.trim();
    if (!message) return;

    setRouterTask({
      task_id: "",
      status: "analyzing",
      progress: "LLM 分析意图中...",
    });

    try {
      const res = await fetch(`${API_BASE}/router/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const data = await res.json();
      const tid = data.task_id;

      setRouterTask({
        task_id: tid,
        chain: data.chain,
        chain_name: data.chain_name,
        reasoning: data.reasoning,
        status: "running",
      });

      // 轮询进度
      if (routerPollRef.current) clearInterval(routerPollRef.current);
      routerPollRef.current = setInterval(async () => {
        try {
          const statusRes = await fetch(`${API_BASE}/router/${tid}/status`);
          const statusData = await statusRes.json();

          if (statusData.status === "completed" || statusData.status === "failed" || statusData.status === "clarify") {
            // 获取完整结果
            const resultRes = await fetch(`${API_BASE}/router/${tid}/result`);
            const resultData = await resultRes.json();
            setRouterTask({ ...statusData, ...resultData });
            if (routerPollRef.current) clearInterval(routerPollRef.current);
          } else {
            setRouterTask((prev: any) => ({ ...prev, ...statusData }));
          }
        } catch {
          if (routerPollRef.current) clearInterval(routerPollRef.current);
        }
      }, 1500);
    } catch {
      setRouterTask((prev: any) => ({ ...prev, status: "failed", error: "请求失败" }));
    }
  };

  const running = task?.status === "running";
  const lastResult = task?.status === "completed" ? task?.result : null;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">调度中心</h1>

      {/* ── 自然语言路由入口 ─────────────────── */}
      <div className="bg-gradient-to-r from-indigo-50 via-purple-50 to-pink-50 rounded-lg border border-indigo-200 p-5">
        <div className="flex items-center gap-2 mb-3">
          <MessageCircle size={18} className="text-indigo-600" />
          <span className="font-semibold text-indigo-900">智能路由 (NL输入)</span>
          <span className="text-xs bg-indigo-100 text-indigo-600 px-2 py-0.5 rounded-full">NEW</span>
        </div>
        <p className="text-xs text-slate-500 mb-3">
          直接用自然语言描述需求，AI 自动识别意图并分发给对应链路执行。
          试试说："帮我在美国市场分析蓝牙耳机" 或 "帮我做厨房用品的全套运营"
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            value={nlInput}
            onChange={(e) => setNlInput(e.target.value)}
            placeholder="用自然语言描述你的需求..."
            className="flex-1 px-4 py-3 border border-indigo-200 rounded-lg text-sm focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 bg-white"
            onKeyDown={(e) => { if (e.key === "Enter" && routerTask?.status !== "running") runNlRouter(); }}
          />
          <button
            onClick={runNlRouter}
            disabled={routerTask?.status === "running" || !nlInput.trim()}
            className="flex items-center gap-2 px-5 py-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 text-sm font-medium whitespace-nowrap"
          >
            {routerTask?.status === "running" ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
            发送
          </button>
        </div>

        {/* 路由进度提示 */}
        {routerTask && (
          <div className={`mt-3 p-3 rounded text-sm ${
            routerTask.status === "running" || routerTask.status === "analyzing"
              ? "bg-indigo-100 text-indigo-700"
              : routerTask.status === "completed"
              ? "bg-green-100 text-green-700"
              : routerTask.status === "clarify"
              ? "bg-amber-100 text-amber-700"
              : routerTask.status === "failed"
              ? "bg-red-100 text-red-700"
              : ""
          }`}>
            {routerTask.status === "analyzing" && (
              <div className="flex items-center gap-2">
                <Loader2 size={14} className="animate-spin" />
                {routerTask.progress}
              </div>
            )}
            {routerTask.status === "running" && (
              <div className="flex items-center gap-2">
                <Loader2 size={14} className="animate-spin" />
                <span className="font-medium">{routerTask.chain_name || routerTask.chain}</span>
                <span>— {routerTask.progress || "执行中..."}</span>
              </div>
            )}
            {routerTask.status === "clarify" && (
              <div>
                <span className="font-medium">需要更多信息：</span>
                {routerTask.reasoning || routerTask.summary}
              </div>
            )}
            {routerTask.status === "failed" && (
              <div>执行失败: {routerTask.error}</div>
            )}
            {routerTask.status === "completed" && (
              <div>
                <div className="flex items-center justify-between">
                  <span>
                    路由: <span className="font-medium">{routerTask.chain_name}</span>
                    {" — "}{routerTask.reasoning}{" "}
                    {routerTask.confidence && (
                      <span className="text-xs">(置信度: {(routerTask.confidence * 100).toFixed(0)}%)</span>
                    )}
                  </span>
                  <button
                    onClick={() => setExpandResult(!expandResult)}
                    className="text-xs text-green-600 hover:underline flex items-center gap-1"
                  >
                    {expandResult ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    {expandResult ? "收起" : "展开详情"}
                  </button>
                </div>
                <p className="text-xs mt-1 opacity-70">{routerTask.summary}</p>

                {expandResult && routerTask.chain_result && (
                  <div className="mt-3 space-y-2">
                    {routerTask.chain === "full_pipeline" ? (
                      // 全链路: 按 chain 分组显示
                      (routerTask.chain_result || []).map((chainGroup: any, ci: number) => (
                        <div key={ci} className="border border-green-200 rounded p-2 bg-white/50">
                          <div className="text-xs font-medium mb-2">
                            {chainGroup.chain_name}
                            <span className={`ml-2 px-1 py-0.5 rounded text-xs ${
                              chainGroup.status === "done" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                            }`}>{chainGroup.status}</span>
                          </div>
                          {(chainGroup.steps || []).map((step: any, si: number) => (
                            <StepDetailCard key={si} step={step} index={si} />
                          ))}
                        </div>
                      ))
                    ) : (
                      // 单链路: 直接显示 steps
                      routerTask.chain_result.map((step: any, i: number) => (
                        <StepDetailCard key={i} step={step} index={i} />
                      ))
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── 快捷链路按钮 ──────────────────── */}
      <div className="bg-white rounded-lg border p-4">
        <h3 className="text-sm font-medium text-slate-700 mb-3">快捷链路</h3>
        <div className="flex gap-3 flex-wrap">
          <button
            onClick={() => {
              setNlInput("帮我在美国市场分析一下");
              setRouterTask(null);
            }}
            className="px-4 py-2 bg-emerald-50 text-emerald-700 rounded-lg hover:bg-emerald-100 text-sm border border-emerald-200 transition-colors"
          >
            选品上架 (Selection → Listing → Compliance)
          </button>
          <button
            onClick={() => {
              setNlInput("帮我生成社媒营销内容");
              setRouterTask(null);
            }}
            className="px-4 py-2 bg-blue-50 text-blue-700 rounded-lg hover:bg-blue-100 text-sm border border-blue-200 transition-colors"
          >
            营销推广 (Social → Ads)
          </button>
          <button
            onClick={() => {
              setNlInput("帮我监控产品评论和差评");
              setRouterTask(null);
            }}
            className="px-4 py-2 bg-orange-50 text-orange-700 rounded-lg hover:bg-orange-100 text-sm border border-orange-200 transition-colors"
          >
            售后监控 (Review → Alert → Reply)
          </button>
          <button
            onClick={() => {
              setNlInput("帮我做全流程运营，从选品到售后");
              setRouterTask(null);
            }}
            className="px-4 py-2 bg-purple-50 text-purple-700 rounded-lg hover:bg-purple-100 text-sm border border-purple-200 transition-colors"
          >
            全链路调度 (Full Pipeline)
          </button>
        </div>
      </div>

      {/* 分隔线 */}
      <div className="flex items-center gap-3">
        <div className="flex-1 border-t border-slate-200"></div>
        <span className="text-xs text-slate-400">传统手动模式</span>
        <div className="flex-1 border-t border-slate-200"></div>
      </div>

      {/* ── 原有的手动操作区 ─────────────────── */}
      <div className="bg-white rounded-lg border p-4">
        <label className="block text-sm font-medium text-slate-700 mb-2">
          目标品类 (自动运行全流程)
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
