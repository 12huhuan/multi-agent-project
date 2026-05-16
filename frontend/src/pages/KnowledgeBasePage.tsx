import { useState, useEffect, useCallback, useRef } from "react";
import { API_BASE } from "../lib/utils";
import { Upload, Search, Trash2, FileText, X, Globe, FileUp, Sparkles, Eye, ChevronDown, ChevronRight } from "lucide-react";

interface KBDocument {
  id: string;
  title: string;
  source_type: string;
  source_url: string | null;
  chunk_count: number;
  created_at: string;
}

interface SearchResult {
  chunk_id: string;
  content: string;
  score: number;
  source: string;
}

const typeBadge = (t: string) => {
  const map: Record<string, string> = {
    pdf: "bg-red-100 text-red-700",
    url: "bg-blue-100 text-blue-700",
    markdown: "bg-green-100 text-green-700",
    text: "bg-slate-100 text-slate-500",
  };
  return map[t] || map.text;
};

export default function KnowledgeBasePage() {
  const [docs, setDocs] = useState<KBDocument[]>([]);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<"text" | "file" | "search">("text");
  const [showVectors, setShowVectors] = useState(false);
  const [vectorData, setVectorData] = useState<{ total_vectors: number; items: any[] } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const fetchDocs = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/knowledge/documents`);
      if (res.ok) setDocs(await res.json());
    } catch {}
  }, []);

  useEffect(() => { fetchDocs(); }, [fetchDocs]);

  const handleUploadText = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !content.trim()) return;
    setUploading(true); setError("");
    try {
      const res = await fetch(`${API_BASE}/knowledge/documents`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: title.trim(), content: content.trim(), source_type: "markdown" }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "上传失败");
      setTitle(""); setContent("");
      await fetchDocs();
    } catch (err: any) { setError(err.message); }
    setUploading(false);
  };

  const handleUploadFile = async () => {
    if (!file) return;
    setUploading(true); setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API_BASE}/knowledge/documents/upload`, { method: "POST", body: form });
      if (!res.ok) throw new Error((await res.json()).detail || "上传失败");
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      await fetchDocs();
    } catch (err: any) { setError(err.message); }
    setUploading(false);
  };

  const handleImportUrl = async () => {
    if (!url.trim()) return;
    setUploading(true); setError("");
    try {
      const res = await fetch(`${API_BASE}/knowledge/documents/import-url?url=${encodeURIComponent(url.trim())}`, { method: "POST" });
      if (!res.ok) throw new Error((await res.json()).detail || "导入失败");
      setUrl("");
      await fetchDocs();
    } catch (err: any) { setError(err.message); }
    setUploading(false);
  };

  const handleSeedSample = async () => {
    setUploading(true); setError("");
    const samples = [
      { title: "退货政策", content: "## 退货政策\n\n我们提供30天无理由退货服务。收到商品后30天内，您可以申请退货退款。\n\n## 退货条件\n\n商品必须保持原包装完整，配件齐全。已使用的消耗品（如滤芯、电池）不支持退货。\n\n## 退货流程\n\n1. 登录您的账户\n2. 进入订单页面，选择需要退货的商品\n3. 填写退货原因并提交申请\n4. 等待客服审核（1-2个工作日）\n5. 审核通过后按地址寄回商品\n6. 仓库签收后3-5个工作日原路退款\n\n## 运费承担\n\n质量问题退货：我们承担往返运费\n买家原因退货：买家承担退货运费" },
      { title: "物流配送FAQ", content: "## 配送方式\n\n标准配送：5-7个工作日，免费（订单满$35）\n加急配送：2-3个工作日，$9.99\n次日达：下单后1个工作日，$19.99\n\n## 追踪包裹\n\n发货后您将收到包含追踪号码的确认邮件。您也可以登录账户在「我的订单」中查看物流状态。\n\n## 配送范围\n\n我们目前支持美国本土48州、阿拉斯加、夏威夷及波多黎各。暂不支持APO/FPO军邮地址。\n\n## 丢件处理\n\n如果包裹超过预计送达时间7天仍未收到，请联系客服，我们将为您重新发货或全额退款。" },
      { title: "产品质保政策", content: "## 质保期限\n\n所有产品自购买之日起享受12个月质保服务。配件类产品质保3个月。\n\n## 质保范围\n\n制造缺陷、材料问题导致的故障。不包括人为损坏、不当使用、自行改装。\n\n## 质保流程\n\n1. 联系客服描述问题并上传照片\n2. 客服评估后提供维修/更换/退款方案\n3. 维修周期一般为5-10个工作日\n\n## 延保服务\n\n可在购买时加购延保服务，延长至24个月，仅需额外支付产品价格的10%。" },
      { title: "联系我们", content: "## 客服渠道\n\n在线客服：官网右下角聊天窗口，工作时间 7×24\n邮件支持：support@example.com，回复时效 24 小时内\n电话热线：1-800-XXX-XXXX，工作时间周一至周五 9:00-18:00 EST\n\n## 常见咨询时效\n\n订单查询：实时\n退换货申请：1-2个工作日审核\n投诉处理：2-3个工作日\n技术咨询：1-2个工作日\n\n## 社交媒体\n\nTwitter: @ExampleSupport\nFacebook: facebook.com/Example" },
    ];
    let ok = 0;
    for (const s of samples) {
      try {
        const res = await fetch(`${API_BASE}/knowledge/documents`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...s, source_type: "markdown" }),
        });
        if (res.ok) ok++;
      } catch {}
    }
    await fetchDocs();
    setUploading(false);
    setError(ok === samples.length ? "" : `已导入 ${ok}/${samples.length} 篇文档`);
  };

  const fetchVectors = async () => {
    try {
      const res = await fetch(`${API_BASE}/knowledge/vectors?limit=50`);
      if (res.ok) setVectorData(await res.json());
    } catch {}
  };

  const handleDelete = async (id: string) => {
    try {
      await fetch(`${API_BASE}/knowledge/documents/${id}`, { method: "DELETE" });
      setDocs((prev) => prev.filter((d) => d.id !== id));
    } catch {}
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true); setActiveTab("search");
    try {
      const res = await fetch(`${API_BASE}/knowledge/search`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: searchQuery, top_k: 5 }),
      });
      if (res.ok) setSearchResults((await res.json()).results || []);
    } catch {}
    setSearching(false);
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 mb-2">知识库管理</h1>
      <p className="text-sm text-slate-500 mb-6">
        {docs.length} 篇文档 · {docs.reduce((s, d) => s + d.chunk_count, 0)} 个检索片段
      </p>

      {/* Tabs */}
      <div className="flex gap-1 bg-slate-100 rounded-lg p-1 mb-4 w-fit">
        {([
          ["text", "Markdown"],
          ["file", "文件上传"],
          ["search", "检索测试"],
        ] as const).map(([key, label]) => (
          <button key={key}
            onClick={() => setActiveTab(key)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              activeTab === key ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {error && (
        <div className="flex items-center justify-between bg-red-50 text-red-600 text-sm rounded-lg px-4 py-2 mb-4">
          {error}
          <button onClick={() => setError("")}><X size={14} /></button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Markdown 输入 */}
        {activeTab === "text" && (
          <form onSubmit={handleUploadText} className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
            <h2 className="font-semibold text-slate-800 flex items-center gap-2"><Upload size={16} /> 文本 / Markdown</h2>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">标题</label>
              <input type="text" value={title} onChange={(e) => setTitle(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                placeholder="例如：退货政策 FAQ" required />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">内容 <span className="text-slate-400 font-normal">（段落自动分块）</span></label>
              <textarea value={content} onChange={(e) => setContent(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm h-48 focus:ring-2 focus:ring-blue-500 font-mono"
                placeholder={`## 退货政策\n\n我们提供30天无理由退货...`} required />
            </div>
            <button type="submit" disabled={uploading || !title.trim() || !content.trim()}
              className="w-full bg-blue-600 text-white py-2 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">
              {uploading ? "上传中..." : "上传并索引"}
            </button>
          </form>
        )}

        {/* 文件 / URL 上传 */}
        {activeTab === "file" && (
          <div className="space-y-6">
            {/* PDF / 文件上传 */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
              <h2 className="font-semibold text-slate-800 flex items-center gap-2"><FileUp size={16} /> 上传文件</h2>
              <p className="text-xs text-slate-400">支持 PDF、Markdown (.md)、纯文本 (.txt)</p>
              <input ref={fileRef} type="file" accept=".pdf,.md,.txt"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="w-full text-sm text-slate-600 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100" />
              {file && <p className="text-xs text-slate-500">已选择: {file.name} ({(file.size / 1024).toFixed(1)} KB)</p>}
              <button onClick={handleUploadFile} disabled={uploading || !file}
                className="w-full bg-blue-600 text-white py-2 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">
                {uploading ? "解析中..." : "上传文件"}
              </button>
            </div>

            {/* URL 导入 */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
              <h2 className="font-semibold text-slate-800 flex items-center gap-2"><Globe size={16} /> 导入网页</h2>
              <input type="url" value={url} onChange={(e) => setUrl(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                placeholder="https://example.com/returns-policy" />
              <button onClick={handleImportUrl} disabled={uploading || !url.trim()}
                className="w-full bg-blue-600 text-white py-2 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">
                {uploading ? "抓取中..." : "导入网页"}
              </button>
            </div>
          </div>
        )}

        {/* 检索面板 */}
        {activeTab === "search" && (
          <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
            <h2 className="font-semibold text-slate-800 flex items-center gap-2"><Search size={16} /> 检索测试</h2>
            <div className="flex gap-2">
              <input type="text" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                className="flex-1 px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                placeholder="输入查询内容..." />
              <button onClick={handleSearch} disabled={searching || !searchQuery.trim()}
                className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">
                {searching ? "检索中" : "搜索"}
              </button>
            </div>
            {searchResults.length > 0 && (
              <div className="space-y-3 max-h-[400px] overflow-auto">
                {searchResults.map((r, i) => (
                  <div key={i} className="border border-slate-100 rounded-lg p-3 bg-slate-50">
                    <div className="flex justify-between items-start mb-2">
                      <span className="text-xs text-slate-400 truncate max-w-[70%]">{r.source || `片段 ${i + 1}`}</span>
                      <span className="text-xs font-mono text-blue-600">{(r.score * 100).toFixed(0)}%</span>
                    </div>
                    <p className="text-sm text-slate-700 leading-relaxed line-clamp-4">{r.content}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 文档列表 */}
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h2 className="font-semibold text-slate-800 mb-4 flex items-center gap-2"><FileText size={16} /> 文档列表</h2>
          {docs.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-sm text-slate-400 mb-4">暂无文档</p>
              <button onClick={handleSeedSample} disabled={uploading}
                className="inline-flex items-center gap-2 px-4 py-2 bg-amber-50 text-amber-700 rounded-lg text-sm font-medium hover:bg-amber-100 disabled:opacity-50 transition-colors border border-amber-200">
                <Sparkles size={14} />
                {uploading ? "导入中..." : "一键导入示例数据"}
              </button>
              <p className="text-xs text-slate-400 mt-2">包含退货政策、物流配送、质保政策、客服信息</p>
            </div>
          ) : (
            <div className="space-y-2 max-h-[400px] overflow-auto">
              {docs.map((doc) => (
                <div key={doc.id}
                  className="flex items-center justify-between p-3 border border-slate-100 rounded-lg hover:bg-slate-50 transition-colors">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-slate-700 truncate">{doc.title}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className={`text-xs px-1.5 py-0.5 rounded ${typeBadge(doc.source_type)}`}>
                        {doc.source_type}
                      </span>
                      <span className="text-xs text-slate-400">{doc.chunk_count} chunks</span>
                      <span className="text-xs text-slate-400">
                        {new Date(doc.created_at).toLocaleDateString("zh-CN")}
                      </span>
                    </div>
                  </div>
                  <button onClick={() => handleDelete(doc.id)}
                    className="ml-3 p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors" title="删除文档">
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* 向量数据预览 */}
          <div className="mt-4 border-t border-slate-100 pt-4">
            <button
              onClick={() => { setShowVectors(!showVectors); if (!vectorData) fetchVectors(); }}
              className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-700 transition-colors w-full text-left"
            >
              {showVectors ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              <Eye size={14} />
              向量数据预览
              {vectorData && (
                <span className="text-xs text-slate-400 ml-2">
                  ({vectorData.total_vectors} vectors · {vectorData.items.length} shown)
                </span>
              )}
            </button>

            {showVectors && vectorData && (
              <div className="mt-3 space-y-2 max-h-[300px] overflow-auto">
                {vectorData.items.map((item: any) => (
                  <div key={item.chunk_id} className="border border-slate-100 rounded p-2 bg-slate-50/50">
                    <div className="flex items-center gap-2 mb-1">
                      <code className="text-xs text-slate-400 font-mono truncate max-w-[180px]">
                        {item.chunk_id}
                      </code>
                      <span className={`text-xs px-1 py-0.5 rounded ${typeBadge(item.source_type)}`}>
                        {item.source_type}
                      </span>
                      <span className="text-xs text-slate-400 truncate ml-auto">{item.source}</span>
                    </div>
                    <p className="text-xs text-slate-600 leading-relaxed">{item.content_preview}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
