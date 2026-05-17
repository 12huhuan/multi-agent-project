import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import {
  TrendingUp, FileText, Shield, Share2, Star, BarChart3,
  MessageSquare, ArrowRight, Plus, ChevronRight
} from "lucide-react";
import { API_BASE } from "../lib/utils";
import ChartWidget from "../components/ChartWidget";

interface StageStat {
  label: string;
  icon: React.ComponentType<{ size?: number }>;
  to: string;
  count: number;
  status: "idle" | "active" | "warning";
  color: string;
}

const stages: StageStat[] = [
  {
    label: "选品分析",
    icon: TrendingUp,
    to: "/selection",
    count: 0,
    status: "idle",
    color: "emerald",
  },
  {
    label: "Listing",
    icon: FileText,
    to: "/listing",
    count: 0,
    status: "idle",
    color: "blue",
  },
  {
    label: "合规审查",
    icon: Shield,
    to: "/compliance",
    count: 0,
    status: "idle",
    color: "orange",
  },
  {
    label: "社媒内容",
    icon: Share2,
    to: "/social",
    count: 0,
    status: "idle",
    color: "pink",
  },
  {
    label: "评论监控",
    icon: Star,
    to: "/reviews",
    count: 0,
    status: "idle",
    color: "amber",
  },
  {
    label: "广告管理",
    icon: BarChart3,
    to: "/ads",
    count: 0,
    status: "idle",
    color: "purple",
  },
];

const statusBadge = (s: StageStat) => {
  switch (s.status) {
    case "active":
      return `bg-${s.color}-50 text-${s.color}-700 border-${s.color}-200`;
    case "warning":
      return "bg-red-50 text-red-700 border-red-200";
    default:
      return "bg-gray-50 text-gray-500 border-gray-200";
  }
};

export default function DashboardPage() {
  const [logs, setLogs] = useState<any[]>([]);
  const [stageStats] = useState<StageStat[]>(stages);

  useEffect(() => {
    fetchLogs();
  }, []);

  const fetchLogs = async () => {
    try {
      const res = await fetch(`${API_BASE}/orchestrator/logs`);
      if (res.ok) {
        const data = await res.json();
        setLogs(data.slice(0, 8));
      }
    } catch {}
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">产品管线</h1>
          <p className="text-sm text-slate-500 mt-1">
            从选品到运营的全生命周期追踪
          </p>
        </div>
        <Link
          to="/orchestrator"
          className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 text-sm transition-colors"
        >
          <Plus size={16} />
          新建产品
        </Link>
      </div>

      {/* Pipeline stages */}
      <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
        {stageStats.map((stage, i) => {
          const Icon = stage.icon;
          return (
            <Link
              key={stage.label}
              to={stage.to}
              className={`bg-white rounded-xl border p-4 hover:shadow-md transition-all group ${
                stage.status === "active"
                  ? "border-blue-300 ring-1 ring-blue-100"
                  : "border-slate-200"
              }`}
            >
              <div className={`p-2 rounded-lg inline-block bg-${stage.color}-50 mb-3`}>
                <Icon size={20} className={`text-${stage.color}-600`} />
              </div>
              <div className="text-sm font-medium text-slate-700 group-hover:text-slate-900">
                {stage.label}
              </div>
              <div className="flex items-center justify-between mt-2">
                <span className={`text-xs px-1.5 py-0.5 rounded ${statusBadge(stage)}`}>
                  {stage.count > 0 ? `${stage.count} 个` : "待启动"}
                </span>
                {i < stageStats.length - 1 && (
                  <ChevronRight size={12} className="text-slate-300 hidden md:block" />
                )}
              </div>
            </Link>
          );
        })}
      </div>

      {/* Quick actions grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <QuickCard
          icon={TrendingUp}
          title="智能选品"
          desc="分析品类趋势，发现潜力产品"
          to="/selection"
          color="emerald"
        />
        <QuickCard
          icon={FileText}
          title="Listing 生成"
          desc="AI 生成完整 Amazon 产品页"
          to="/listing"
          color="blue"
        />
        <QuickCard
          icon={Share2}
          title="社媒推广"
          desc="一键生成多平台推广素材"
          to="/social"
          color="pink"
        />
        <QuickCard
          icon={MessageSquare}
          title="客服应答"
          desc="智能客服 SSE 流式对话"
          to="/customer-service"
          color="indigo"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartWidget
          type="pie"
          title="产品流程分布"
          data={{
            "待选品": stageStats[0].count || 3,
            "Listing中": stageStats[1].count || 2,
            "合规中": stageStats[2].count || 1,
            "已发布": stageStats[3].count || 4,
          }}
        />
        <ChartWidget
          type="bar"
          title="运营阶段总览"
          data={Object.fromEntries(stageStats.map(s => [s.label, s.count || Math.floor(Math.random() * 5) + 1]))}
        />
      </div>

      {/* Recent activity */}
      <div className="bg-white rounded-xl border">
        <div className="p-4 border-b flex items-center justify-between">
          <h3 className="font-semibold text-sm text-slate-800">最近活动</h3>
          <button
            onClick={fetchLogs}
            className="text-xs text-blue-600 hover:text-blue-800"
          >
            刷新
          </button>
        </div>
        <div className="divide-y">
          {logs.length === 0 && (
            <div className="p-6 text-center text-sm text-slate-400">
              暂无活动记录。前往
              <Link to="/orchestrator" className="text-purple-600 mx-1 hover:underline">
                调度中心
              </Link>
              启动一次全流程。
            </div>
          )}
          {logs.map((log: any, i: number) => (
            <div key={i} className="p-3 flex items-center gap-3 text-sm">
              <span className="text-xs text-slate-400 w-12 shrink-0">
                {log.id ? `#${log.id}` : ""}
              </span>
              <span className="font-medium text-slate-600 w-16 shrink-0">
                {log.action === "auto" ? "全流程" : log.action}
              </span>
              <span className="text-slate-400 truncate">{log.summary}</span>
              <ArrowRight size={14} className="text-slate-300 shrink-0 ml-auto" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function QuickCard({
  icon: Icon,
  title,
  desc,
  to,
  color,
}: {
  icon: React.ComponentType<{ size?: number }>;
  title: string;
  desc: string;
  to: string;
  color: string;
}) {
  return (
    <Link
      to={to}
      className="bg-white rounded-xl border border-slate-200 p-4 hover:shadow-md hover:border-slate-300 transition-all group"
    >
      <div className={`p-2 rounded-lg inline-block bg-${color}-50 mb-3`}>
        <Icon size={20} className={`text-${color}-600`} />
      </div>
      <h4 className="font-medium text-sm text-slate-800">{title}</h4>
      <p className="text-xs text-slate-500 mt-1">{desc}</p>
      <div className="flex items-center text-xs text-blue-600 font-medium mt-3 opacity-0 group-hover:opacity-100 transition-opacity">
        开始使用 <ArrowRight size={12} className="ml-1" />
      </div>
    </Link>
  );
}
