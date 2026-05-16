import { useState, useRef } from "react";
import { Send, Image, Globe, Check, X, Loader2, Star, Languages, RefreshCw, AlertTriangle } from "lucide-react";
import { API_BASE } from "../lib/utils";

interface Post {
  id: string;
  product_name: string;
  platform: string;
  language: string;
  copy: string;
  short_copy: string;
  hashtags: string[];
  call_to_action: string;
  image_urls: string[];
  quality_score: number;
  quality_verdict: string;
  status: string;
  created_at: string;
}

const PLATFORM_LABELS: Record<string, string> = {
  instagram: "Instagram",
  threads: "Threads",
  pinterest: "Pinterest",
  facebook: "Facebook",
  tiktok: "TikTok",
};

const PLATFORM_COLORS: Record<string, string> = {
  instagram: "border-pink-200 hover:border-pink-400",
  threads: "border-gray-300 hover:border-gray-500",
  pinterest: "border-red-200 hover:border-red-400",
  facebook: "border-blue-200 hover:border-blue-400",
  tiktok: "border-slate-300 hover:border-slate-500",
};

export default function SocialMediaPage() {
  const [productName, setProductName] = useState("");
  const [category, setCategory] = useState("");
  const [features, setFeatures] = useState("");
  const [brandStory, setBrandStory] = useState("");
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>(["instagram", "threads", "pinterest"]);
  const [language, setLanguage] = useState("en");
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const [platformTab, setPlatformTab] = useState("all");
  const wsRef = useRef<WebSocket | null>(null);

  const togglePlatform = (p: string) => {
    setSelectedPlatforms((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]
    );
  };

  const fetchPosts = async () => {
    try {
      const res = await fetch(`${API_BASE}/social/posts`);
      if (res.ok) setPosts(await res.json());
    } catch {}
  };

  const startGenerate = async () => {
    if (!productName.trim()) return;
    setLoading(true);
    setError("");
    setPosts([]);

    try {
      const res = await fetch(`${API_BASE}/social/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          product_name: productName.trim(),
          category,
          features: features.split(",").map((f) => f.trim()).filter(Boolean),
          brand_story: brandStory,
          platforms: selectedPlatforms,
          language,
        }),
      });
      const data = await res.json();
      setTaskId(data.task_id);

      const ws = new WebSocket(`ws://localhost:8000/api/v1/social/${data.task_id}/stream`);
      wsRef.current = ws;
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "progress") {
          setProgress(`${msg.current_step} | 帖子: ${msg.posts_count || 0}`);
        } else if (msg.type === "done") {
          setLoading(false);
          setProgress("");
          fetchPosts();
        }
      };
      ws.onerror = () => { setLoading(false); setError("WebSocket 连接失败"); };
    } catch (err: any) {
      setError(err.message || "生成失败");
      setLoading(false);
    }
  };

  const translatePost = async (postId: string, targetLang: string) => {
    try {
      await fetch(`${API_BASE}/social/posts/${postId}/translate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_language: targetLang }),
      });
      fetchPosts();
    } catch {}
  };

  const approvePost = async (postId: string) => {
    try {
      await fetch(`${API_BASE}/social/posts/${postId}/approve?approved=true`, { method: "POST" });
      fetchPosts();
    } catch {}
  };

  const filteredPosts = platformTab === "all" ? posts : posts.filter((p) => p.platform === platformTab);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">社媒内容</h1>

      {/* Input Panel */}
      <div className="bg-white rounded-lg border p-4">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-sm font-medium text-gray-600">产品名称 *</label>
            <input
              value={productName}
              onChange={(e) => setProductName(e.target.value)}
              placeholder="Wireless Bluetooth Headphones"
              className="w-full border rounded px-3 py-2 mt-1 text-sm"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-600">类目</label>
            <input
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="Electronics"
              className="w-full border rounded px-3 py-2 mt-1 text-sm"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-600">产品特性 (逗号分隔)</label>
            <input
              value={features}
              onChange={(e) => setFeatures(e.target.value)}
              placeholder="Bluetooth 5.3, Noise Cancelling, 30hr battery"
              className="w-full border rounded px-3 py-2 mt-1 text-sm"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-gray-600">品牌故事</label>
            <input
              value={brandStory}
              onChange={(e) => setBrandStory(e.target.value)}
              placeholder="Brand story..."
              className="w-full border rounded px-3 py-2 mt-1 text-sm"
            />
          </div>
        </div>

        {/* Platform Selection */}
        <div className="mt-3">
          <label className="text-sm font-medium text-gray-600 mb-1 block">目标平台</label>
          <div className="flex flex-wrap gap-2">
            {Object.entries(PLATFORM_LABELS).map(([key, label]) => (
              <button
                key={key}
                onClick={() => togglePlatform(key)}
                className={`px-3 py-1 rounded-full text-xs border transition-colors ${
                  selectedPlatforms.includes(key)
                    ? "bg-blue-600 text-white border-blue-600"
                    : "bg-white text-gray-600 hover:bg-gray-50"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Language & Submit */}
        <div className="flex items-end gap-3 mt-3">
          <div className="w-24">
            <label className="text-sm font-medium text-gray-600">语言</label>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="w-full border rounded px-3 py-2 mt-1 text-sm"
            >
              <option value="en">English</option>
              <option value="zh">中文</option>
              <option value="ja">日本語</option>
              <option value="ko">한국어</option>
              <option value="fr">Français</option>
              <option value="de">Deutsch</option>
              <option value="es">Español</option>
            </select>
          </div>
          <button
            onClick={startGenerate}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50 text-sm"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            生成内容
          </button>
        </div>
        {progress && (
          <div className="mt-3 flex items-center gap-2 text-sm text-purple-600">
            <Loader2 size={14} className="animate-spin" />
            {progress}
          </div>
        )}
        {error && <div className="mt-2 text-sm text-red-600">{error}</div>}
      </div>

      {/* Platform Tabs */}
      {posts.length > 0 && (
        <div className="flex gap-2 items-center">
          <button
            onClick={() => setPlatformTab("all")}
            className={`px-3 py-1 rounded-full text-xs border ${
              platformTab === "all" ? "bg-purple-600 text-white" : "bg-white text-gray-600"
            }`}
          >
            全部 ({posts.length})
          </button>
          {Object.keys(PLATFORM_LABELS).map((p) => {
            const count = posts.filter((x) => x.platform === p).length;
            if (count === 0) return null;
            return (
              <button
                key={p}
                onClick={() => setPlatformTab(p)}
                className={`px-3 py-1 rounded-full text-xs border ${
                  platformTab === p ? "bg-purple-600 text-white" : "bg-white text-gray-600"
                }`}
              >
                {PLATFORM_LABELS[p]} ({count})
              </button>
            );
          })}
          <button onClick={fetchPosts} className="ml-auto flex items-center gap-1 px-3 py-1 text-xs text-gray-500 hover:text-gray-700">
            <RefreshCw size={12} /> 刷新
          </button>
        </div>
      )}

      {/* Post Cards */}
      <div className="grid gap-6">
        {posts.length === 0 && !loading && (
          <div className="text-center text-gray-400 py-12">输入产品信息，选择平台，开始生成社媒内容</div>
        )}
        {filteredPosts.map((post) => (
          <div
            key={post.id}
            className={`bg-white rounded-lg border-2 p-5 transition-colors ${PLATFORM_COLORS[post.platform] || ""}`}
          >
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="font-medium text-sm">{PLATFORM_LABELS[post.platform] || post.platform}</span>
                <span className="text-xs bg-gray-100 px-2 py-0.5 rounded">{post.language.toUpperCase()}</span>
                {post.status === "approved" && (
                  <span className="flex items-center gap-1 text-xs text-green-600">
                    <Check size={12} /> Approved
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                <Star size={14} className={post.quality_score >= 7 ? "text-yellow-400" : "text-gray-300"} />
                <span className="text-xs text-gray-500">{post.quality_score.toFixed(1)}</span>
              </div>
            </div>

            {/* Copy */}
            <p className="text-sm text-gray-800 whitespace-pre-line mb-3">{post.copy}</p>

            {/* Short Copy */}
            {post.short_copy && (
              <p className="text-xs text-gray-500 mb-2 italic">"{post.short_copy}"</p>
            )}

            {/* Hashtags */}
            {post.hashtags.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-3">
                {post.hashtags.map((tag, i) => (
                  <span key={i} className="text-xs text-blue-600 bg-blue-50 px-2 py-0.5 rounded">
                    #{tag}
                  </span>
                ))}
              </div>
            )}

            {/* CTA */}
            {post.call_to_action && (
              <p className="text-sm font-medium text-gray-700 mb-3">{post.call_to_action}</p>
            )}

            {/* Images */}
            {post.image_urls.length > 0 && (
              <div className="flex gap-2 mb-3">
                {post.image_urls.map((url, i) => (
                  <div key={i} className="w-20 h-20 bg-gray-100 rounded border flex items-center justify-center">
                    {url.startsWith("[image-gen]") ? (
                      <Image size={20} className="text-gray-400" />
                    ) : (
                      <img src={url} alt="" className="w-full h-full object-cover rounded" />
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center gap-2 pt-3 border-t">
              {post.status !== "approved" && (
                <button
                  onClick={() => approvePost(post.id)}
                  className="flex items-center gap-1 text-xs text-green-600 hover:text-green-800"
                >
                  <Check size={12} /> 通过
                </button>
              )}
              <div className="flex items-center gap-1">
                {["zh", "ja", "fr", "de", "es"].map((lang) => (
                  <button
                    key={lang}
                    onClick={() => translatePost(post.id, lang)}
                    className="text-xs text-gray-500 hover:text-blue-600 px-1"
                  >
                    {lang.toUpperCase()}
                  </button>
                ))}
                <Globe size={12} className="text-gray-400 ml-1" />
              </div>
              {post.quality_verdict === "needs_revision" && (
                <span className="ml-auto text-xs text-orange-600 flex items-center gap-1">
                  <AlertTriangle size={12} /> 需修改
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

