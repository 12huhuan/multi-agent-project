import { useState, useEffect } from "react";
import { Heart, MessageCircle, Share2, Bookmark, Play, RefreshCw } from "lucide-react";
import { API_BASE } from "../lib/utils";

interface FeedPost {
  id: string;
  product_name: string;
  platform: string;
  copy: string;
  hashtags: string[];
  image_urls: string[];
  status: string;
  created_at: string;
}

const PLATFORM_STYLE: Record<string, { name: string; accent: string; gradient: string }> = {
  instagram: { name: "Instagram", accent: "border-pink-300", gradient: "from-pink-500 to-orange-400" },
  threads: { name: "Threads", accent: "border-gray-300", gradient: "from-gray-700 to-gray-500" },
  pinterest: { name: "Pinterest", accent: "border-red-300", gradient: "from-red-600 to-red-400" },
  facebook: { name: "Facebook", accent: "border-blue-300", gradient: "from-blue-600 to-blue-400" },
  tiktok: { name: "TikTok", accent: "border-slate-300", gradient: "from-slate-800 to-slate-600" },
};

function XiaohongshuCard({ post }: { post: FeedPost }) {
  const [liked, setLiked] = useState(false);
  const style = PLATFORM_STYLE[post.platform] || PLATFORM_STYLE.instagram;

  return (
    <div className="bg-white rounded-xl shadow-md overflow-hidden border border-gray-100 max-w-md mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 p-3">
        <div className={`w-10 h-10 rounded-full bg-gradient-to-br ${style.gradient} flex items-center justify-center text-white text-sm font-bold`}>
          {post.product_name.charAt(0)}
        </div>
        <div className="flex-1">
          <p className="text-sm font-semibold">{post.product_name}</p>
          <p className="text-xs text-gray-400">{post.created_at?.slice(0, 10)}</p>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full border ${style.accent}`}>{style.name}</span>
      </div>

      {/* Image */}
      {post.image_urls.length > 0 && !post.image_urls[0].startsWith("[image-gen]") && (
        <div className="w-full aspect-square bg-gray-100 overflow-hidden">
          <img src={post.image_urls[0]} alt="" className="w-full h-full object-cover" />
        </div>
      )}
      {post.image_urls.length > 0 && post.image_urls[0].startsWith("[image-gen]") && (
        <div className="w-full aspect-square bg-gradient-to-br from-gray-100 to-gray-200 flex flex-col items-center justify-center gap-2">
          <div className={`w-16 h-16 rounded-2xl bg-gradient-to-br ${style.gradient} opacity-60`} />
          <p className="text-xs text-gray-400">product image</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-4 px-3 py-2">
        <button onClick={() => setLiked(!liked)}>
          <Heart size={20} className={liked ? "fill-red-500 text-red-500" : "text-gray-700"} />
        </button>
        <MessageCircle size={20} className="text-gray-700" />
        <Share2 size={20} className="text-gray-700" />
        <Bookmark size={20} className="text-gray-700 ml-auto" />
      </div>

      {/* Likes */}
      <p className="px-3 text-xs font-semibold">{liked ? 128 : 127} 次赞</p>

      {/* Content */}
      <div className="px-3 pb-3">
        <p className="text-sm text-gray-800 whitespace-pre-line leading-relaxed">{post.copy}</p>
        {post.hashtags.length > 0 && (
          <p className="text-xs text-blue-500 mt-1">
            {post.hashtags.map((t, i) => (
              <span key={i}>#{t} </span>
            ))}
          </p>
        )}
      </div>
    </div>
  );
}

export default function PublishedFeedPage() {
  const [posts, setPosts] = useState<FeedPost[]>([]);
  const [filter, setFilter] = useState("all");

  const fetchPosts = async () => {
    try {
      const res = await fetch(`${API_BASE}/social/posts`);
      if (res.ok) {
        const data = await res.json();
        setPosts(data.filter((p: FeedPost) => p.status === "published" || p.status === "approved"));
      }
    } catch {}
  };

  useEffect(() => { fetchPosts(); }, []);

  const platforms = ["all", ...new Set(posts.map(p => p.platform))];
  const filtered = filter === "all" ? posts : posts.filter(p => p.platform === filter);

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">社媒动态</h1>
        <button onClick={fetchPosts} className="flex items-center gap-1 px-3 py-1 text-xs text-gray-500 hover:text-gray-700">
          <RefreshCw size={12} /> 刷新
        </button>
      </div>

      {/* Platform Tabs */}
      {platforms.length > 1 && (
        <div className="flex gap-2 pb-2">
          {platforms.map(p => (
            <button
              key={p}
              onClick={() => setFilter(p)}
              className={`px-4 py-1.5 rounded-full text-xs font-medium transition-colors ${
                filter === p ? "bg-gray-800 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {p === "all" ? "全部" : p}
            </button>
          ))}
        </div>
      )}

      {/* Feed */}
      <div className="space-y-6">
        {filtered.length === 0 && (
          <div className="text-center py-20 text-gray-400">
            <p className="text-lg mb-2">还没有发布的帖子</p>
            <p className="text-sm">去社媒内容页面生成并发布内容</p>
          </div>
        )}
        {filtered.map(post => (
          <XiaohongshuCard key={post.id} post={post} />
        ))}
      </div>
    </div>
  );
}
