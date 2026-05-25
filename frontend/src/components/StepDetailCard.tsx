import { useState } from "react";
import { ChevronDown, ChevronRight, ExternalLink, Edit3, AlertTriangle, CheckCircle, XCircle, Image } from "lucide-react";
import { useNavigate } from "react-router-dom";

interface Props {
  step: any;
  index: number;
}

export default function StepDetailCard({ step, index }: Props) {
  const [expanded, setExpanded] = useState(false);
  const navigate = useNavigate();
  const d = step;
  const data = d.data || {};

  const statusBadge = (status: string) => {
    const cls =
      status === "done" ? "bg-green-100 text-green-700" :
      status === "failed" ? "bg-red-100 text-red-700" :
      "bg-yellow-100 text-yellow-700";
    return <span className={`px-1.5 py-0.5 rounded font-medium text-xs ${cls}`}>{status}</span>;
  };

  const actionLabel = (action: string) => {
    const map: Record<string, string> = {
      select_product: "智能选品",
      run_listing: "Listing 生成",
      check_compliance: "合规审查",
      generate_social: "社媒内容",
      monitor_reviews: "评论监控",
    };
    return map[action] || action;
  };

  return (
    <div className="mb-3 border rounded-lg overflow-hidden">
      {/* Header — always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 p-3 bg-gray-50 text-xs text-left hover:bg-gray-100 transition-colors"
      >
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        {statusBadge(d.status)}
        <span className="font-medium">{actionLabel(d.action)}</span>
        <span className="text-gray-400">— {d.reason}</span>
        <span className="ml-auto text-gray-400">{expanded ? "收起" : "展开详情"}</span>
      </button>

      {/* Expandable detail */}
      {expanded && (
        <div className="p-3 border-t bg-gray-50/50 text-xs space-y-3">
          {d.result && <div className="text-gray-600 italic mb-2">{d.result}</div>}

          {/* ── Selection ── */}
          {d.action === "select_product" && (
            <div className="space-y-2">
              {data.top_pick && (
                <div className="font-medium">
                  Top Pick: <span className="text-emerald-700">{data.top_pick}</span>
                  <span className="text-gray-400 ml-2">({data.product_count} products found)</span>
                </div>
              )}
              {data.category_overview && <p className="text-gray-600">{data.category_overview}</p>}
              {data.recommended_niches?.length > 0 && (
                <div>
                  <div className="font-medium text-gray-500 mb-1">推荐利基</div>
                  <div className="flex flex-wrap gap-1">
                    {data.recommended_niches.map((n: string, i: number) => (
                      <span key={i} className="px-2 py-0.5 bg-emerald-50 text-emerald-700 rounded">{n}</span>
                    ))}
                  </div>
                </div>
              )}
              {data.scored_products?.length > 0 && (
                <div>
                  <div className="font-medium text-gray-500 mb-1">评分产品</div>
                  {data.scored_products.map((p: any, j: number) => (
                    <div key={j} className="flex justify-between py-1 border-b border-gray-100 last:border-0">
                      <span className="truncate max-w-[300px]">{p.product_name}</span>
                      <span className="text-gray-500 shrink-0">
                        score: {typeof p.overall_score === "number" ? p.overall_score.toFixed(1) : p.overall_score} | {p.verdict}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── Listing ── */}
          {d.action === "run_listing" && (
            <div className="space-y-3">
              {/* Action buttons */}
              <div className="flex gap-2">
                {data.listing_task_id && data.status !== "failed" && (
                  <button
                    onClick={() => navigate(`/listing?taskId=${data.listing_task_id}`)}
                    className="flex items-center gap-1 px-3 py-1.5 bg-blue-100 text-blue-700 rounded text-xs hover:bg-blue-200 transition-colors"
                  >
                    <Edit3 size={12} /> 审核 Listing
                  </button>
                )}
              </div>

              {/* Keywords */}
              {data.keywords?.length > 0 && (
                <div>
                  <div className="font-medium text-gray-500 mb-1">关键词 ({data.keywords.length})</div>
                  <div className="flex flex-wrap gap-1">
                    {data.keywords.slice(0, 15).map((kw: any, i: number) => (
                      <span key={i} className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-xs">
                        {kw.keyword || kw}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Top Keywords */}
              {data.top_keywords?.length > 0 && (
                <div>
                  <div className="font-medium text-gray-500 mb-1">Top 关键词</div>
                  <div className="flex flex-wrap gap-1">
                    {data.top_keywords.map((kw: string, i: number) => (
                      <span key={i} className="px-2 py-0.5 bg-purple-50 text-purple-700 rounded text-xs">{kw}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* Title Candidates */}
              {data.title_candidates?.length > 0 && (
                <div>
                  <div className="font-medium text-gray-500 mb-1">标题候选</div>
                  {data.title_candidates.map((t: any, i: number) => (
                    <div key={i} className={`p-2 rounded mb-1 ${t.title === data.best_title ? "bg-green-50 border border-green-200" : "bg-slate-50"}`}>
                      <div className="flex justify-between mb-0.5">
                        <span className="font-medium">候选 {i + 1}</span>
                        <span className="text-blue-600">评分: {t.score}</span>
                      </div>
                      <p className="text-slate-700">{t.title}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Bullet Points */}
              {data.bullet_points?.length > 0 && (
                <div>
                  <div className="font-medium text-gray-500 mb-1">五点描述</div>
                  <ul className="list-disc pl-4 space-y-1">
                    {data.bullet_points.map((bp: any, i: number) => (
                      <li key={i} className="text-slate-700">{typeof bp === "string" ? bp : bp.text}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Description HTML */}
              {data.description_html && (
                <div>
                  <div className="font-medium text-gray-500 mb-1">产品长描述</div>
                  <div
                    className="border rounded p-2 max-h-[150px] overflow-auto prose prose-xs"
                    dangerouslySetInnerHTML={{ __html: data.description_html.slice(0, 2000) }}
                  />
                </div>
              )}

              {/* A+ Modules */}
              {data.a_plus_modules?.length > 0 && (
                <div>
                  <div className="font-medium text-gray-500 mb-1">A+ 内容模块 ({data.a_plus_modules.length})</div>
                  <div className="space-y-1.5">
                    {data.a_plus_modules.map((mod: any, i: number) => (
                      <div key={i} className="border rounded p-2 bg-white">
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="px-1.5 py-0.5 rounded bg-slate-200 text-slate-600 text-xs">{mod.type || `模块 ${i + 1}`}</span>
                          {mod.title && <span className="font-medium text-slate-700">{mod.title}</span>}
                        </div>
                        {mod.content && <p className="text-slate-600 mt-0.5">{mod.content?.slice(0, 200)}</p>}
                        {mod.image_suggestion && <p className="text-blue-500 mt-0.5 text-xs">图片建议: {mod.image_suggestion}</p>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* SEO Report */}
              {data.seo_report && Object.keys(data.seo_report).length > 0 && (
                <div>
                  <div className="font-medium text-gray-500 mb-1">SEO 评分</div>
                  {data.seo_report.overall_score > 0 && (
                    <div className="text-xl font-bold text-blue-600 mb-2">
                      {typeof data.seo_report.overall_score === "number"
                        ? data.seo_report.overall_score.toFixed(0)
                        : data.seo_report.overall_score}
                      <span className="text-sm text-slate-400">/100</span>
                    </div>
                  )}
                  <div className="grid grid-cols-2 gap-1.5">
                    {Object.entries(data.seo_report)
                      .filter(([k]) => !["overall_score", "overallScore", "improvement_priority"].includes(k))
                      .map(([key, value]) => (
                        <div key={key} className="bg-white rounded p-1.5">
                          <span className="text-slate-500 capitalize">{key.replace(/_/g, " ")}</span>
                          <span className="text-slate-700 ml-1.5">
                            {typeof value === "object" ? JSON.stringify(value).slice(0, 40) : String(value)}
                          </span>
                        </div>
                      ))}
                  </div>
                </div>
              )}

              {/* Product Images */}
              {data.product_images?.length > 0 && (
                <div>
                  <div className="font-medium text-gray-500 mb-1">产品图片</div>
                  <div className="grid grid-cols-3 gap-2">
                    {data.product_images.map((img: any, i: number) => (
                      <div key={i} className="border rounded overflow-hidden bg-white">
                        <img
                          src={img.url || img}
                          alt={img.description || `Product image ${i + 1}`}
                          className="w-full h-32 object-cover"
                          onError={(e) => {
                            (e.target as HTMLImageElement).style.display = "none";
                          }}
                        />
                        {img.description && <p className="p-1 text-gray-500 truncate">{img.description}</p>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── Compliance ── */}
          {d.action === "check_compliance" && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                {data.verdict === "pass" ? <CheckCircle size={16} className="text-green-500" /> :
                 data.verdict === "violation" ? <XCircle size={16} className="text-red-500" /> :
                 <AlertTriangle size={16} className="text-yellow-500" />}
                <span className={`font-medium text-sm ${
                  data.verdict === "pass" ? "text-green-700" : data.verdict === "warning" ? "text-yellow-700" : "text-red-700"
                }`}>
                  {data.verdict?.toUpperCase()}
                </span>
                <span className="text-gray-500">{data.total_issues} issues | Risk: {data.risk_level}</span>
              </div>
              {data.critical_items?.length > 0 && (
                <div>
                  <div className="font-medium text-red-600 mb-0.5">严重问题</div>
                  {data.critical_items.map((c: string, j: number) => (
                    <div key={j} className="text-red-600 ml-2">- {c}</div>
                  ))}
                </div>
              )}
              {data.action_items?.length > 0 && (
                <div>
                  <div className="font-medium text-blue-600 mb-0.5">建议操作</div>
                  {data.action_items.map((a: string, j: number) => (
                    <div key={j} className="text-blue-600 ml-2">- {a}</div>
                  ))}
                </div>
              )}
              {data.policy_issues?.length > 0 && (
                <div>
                  <div className="font-medium text-gray-500 mb-0.5">政策问题</div>
                  {data.policy_issues.map((p: any, j: number) => (
                    <div key={j} className="text-gray-600 ml-2">- {typeof p === "string" ? p : p.description}</div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── Social ── */}
          {d.action === "generate_social" && (
            <div className="space-y-2">
              {data.marketing_angles?.length > 0 && (
                <div>
                  <div className="font-medium text-gray-500 mb-1">营销角度</div>
                  <div className="flex flex-wrap gap-1">
                    {data.marketing_angles.map((a: string, i: number) => (
                      <span key={i} className="px-2 py-0.5 bg-pink-50 text-pink-700 rounded">{a}</span>
                    ))}
                  </div>
                </div>
              )}
              {data.posts?.length > 0 && (
                <div>
                  <div className="font-medium text-gray-500 mb-1">社媒帖子 ({data.post_count || data.posts.length})</div>
                  {data.posts.map((p: any, j: number) => (
                    <div key={j} className="border-l-2 border-pink-300 pl-3 py-1 mb-2">
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="font-medium px-1.5 py-0.5 rounded bg-gray-200 text-gray-700 text-xs">[{p.platform}]</span>
                        <span className="text-gray-500">score: {p.quality_score}</span>
                      </div>
                      <div className="text-gray-600 whitespace-pre-wrap">{p.copy}</div>
                      {p.hashtags?.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {p.hashtags.map((h: string, i: number) => (
                            <span key={i} className="text-blue-500">{h}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── Reviews ── */}
          {d.action === "monitor_reviews" && (
            <div className="space-y-2">
              <div>
                <span className="font-medium">{data.total_scraped}</span>
                <span className="text-gray-500"> reviews scraped, </span>
                <span className="text-red-600 font-medium">{data.alert_count} alerts</span>
                <span className="text-gray-500">, </span>
                <span className="text-yellow-600">{data.negative_count} negative</span>
              </div>
              {data.alerts?.length > 0 && (
                <div>
                  <div className="font-medium text-red-600 mb-0.5">预警详情</div>
                  {data.alerts.map((a: any, j: number) => (
                    <div key={j} className="text-red-600 ml-2 py-0.5">
                      - [{a.alert_level}] {a.reviewer}: {a.content}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
