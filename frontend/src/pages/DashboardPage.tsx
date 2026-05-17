import { useState } from "react";
import { Link } from "react-router-dom";
import {
  FileText, MessageSquare, BookOpen, MessageSquareWarning,
  Share2, TrendingUp, Shield, Zap, Eye, Target, ArrowRight
} from "lucide-react";

const phases = [
  {
    label: "Phase 1",
    color: "blue",
    workflows: [
      {
        title: "Listing 优化",
        description: "AI 驱动的亚马逊 Listing — 关键词研究 → 标题生成 → 五点描述 → 长描述 → A+内容 → SEO评分",
        icon: FileText,
        to: "/listing",
        agents: 6,
      },
      {
        title: "智能客服",
        description: "多渠道智能客服 — 意图识别 → RAG检索 → 回复生成 → 升级决策 → 工单生成，支持 SSE 流式",
        icon: MessageSquare,
        to: "/customer-service",
        agents: 5,
      },
      {
        title: "知识库",
        description: "RAG 向量知识库管理 — Markdown/PDF/URL 导入 → ChromaDB 向量检索 → 语义搜索",
        icon: BookOpen,
        to: "/knowledge-base",
        agents: 0,
      },
    ],
  },
  {
    label: "Phase 2",
    color: "emerald",
    workflows: [
      {
        title: "评论监控",
        description: "Amazon 评论抓取 → 情感分析 → 翻译 → 负面预警 → 智能回复建议",
        icon: MessageSquareWarning,
        to: "/reviews",
        agents: 5,
      },
      {
        title: "社媒内容",
        description: "产品分析 → 多平台适配 (IG/Threads/Pinterest/FB/TT) → AI 文案 → 图片生成 → 质检",
        icon: Share2,
        to: "/social",
        agents: 5,
      },
    ],
  },
  {
    label: "Phase 3",
    color: "purple",
    workflows: [
      {
        title: "智能选品",
        description: "品类趋势分析 → 产品匹配 → 机会评分 (竞争/利润/趋势/风险) → 选品报告",
        icon: TrendingUp,
        to: "/selection",
        agents: 3,
      },
      {
        title: "合规审查",
        description: "Amazon 政策检查 → 声明验证 → 风险报告 (通过/警告/违规) → 整改建议",
        icon: Shield,
        to: "/compliance",
        agents: 3,
      },
      {
        title: "调度中心",
        description: "全自动化编排 — 选品→Listing→合规→社媒→评论，一站式自动执行 + 实时进度",
        icon: Zap,
        to: "/orchestrator",
        agents: 1,
      },
      {
        title: "广告管理",
        description: "广告效果分析 → 竞价优化 → 预算分配 (ACOS/ROAS/CTR/CPC 多维度)",
        icon: Target,
        to: "/ads",
        agents: 3,
      },
      {
        title: "社媒动态",
        description: "已发布社媒内容展示 — 小红书风格卡片，多平台内容浏览",
        icon: Eye,
        to: "/feed",
        agents: 0,
      },
    ],
  },
];

const colorMap: Record<string, { badge: string; icon: string; border: string; hover: string }> = {
  blue:   { badge: "bg-blue-50 text-blue-700",    icon: "bg-blue-50 text-blue-600",    border: "border-slate-200 hover:border-blue-300",    hover: "hover:shadow-blue-100" },
  emerald:{ badge: "bg-emerald-50 text-emerald-700", icon: "bg-emerald-50 text-emerald-600", border: "border-slate-200 hover:border-emerald-300", hover: "hover:shadow-emerald-100" },
  purple: { badge: "bg-purple-50 text-purple-700",  icon: "bg-purple-50 text-purple-600",  border: "border-slate-200 hover:border-purple-300",  hover: "hover:shadow-purple-100" },
};

export default function DashboardPage() {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const totalAgents = phases.flatMap(p => p.workflows).reduce((sum, w) => sum + w.agents, 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Cross-Border Agents</h1>
          <p className="text-slate-500">跨境电商多 Agent 全自动化系统 — {phases.length} Phase · {totalAgents} Agents · 10 页面</p>
        </div>
      </div>

      <div className="space-y-6 mt-8">
        {phases.map(({ label, color, workflows }) => {
          const c = colorMap[color];
          const isOpen = !collapsed[label];
          return (
            <div key={label}>
              <button
                onClick={() => setCollapsed(prev => ({ ...prev, [label]: !prev[label] }))}
                className="flex items-center gap-2 mb-3 group"
              >
                <span className={`text-xs font-semibold px-2 py-0.5 rounded ${c.badge}`}>{label}</span>
                <span className="text-xs text-slate-400 group-hover:text-slate-600 transition-colors">
                  {isOpen ? "收起" : "展开"} · {workflows.length} 模块
                </span>
              </button>

              {isOpen && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {workflows.map(({ title, description, icon: Icon, to, agents }) => (
                    <Link
                      key={to}
                      to={to}
                      className={`block p-5 bg-white rounded-xl border ${c.border} hover:shadow-md transition-all ${c.hover}`}
                    >
                      <div className="flex items-center gap-3 mb-3">
                        <div className={`p-2 rounded-lg ${c.icon}`}>
                          <Icon size={22} />
                        </div>
                        <div>
                          <h3 className="font-semibold text-slate-900 text-sm">{title}</h3>
                          {agents > 0 && (
                            <span className="text-xs text-slate-400">{agents} Agents</span>
                          )}
                        </div>
                      </div>
                      <p className="text-xs text-slate-500 mb-3 leading-relaxed">{description}</p>
                      <div className="flex items-center text-xs text-blue-600 font-medium">
                        开始使用 <ArrowRight size={12} className="ml-1" />
                      </div>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
