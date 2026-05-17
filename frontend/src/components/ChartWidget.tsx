import { useState, useEffect } from "react";
import { BarChart3, Loader2 } from "lucide-react";
import { API_BASE } from "../lib/utils";

interface Props {
  type: "pie" | "bar" | "line" | "radar" | "wordcloud";
  title: string;
  data: Record<string, number | number[]>;
  className?: string;
  /** 雷达图时需要 */
  axes?: string[];
}

export default function ChartWidget({ type, title, data, axes, className }: Props) {
  const [imgUrl, setImgUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");

    fetch(`${API_BASE}/charts/${type}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, data, ...(axes ? { axes } : {}) }),
    })
      .then(async (res) => {
        const json = await res.json();
        if (!cancelled) {
          if (json.success && json.image_url) {
            setImgUrl(json.image_url);
          } else {
            setError("图表生成失败");
          }
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("网络错误");
          setLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [type, title, JSON.stringify(data)]);

  if (loading) {
    return (
      <div className={`flex items-center justify-center h-48 bg-white rounded-lg border ${className}`}>
        <Loader2 size={20} className="animate-spin text-gray-400" />
      </div>
    );
  }

  if (error || !imgUrl) {
    return (
      <div className={`flex items-center justify-center h-48 bg-white rounded-lg border text-gray-400 text-sm ${className}`}>
        <BarChart3 size={16} className="mr-2" />{error || "暂无图表"}
      </div>
    );
  }

  return (
    <div className={`bg-white rounded-lg border overflow-hidden ${className}`}>
      <img src={imgUrl} alt={title} className="w-full h-auto" />
    </div>
  );
}
