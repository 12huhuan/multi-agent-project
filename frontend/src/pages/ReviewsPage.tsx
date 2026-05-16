import { useState, useEffect } from "react";
import { Search, Star, AlertTriangle, MessageSquare, Check, X, Loader2, RefreshCw } from "lucide-react";
import { API_BASE } from "../lib/utils";
import { taskStore } from "../lib/TaskStore";

interface Review {
  id: string;
  product_asin: string;
  reviewer_name: string;
  rating: number;
  title: string;
  content: string;
  translated_title: string;
  translated_content: string;
  sentiment: string;
  sentiment_score: number;
  alert_level: string;
  reply_suggestion: string;
  reply_status: string;
  date: string;
  verified_purchase: boolean;
}

interface ReplySuggestion {
  review_id: string;
  subject: string;
  reply_text: string;
  alternative_reply: string;
  tone: string;
  key_points_addressed: string[];
}

const SENTIMENT_COLORS: Record<string, string> = {
  positive: "bg-green-100 text-green-800 border-green-200",
  neutral: "bg-gray-100 text-gray-600 border-gray-200",
  negative: "bg-red-100 text-red-800 border-red-200",
};

const ALERT_COLORS: Record<string, string> = {
  none: "",
  info: "border-l-4 border-blue-400",
  warning: "border-l-4 border-yellow-400 bg-yellow-50",
  alert: "border-l-4 border-orange-400 bg-orange-50",
  critical: "border-l-4 border-red-500 bg-red-50",
};

