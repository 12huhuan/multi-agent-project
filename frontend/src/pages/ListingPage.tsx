import { useState, useEffect } from "react";
import { API_BASE } from "../lib/utils";
import { taskStore } from "../lib/TaskStore";
import { Check, X, Edit3, Eye, RotateCcw } from "lucide-react";

export default function ListingPage() {
  const [productName, setProductName] = useState("");
  const [category, setCategory] = useState("");
  const [features, setFeatures] = useState("");
  const [brandStory, setBrandStory] = useState("");
  const [platform, setPlatform] = useState("amazon_us");
  const [language, setLanguage] = useState("en");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [tasks, setTasks] = useState(taskStore.getAll());
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  useEffect(() => {
    return taskStore.subscribe(() => {
      setTasks(taskStore.getAll());
    });
  }, []);

  useEffect(() => {
    taskStore.getAll().forEach((t) => {
      if (t.status === "running") taskStore.refresh(t.id);
    });
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const res = await fetch(`${API_BASE}/listing/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          product_name: productName,
          category,
          features: features.split("\n").filter(Boolean),
          brand_story: brandStory || null,
          target_platform: platform,
          target_language: language,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "请求失败");
      }

      const task = await res.json();
      taskStore.add({
        id: task.id,
        type: "listing",
        status: task.status,
        product_name: task.product_name,
        progress: "0/6",
      });
      setSelectedTaskId(task.id);
      setLoading(false);
    } catch (err: any) {
      setError(err.message);
      setLoading(false);
    }
  };

  const selectedTask = selectedTaskId ? taskStore.get(selectedTaskId) : null;
  const runningCount = tasks.filter((t) => t.type === "listing" && t.status === "running").length;

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 mb-2">Listing 优化</h1>
      {runningCount > 0 && (
        <p className="text-sm text-blue-600 mb-4">
          后台 {runningCount} 个任务进行中，切换页面不会中断
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 输入表单 */}
        <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
          <h2 className="font-semibold text-slate-800 mb-4">产品信息</h2>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">产品名称</label>
            <input type="text" value={productName} onChange={(e) => setProductName(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="例如: Wireless Bluetooth Headphones" required />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">品类</label>
            <input type="text" value={category} onChange={(e) => setCategory(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="例如: Electronics > Headphones" required />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">目标平台</label>
              <select value={platform} onChange={(e) => setPlatform(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm">
                <option value="amazon_us">Amazon US</option>
                <option value="amazon_jp">Amazon JP</option>
                <option value="amazon_uk">Amazon UK</option>
                <option value="amazon_de">Amazon DE</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">语言</label>
              <select value={language} onChange={(e) => setLanguage(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm">
                <option value="en">English</option>
                <option value="ja">日本語</option>
                <option value="de">Deutsch</option>
                <option value="zh">中文</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">产品特性 (每行一个)</label>
            <textarea value={features} onChange={(e) => setFeatures(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm h-24 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="Noise Cancellation Technology&#10;40-Hour Battery Life&#10;Premium Comfort Design" />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">品牌故事 (可选)</label>
            <textarea value={brandStory} onChange={(e) => setBrandStory(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm h-20 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="品牌理念与故事..." />
          </div>

          {error && <div className="text-red-500 text-sm bg-red-50 p-2 rounded">{error}</div>}

          <button type="submit" disabled={loading}
            className="w-full bg-blue-600 text-white py-2 rounded-lg font-medium hover:bg-blue-700 transition-colors disabled:opacity-50">
            {loading ? "提交中..." : "开始 Listing 优化"}
          </button>
        </form>

        {/* 结果 + 历史 */}
        <div className="space-y-4">
          {/* 进行中的任务 */}
          {tasks.filter((t) => t.type === "listing" && t.status === "running").map((t) => (
            <div key={t.id} className="bg-blue-50 rounded-xl border border-blue-200 p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-blue-800">{t.product_name?.slice(0, 40)}...</span>
                <span className="text-xs text-blue-500">{t.progress}</span>
              </div>
              <div className="w-full bg-blue-200 rounded-full h-2">
                <div className="bg-blue-600 h-2 rounded-full animate-pulse" style={{ width: `${(parseInt(t.progress || "0") / 6) * 100}%` }} />
              </div>
            </div>
          ))}

          {/* 已完成的任务列表 */}
          {tasks.filter((t) => t.type === "listing" && t.status !== "running").length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <h3 className="font-semibold text-slate-700 mb-3">历史任务</h3>
              <div className="space-y-2 max-h-[200px] overflow-auto">
                {tasks.filter((t) => t.type === "listing" && t.status !== "running").map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setSelectedTaskId(t.id)}
                    className={`w-full text-left p-2 rounded-lg text-sm transition-colors ${
                      selectedTaskId === t.id ? "bg-blue-50 border border-blue-200" : "hover:bg-slate-50 border border-transparent"
                    }`}
                  >
                    <div className="flex justify-between">
                      <span className="text-slate-700 truncate max-w-[300px]">{t.product_name}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        t.status === "completed" ? "bg-green-100 text-green-700" :
                        t.status === "awaiting_review" ? "bg-yellow-100 text-yellow-700" :
                        t.status === "rejected" ? "bg-red-100 text-red-700" :
                        "bg-red-100 text-red-700"
                      }`}>
                        {t.status === "completed" ? "已完成" : t.status === "awaiting_review" ? "待审核" : t.status === "rejected" ? "已驳回" : "失败"}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 详情 */}
          {selectedTask?.result && selectedTask?.status === "awaiting_review" ? (
            <ReviewPanel
              taskId={selectedTask.id}
              result={selectedTask.result}
              onUpdated={() => {
                const updated = taskStore.get(selectedTask.id);
                if (updated) setTasks(taskStore.getAll());
              }}
            />
          ) : selectedTask?.result ? (
            <ResultCard result={selectedTask.result} status={selectedTask.status} />
          ) : selectedTask?.status === "running" ? (
            <div className="bg-white rounded-xl border border-slate-200 p-6 text-center text-slate-400">
              <div className="animate-spin w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full mx-auto mb-2" />
              6 个 Agent 依次执行中...（可切换到其他页面，任务不会中断）
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** 审核面板 — 待审核任务，支持编辑+审批 */
function ReviewPanel({ taskId, result, onUpdated }: { taskId: string; result: any; onUpdated: () => void }) {
  const [approving, setApproving] = useState(false);
  const [reviewError, setReviewError] = useState("");
  const [editMode, setEditMode] = useState(false);

  // 可编辑字段
  const [editTitle, setEditTitle] = useState(result.best_title || result.title_candidates?.[0]?.title || "");
  const [editBullets, setEditBullets] = useState<string[]>(result.bullet_points || []);
  const [editDesc, setEditDesc] = useState(result.description_html || "");

  const handleApprove = async (approved: boolean) => {
    setApproving(true);
    setReviewError("");

    const modifications: Record<string, any> = {};
    if (approved && editMode) {
      if (editTitle !== (result.best_title || result.title_candidates?.[0]?.title || "")) {
        modifications.best_title = editTitle;
      }
      if (JSON.stringify(editBullets) !== JSON.stringify(result.bullet_points || [])) {
        modifications.bullet_points = editBullets.map((text) => ({ text }));
      }
      if (editDesc !== (result.description_html || "")) {
        modifications.description_html = editDesc;
      }
    }

    try {
      const res = await fetch(`${API_BASE}/listing/${taskId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approved,
          modifications: Object.keys(modifications).length > 0 ? modifications : null,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "审核失败");
      }

      const data = await res.json();
      // 更新本地 store
      const task = taskStore.get(taskId);
      if (task) {
        taskStore.add({ ...task, status: data.status });
      }
      onUpdated();
    } catch (err: any) {
      setReviewError(err.message);
    }
    setApproving(false);
  };

  const seoScore = result.seo_score?.overall_score ?? result.seo_score?.overallScore ?? 0;

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 space-y-4 max-h-[700px] overflow-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-slate-700">审核结果</h3>
          <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-700">待审核</span>
        </div>
        <div className="flex items-center gap-2">
          {seoScore > 0 && (
            <span className={`text-sm font-bold ${seoScore >= 80 ? "text-green-600" : seoScore >= 60 ? "text-yellow-600" : "text-red-600"}`}>
              SEO {seoScore}/100
            </span>
          )}
          <button
            onClick={() => setEditMode(!editMode)}
            className={`flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
              editMode ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {editMode ? <Eye size={12} /> : <Edit3 size={12} />}
            {editMode ? "预览" : "编辑"}
          </button>
        </div>
      </div>

      {reviewError && (
        <div className="text-red-500 text-sm bg-red-50 p-2 rounded">{reviewError}</div>
      )}

      {/* Keywords */}
      {result.keywords?.length > 0 && (
        <section>
          <h4 className="text-sm font-semibold text-slate-600 mb-2">关键词 ({result.keywords.length})</h4>
          <div className="flex flex-wrap gap-1">
            {result.keywords.slice(0, 20).map((kw: any, i: number) => (
              <span key={i} className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-xs">
                {kw.keyword || kw}
                {kw.search_volume && <span className="ml-1 text-blue-400">({kw.search_volume})</span>}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Title Candidates */}
      {result.title_candidates?.length > 0 && (
        <section>
          <h4 className="text-sm font-semibold text-slate-600 mb-2">
            标题候选
            {result.best_title && <span className="text-xs text-slate-400 ml-2">（已选最优）</span>}
          </h4>
          {editMode ? (
            <input
              type="text"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              className="w-full px-3 py-2 border border-amber-300 bg-amber-50 rounded-lg text-sm focus:ring-2 focus:ring-amber-500"
            />
          ) : (
            <div className="space-y-2">
              {result.title_candidates.map((t: any, i: number) => (
                <div key={i} className={`p-2 rounded text-xs ${t.title === result.best_title ? "bg-green-50 border border-green-200" : "bg-slate-50"}`}>
                  <div className="flex justify-between mb-1">
                    <span className="font-medium">候选 {i + 1}</span>
                    <span className="text-blue-600">评分: {t.score}</span>
                  </div>
                  <p className="text-slate-700">{t.title}</p>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Bullet Points */}
      {result.bullet_points?.length > 0 && (
        <section>
          <h4 className="text-sm font-semibold text-slate-600 mb-2">五点描述</h4>
          {editMode ? (
            <div className="space-y-2">
              {editBullets.map((bp, i) => (
                <div key={i} className="flex gap-2">
                  <span className="text-xs text-slate-400 mt-2">{i + 1}.</span>
                  <input
                    type="text"
                    value={bp}
                    onChange={(e) => {
                      const next = [...editBullets];
                      next[i] = e.target.value;
                      setEditBullets(next);
                    }}
                    className="flex-1 px-2 py-1 border border-amber-300 bg-amber-50 rounded text-xs focus:ring-2 focus:ring-amber-500"
                  />
                </div>
              ))}
            </div>
          ) : (
            <ul className="list-disc pl-4 text-xs text-slate-700 space-y-1">
              {result.bullet_points.map((bp: string, i: number) => (
                <li key={i}>{bp}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      {/* Description HTML */}
      {result.description_html && (
        <section>
          <h4 className="text-sm font-semibold text-slate-600 mb-2">产品长描述</h4>
          {editMode ? (
            <textarea
              value={editDesc}
              onChange={(e) => setEditDesc(e.target.value)}
              className="w-full px-3 py-2 border border-amber-300 bg-amber-50 rounded-lg text-xs font-mono h-32 focus:ring-2 focus:ring-amber-500"
            />
          ) : (
            <div
              className="border border-slate-200 rounded-lg p-3 text-xs text-slate-700 max-h-[200px] overflow-auto prose prose-sm prose-slate"
              dangerouslySetInnerHTML={{ __html: result.description_html }}
            />
          )}
        </section>
      )}

      {/* A+ Content */}
      {result.a_plus_content?.modules?.length > 0 && (
        <section>
          <h4 className="text-sm font-semibold text-slate-600 mb-2">A+ 内容模块 ({result.a_plus_content.modules.length})</h4>
          <div className="space-y-2">
            {result.a_plus_content.modules.map((mod: any, i: number) => (
              <div key={i} className="border border-slate-200 rounded-lg p-3 bg-slate-50">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs px-1.5 py-0.5 rounded bg-slate-200 text-slate-600">{mod.type || `模块 ${i + 1}`}</span>
                  {mod.title && <span className="text-xs font-medium text-slate-700">{mod.title}</span>}
                </div>
                {mod.content && <p className="text-xs text-slate-600">{mod.content}</p>}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* SEO Score Breakdown */}
      {result.seo_score && Object.keys(result.seo_score).length > 0 && (
        <section>
          <h4 className="text-sm font-semibold text-slate-600 mb-2">SEO 评分详情</h4>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(result.seo_score).filter(([k]) => k !== "overall_score" && k !== "overallScore").map(([key, value]) => (
              <div key={key} className="bg-slate-50 rounded p-2">
                <span className="text-xs text-slate-500 capitalize">{key.replace(/_/g, " ")}</span>
                <span className="text-xs font-medium text-slate-700 ml-2">
                  {typeof value === "number" ? `${value}/100` : String(value)}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Action Buttons */}
      <div className="flex gap-3 pt-2 border-t border-slate-100">
        <button
          onClick={() => handleApprove(true)}
          disabled={approving}
          className="flex-1 flex items-center justify-center gap-2 bg-green-600 text-white py-2 rounded-lg font-medium hover:bg-green-700 disabled:opacity-50 transition-colors"
        >
          <Check size={16} />
          {approving ? "处理中..." : editMode ? "保存修改并审批" : "审批通过"}
        </button>
        <button
          onClick={() => handleApprove(false)}
          disabled={approving}
          className="flex items-center justify-center gap-2 px-6 py-2 bg-white text-red-600 border border-red-200 rounded-lg font-medium hover:bg-red-50 disabled:opacity-50 transition-colors"
        >
          <X size={16} />
          驳回
        </button>
      </div>
    </div>
  );
}

/** 结果展示组件 — 已完成/已驳回任务只读 */
function ResultCard({ result, status }: { result: any; status?: string }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-4 max-h-[600px] overflow-auto">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-slate-700">优化结果</h3>
        {status && (
          <span className={`text-xs px-2 py-0.5 rounded-full ${
            status === "completed" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
          }`}>
            {status === "completed" ? "已通过" : "已驳回"}
          </span>
        )}
      </div>

      {result.keywords?.length > 0 && (
        <section>
          <h4 className="text-sm font-semibold text-slate-600 mb-2">关键词 ({result.keywords.length})</h4>
          <div className="flex flex-wrap gap-1">
            {result.keywords.slice(0, 15).map((kw: any, i: number) => (
              <span key={i} className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-xs">
                {kw.keyword || kw}
              </span>
            ))}
          </div>
        </section>
      )}

      {result.title_candidates?.length > 0 && (
        <section>
          <h4 className="text-sm font-semibold text-slate-600 mb-2">标题候选</h4>
          {result.title_candidates.map((t: any, i: number) => (
            <div key={i} className={`mb-2 p-2 rounded text-xs ${t.title === result.best_title ? "bg-green-50 border border-green-200" : "bg-slate-50"}`}>
              <div className="flex justify-between mb-1">
                <span className="font-medium">候选 {i + 1}</span>
                <span className="text-blue-600">评分: {t.score}</span>
              </div>
              <p className="text-slate-700">{t.title}</p>
            </div>
          ))}
        </section>
      )}

      {result.bullet_points?.length > 0 && (
        <section>
          <h4 className="text-sm font-semibold text-slate-600 mb-2">五点描述</h4>
          <ul className="list-disc pl-4 text-xs text-slate-700 space-y-1">
            {result.bullet_points.map((bp: string, i: number) => (
              <li key={i}>{bp}</li>
            ))}
          </ul>
        </section>
      )}

      {result.description_html && (
        <section>
          <h4 className="text-sm font-semibold text-slate-600 mb-2">产品长描述</h4>
          <div
            className="border border-slate-200 rounded-lg p-3 text-xs text-slate-700 max-h-[200px] overflow-auto prose prose-sm prose-slate"
            dangerouslySetInnerHTML={{ __html: result.description_html }}
          />
        </section>
      )}

      {result.a_plus_content?.modules?.length > 0 && (
        <section>
          <h4 className="text-sm font-semibold text-slate-600 mb-2">A+ 内容模块</h4>
          <div className="space-y-2">
            {result.a_plus_content.modules.map((mod: any, i: number) => (
              <div key={i} className="border border-slate-200 rounded-lg p-3 bg-slate-50">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs px-1.5 py-0.5 rounded bg-slate-200 text-slate-600">{mod.type || `模块 ${i + 1}`}</span>
                  {mod.title && <span className="text-xs font-medium text-slate-700">{mod.title}</span>}
                </div>
                {mod.content && <p className="text-xs text-slate-600">{mod.content}</p>}
              </div>
            ))}
          </div>
        </section>
      )}

      {result.seo_score?.overall_score > 0 && (
        <section>
          <h4 className="text-sm font-semibold text-slate-600 mb-2">SEO 评分</h4>
          <div className="text-2xl font-bold text-blue-600">
            {result.seo_score.overall_score}<span className="text-sm text-slate-400">/100</span>
          </div>
        </section>
      )}
    </div>
  );
}
