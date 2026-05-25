import { useEffect, useState } from "react";
import { Outlet, NavLink } from "react-router-dom";
import {
  LayoutDashboard, FileText, MessageSquare, BookOpen,
  MessageSquareWarning, Share2, TrendingUp, Shield,
  Zap, Eye, Target, Loader2,
  Package, Megaphone, BarChart3, Settings
} from "lucide-react";
import { taskStore } from "../lib/TaskStore";

const navGroups = [
  {
    label: "产品上架",
    icon: Package,
    items: [
      { to: "/selection", icon: TrendingUp, label: "智能选品" },
      { to: "/listing", icon: FileText, label: "Listing 生成" },
      { to: "/compliance", icon: Shield, label: "合规审查" },
    ],
  },
  {
    label: "内容营销",
    icon: Megaphone,
    items: [
      { to: "/social", icon: Share2, label: "社媒内容" },
      { to: "/feed", icon: Eye, label: "社媒动态" },
    ],
  },
  {
    label: "运营监控",
    icon: BarChart3,
    items: [
      { to: "/reviews", icon: MessageSquareWarning, label: "评论监控" },
      { to: "/ads", icon: Target, label: "广告管理" },
      { to: "/customer-service", icon: MessageSquare, label: "智能客服" },
    ],
  },
  {
    label: "系统",
    icon: Settings,
    items: [
      { to: "/orchestrator", icon: Zap, label: "调度中心" },
      { to: "/knowledge-base", icon: BookOpen, label: "知识库" },
    ],
  },
];

export default function Layout() {
  const [runningCount, setRunningCount] = useState(0);
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  useEffect(() => {
    return taskStore.subscribe(() => {
      const all = taskStore.getAll();
      setRunningCount(all.filter((t) => t.status === "running").length);
    });
  }, []);

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-900 text-white p-4 flex flex-col gap-1 overflow-auto">
        <NavLink to="/" className="text-lg font-bold px-3 py-4 border-b border-slate-700 mb-1 hover:text-blue-300 transition-colors">
          CrossBorder Agents
          <span className="block text-xs text-slate-400 font-normal mt-1">Full Automation</span>
        </NavLink>

        {/* Dashboard link */}
        <NavLink
          to="/"
          end
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2 rounded-lg transition-colors mb-2 ${
              isActive ? "bg-slate-700 text-white" : "text-slate-300 hover:bg-slate-800"
            }`
          }
        >
          <LayoutDashboard size={18} />
          仪表盘
        </NavLink>

        {/* Grouped nav items */}
        {navGroups.map(({ label, icon: GroupIcon, items }) => {
          const isOpen = !collapsed[label];
          return (
            <div key={label} className="mb-1">
              <button
                onClick={() => setCollapsed(prev => ({ ...prev, [label]: !prev[label] }))}
                className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-slate-400 uppercase tracking-wider hover:text-slate-200 transition-colors"
              >
                <GroupIcon size={14} />
                {label}
                <span className="ml-auto text-[10px]">{isOpen ? "▾" : "▸"}</span>
              </button>
              {isOpen && (
                <nav className="flex flex-col gap-0.5 mt-0.5">
                  {items.map(({ to, icon: Icon, label: itemLabel }) => (
                    <NavLink
                      key={to}
                      to={to}
                      className={({ isActive }) =>
                        `flex items-center gap-3 px-3 py-2 rounded-lg transition-colors text-sm ${
                          isActive ? "bg-slate-700 text-white" : "text-slate-300 hover:bg-slate-800"
                        }`
                      }
                    >
                      <Icon size={16} />
                      {itemLabel}
                    </NavLink>
                  ))}
                </nav>
              )}
            </div>
          );
        })}

        {/* 后台任务指示器 */}
        {runningCount > 0 && (
          <div className="mt-auto pt-4">
            <div className="p-3 bg-slate-800 rounded-lg border border-slate-700">
              <div className="flex items-center gap-2 text-sm text-slate-300 mb-2">
                <Loader2 size={14} className="animate-spin text-blue-400" />
                {runningCount} 个任务运行中
              </div>
              <p className="text-xs text-slate-500">切换页面不中断</p>
            </div>
          </div>
        )}
      </aside>

      {/* Main content */}
      <main className="flex-1 p-6 overflow-auto bg-slate-50">
        <Outlet />
      </main>
    </div>
  );
}