export default function ReviewsPage() {
  const [asin, setAsin] = useState("");
  const [maxReviews, setMaxReviews] = useState(15);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const [sentimentFilter, setSentimentFilter] = useState("");
  const [selectedReview, setSelectedReview] = useState<Review | null>(null);
  const [replyText, setReplyText] = useState("");
  const [replyLoading, setReplyLoading] = useState(false);
  const [showTranslation, setShowTranslation] = useState<Record<string, boolean>>({});
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);

  // 页面挂载时自动加载已有评论
  useEffect(() => {
    fetchReviews();
  }, []);

  // 恢复进行中的任务 + 监听 taskStore
  useEffect(() => {
    const allTasks = taskStore.getAll();
    const runningTask = allTasks.find(
      (t) => t.type === "review" && (t.status === "running" || t.status === "awaiting_review")
    );
    if (runningTask) {
      setActiveTaskId(runningTask.id);
      setLoading(true);
      setProgress(runningTask.current_step || runningTask.progress || "");
    }

    const unsub = taskStore.subscribe(() => {
      if (!activeTaskId) {
        // 重新检查
        const current = taskStore.getAll().find(
          (t) => t.type === "review" && (t.status === "running" || t.status === "awaiting_review")
        );
        if (current) {
          setActiveTaskId(current.id);
          setLoading(true);
          setProgress(current.current_step || current.progress || "");
        }
        return;
      }

      const task = taskStore.get(activeTaskId);
      if (!task) return;

      setProgress(task.current_step || task.progress || "");

      if (task.status === "awaiting_review" || task.status === "completed") {
        setLoading(false);
        setProgress("");
        // 从 result 加载 reviews
        if (task.result?.reviews) {
          const mapped: Review[] = task.result.reviews.map((r: any, i: number) => ({
            id: r.id || `rev-${i}`,
            product_asin: r.product_asin || asin,
            reviewer_name: r.reviewer_name || "Anonymous",
            rating: r.rating || 0,
            title: r.title || "",
            content: r.content || "",
            translated_title: r.translated_title || "",
            translated_content: r.translated_content || "",
            sentiment: r.sentiment || "neutral",
            sentiment_score: r.sentiment_score || 5.0,
            alert_level: r.alert_level || "none",
            reply_suggestion: r.reply_suggestion || "",
            reply_status: r.reply_status || "none",
            date: r.date || "",
            verified_purchase: r.verified_purchase || false,
          }));
          setReviews(mapped);
        }
      } else if (task.status === "failed") {
        setLoading(false);
        setProgress("");
        setError(task.error || "抓取失败");
      }
    });

    return unsub;
  }, [activeTaskId]);

  // 筛选变更时重新拉取
  useEffect(() => {
    if (!loading) fetchReviews();
  }, [sentimentFilter]);

  const fetchReviews = async () => {
    try {
      const params = sentimentFilter ? `?sentiment=${sentimentFilter}` : "";
      const res = await fetch(`${API_BASE}/reviews/${params}`);
      if (res.ok) setReviews(await res.json());
    } catch {}
  };

  const startScrape = async () => {
    if (!asin.trim()) return;
    setLoading(true);
    setError("");
    setReviews([]);

    try {
      const res = await fetch(`${API_BASE}/reviews/scrape`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product_asin: asin.trim(), max_reviews: maxReviews }),
      });
      const data = await res.json();
      const taskId = data.task_id;
      setActiveTaskId(taskId);

      // 加入全局 TaskStore，跨页面持久化
      taskStore.add({
        id: taskId,
        type: "review",
        status: "running",
        product_asin: asin.trim(),
      });
    } catch (err: any) {
      setError(err.message || "抓取失败");
      setLoading(false);
    }
  };

  const suggestReply = async (reviewId: string) => {
    setReplyLoading(true);
    try {
      const res = await fetch(`${API_BASE}/reviews/${reviewId}/suggest-reply`, { method: "POST" });
      if (res.ok) {
        const data: ReplySuggestion = await res.json();
        setReplyText(data.reply_text);
        fetchReviews();
      }
    } catch {}
    setReplyLoading(false);
  };

  const approveReply = async (reviewId: string, approved: boolean) => {
    try {
      await fetch(`${API_BASE}/reviews/${reviewId}/approve-reply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved, edited_reply: replyText || undefined }),
      });
      setSelectedReview(null);
      setReplyText("");
      fetchReviews();
    } catch {}
  };

  const toggleTranslation = (reviewId: string) => {
    setShowTranslation((prev) => ({ ...prev, [reviewId]: !prev[reviewId] }));
  };

  const renderStars = (rating: number) =>
    Array.from({ length: 5 }, (_, i) => (
      <Star key={i} size={14} className={i < rating ? "fill-yellow-400 text-yellow-400" : "text-gray-300"} />
    ));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">评论监控</h1>

      {/* Input Panel */}
      <div className="bg-white rounded-lg border p-4">
        <div className="flex gap-3 items-end">
          <div className="flex-1">
            <label className="text-sm font-medium text-gray-600">Amazon ASIN 或 URL</label>
            <input
              value={asin}
              onChange={(e) => setAsin(e.target.value)}
              placeholder="B0EXAMPLE"
              className="w-full border rounded px-3 py-2 mt-1 text-sm"
            />
          </div>
          <div className="w-24">
            <label className="text-sm font-medium text-gray-600">数量</label>
            <input
              type="number"
              value={maxReviews}
              onChange={(e) => setMaxReviews(Number(e.target.value))}
              min={5} max={100}
              className="w-full border rounded px-3 py-2 mt-1 text-sm"
            />
          </div>
          <button
            onClick={startScrape}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-sm"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
            抓取评论
          </button>
        </div>
        {progress && (
          <div className="mt-3 flex items-center gap-2 text-sm text-blue-600">
            <Loader2 size={14} className="animate-spin" />
            {progress}
          </div>
        )}
        {error && <div className="mt-2 text-sm text-red-600">{error}</div>}
      </div>

      {/* Filters */}
      <div className="flex gap-2">
        {["", "positive", "neutral", "negative"].map((s) => (
          <button
            key={s}
            onClick={() => setSentimentFilter(s)}
            className={`px-3 py-1 rounded-full text-xs border ${
              sentimentFilter === s
                ? "bg-blue-600 text-white border-blue-600"
                : "bg-white text-gray-600 hover:bg-gray-50"
            }`}
          >
            {s || "全部"}
          </button>
        ))}
        <button onClick={fetchReviews} className="ml-auto flex items-center gap-1 px-3 py-1 text-xs text-gray-500 hover:text-gray-700">
          <RefreshCw size={12} /> 刷新
        </button>
      </div>

      {/* Review Cards */}
      <div className="grid gap-4">
        {reviews.length === 0 && !loading && (
          <div className="text-center text-gray-400 py-12">输入 ASIN 开始抓取评论</div>
        )}
        {reviews.map((review) => (
          <div
            key={review.id}
            className={`bg-white rounded-lg border p-4 ${ALERT_COLORS[review.alert_level] || ""}`}
          >
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center gap-2">
                <div className="flex">{renderStars(review.rating)}</div>
                <span className={`text-xs px-2 py-0.5 rounded border ${SENTIMENT_COLORS[review.sentiment] || ""}`}>
                  {review.sentiment}
                </span>
                {review.alert_level !== "none" && (
                  <span className="flex items-center gap-1 text-xs text-red-600">
                    <AlertTriangle size={12} />
                    {review.alert_level}
                  </span>
                )}
                {review.verified_purchase && (
                  <span className="text-xs text-green-600">Verified</span>
                )}
              </div>
              <div className="text-xs text-gray-400">{review.reviewer_name} · {review.date}</div>
            </div>

            <h3 className="font-medium text-sm mb-1">{review.title}</h3>
            <p className="text-sm text-gray-600 mb-2">{review.content}</p>

            {review.translated_content && (
              <div className="mb-2">
                <button
                  onClick={() => toggleTranslation(review.id)}
                  className="text-xs text-blue-600 hover:underline"
                >
                  {showTranslation[review.id] ? "隐藏译文" : "查看中文译文"}
                </button>
                {showTranslation[review.id] && (
                  <div className="mt-1 p-2 bg-gray-50 rounded text-sm text-gray-600 border">
                    {review.translated_title && <p className="font-medium mb-1">{review.translated_title}</p>}
                    <p>{review.translated_content}</p>
                  </div>
                )}
              </div>
            )}

            <div className="flex items-center gap-2 mt-2 pt-2 border-t">
              {review.reply_status === "none" && (
                <button
                  onClick={() => { setSelectedReview(review); suggestReply(review.id); }}
                  disabled={replyLoading}
                  className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800"
                >
                  <MessageSquare size={12} />
                  生成回复
                </button>
              )}
              {review.reply_status === "pending" && review.reply_suggestion && (
                <div className="w-full">
                  <p className="text-xs text-gray-500 mb-1">建议回复:</p>
                  <p className="text-sm p-2 bg-blue-50 rounded border text-gray-700">{review.reply_suggestion}</p>
                  <div className="flex gap-2 mt-1">
                    <button
                      onClick={() => approveReply(review.id, true)}
                      className="flex items-center gap-1 text-xs text-green-600 hover:text-green-800"
                    >
                      <Check size={12} /> 通过
                    </button>
                    <button
                      onClick={() => approveReply(review.id, false)}
                      className="flex items-center gap-1 text-xs text-red-600 hover:text-red-800"
                    >
                      <X size={12} /> 驳回
                    </button>
                  </div>
                </div>
              )}
              {review.reply_status === "approved" && (
                <span className="text-xs text-green-600 flex items-center gap-1">
                  <Check size={12} /> 已通过
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Reply Edit Panel */}
      {selectedReview && replyText && (
        <div className="fixed bottom-4 right-4 w-96 bg-white rounded-lg shadow-xl border p-4 z-10">
          <h3 className="font-medium text-sm mb-2">
            编辑回复 - {selectedReview.reviewer_name}
          </h3>
          <textarea
            value={replyText}
            onChange={(e) => setReplyText(e.target.value)}
            rows={4}
            className="w-full border rounded px-3 py-2 text-sm mb-2"
          />
          <div className="flex gap-2 justify-end">
            <button
              onClick={() => { setSelectedReview(null); setReplyText(""); }}
              className="px-3 py-1 text-xs border rounded hover:bg-gray-50"
            >
              取消
            </button>
            <button
              onClick={() => approveReply(selectedReview.id, true)}
              className="flex items-center gap-1 px-3 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700"
            >
              <Check size={12} /> 确认
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
