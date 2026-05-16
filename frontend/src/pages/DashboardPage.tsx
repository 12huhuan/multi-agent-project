import { Link } from "react-router-dom";
import { FileText, MessageSquare, ArrowRight } from "lucide-react";

const workflows = [
  {
    title: "Listing 优化",
    description: "AI 驱动的亚马逊 Listing 优化工作流 — 关键词研究 → 标题生成 → 五点描述 → 长描述 → A+内容 → SEO评分",
    icon: FileText,
    to: "/listing",
    agents: 6,
  },
  {
    title: "智能客服",
    description: "多渠道智能客服系统 — 意图识别 → RAG检索 → 回复生成 → 升级决策 → 工单生成",
    icon: MessageSquare,
    to: "/customer-service",
    agents: 5,
  },
];

export default function DashboardPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 mb-2">Cross-Border Agents</h1>
      <p className="text-slate-500 mb-8">跨境电商多 Agent 智能决策系统 — Phase 1 MVP</p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {workflows.map(({ title, description, icon: Icon, to, agents }) => (
          <Link
            key={to}
            to={to}
            className="block p-6 bg-white rounded-xl border border-slate-200 hover:border-blue-300 hover:shadow-md transition-all"
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="p-2 bg-blue-50 rounded-lg">
                <Icon size={24} className="text-blue-600" />
              </div>
              <div>
                <h3 className="font-semibold text-slate-900">{title}</h3>
                <span className="text-xs text-slate-400">{agents} Agents</span>
              </div>
            </div>
            <p className="text-sm text-slate-500 mb-4">{description}</p>
            <div className="flex items-center text-sm text-blue-600 font-medium">
              开始使用 <ArrowRight size={14} className="ml-1" />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
