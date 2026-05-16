import { useEffect, useState } from "react";
import { Outlet, NavLink } from "react-router-dom";
import { LayoutDashboard, FileText, MessageSquare, BookOpen, Loader2 } from "lucide-react";
import { taskStore } from "../lib/TaskStore";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/listing", icon: FileText, label: "Listing 优化" },
  { to: "/customer-service", icon: MessageSquare, label: "智能客服" },
  { to: "/knowledge-base", icon: BookOpen, label: "知识库" },
];

export default function Layout() {
  const [runningCount, setRunningCount] = useState(0);
  const [runningTasks, setRunningTasks] = useState(taskStore.getAll().filter((t) => t.status === "running"));

  useEffect(() => {
    return taskStore.subscribe(() => {
      const all = taskStore.getAll();
      setRunningCount(all.filter((t) => t.status === "running").length);
      setRunningTasks(all.filter((t) => t.status === "running"));
    });
  }, []);

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-900 text-white p-4 flex flex-col gap-2">
        <div className="text-lg font-bold px-3 py-4 border-b border-slate-700 mb-2">
          CrossBorder Agents
          <span className="block text-xs text-slate-400 font-normal mt-1">Phase 1 — MVP</span>
        </div>
        <nav className="flex flex-col gap-1">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${
                  isActive ? "bg-slate-700 text-white" : "text-slate-300 hover:bg-slate-800"
                }`
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* 后台任务指示器 */}
        {runningCount > 0 && (
          <div className="mt-auto mb-4 mx-2 p-3 bg-slate-800 rounded-lg border border-slate-700">
            <div className="flex items-center gap-2 text-sm text-slate-300 mb-2">
              <Loader2 size={14} className="animate-spin text-blue-400" />
              {runningCount} 个任务运行中
            </div>
            {runningTasks.map((t) => (
              <div key={t.id} className="text-xs text-slate-500 truncate">
                {t.product_name?.slice(0, 30)}...
              </div>
            ))}
            <p className="text-xs text-slate-500 mt-2">切换页面不会中断</p>
          </div>
        )}
      </aside>

      {/* Main content */}
      <main className="flex-1 p-6 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
