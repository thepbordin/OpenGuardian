"use client";

import {
  LayoutDashboard,
  Bell,
  Activity,
  ShieldAlert,
  BarChart3,
  Database,
  Settings,
  Shield,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { icon: LayoutDashboard, label: "Dashboard", id: "dashboard" },
  { icon: Bell, label: "Alerts", id: "alerts" },
  { icon: Activity, label: "Activity Timeline", id: "timeline" },
  { icon: ShieldAlert, label: "Risk Patterns", id: "risks" },
  { icon: BarChart3, label: "Reports", id: "reports" },
  { icon: Database, label: "Data Sources", id: "sources" },
];

interface SidebarProps {
  activeItem?: string;
  onItemSelect?: (id: string) => void;
}

export default function Sidebar({
  activeItem = "dashboard",
  onItemSelect,
}: SidebarProps) {
  return (
    <aside className="hidden md:flex flex-col items-center w-[72px] flex-shrink-0 border-r border-slate-100 py-5 gap-1">
      {/* Logo */}
      <div className="mb-5 w-10 h-10 rounded-xl bg-indigo-600 flex items-center justify-center flex-shrink-0 shadow-sm">
        <Shield className="w-5 h-5 text-white" />
      </div>

      {/* Nav items */}
      <nav className="flex flex-col items-center gap-1 flex-1 w-full px-3">
        {navItems.map(({ icon: Icon, label, id }) => (
          <button
            key={id}
            title={label}
            onClick={() => onItemSelect?.(id)}
            className={cn(
              "w-full h-10 flex items-center justify-center rounded-xl transition-colors",
              activeItem === id
                ? "bg-indigo-50 text-indigo-600"
                : "text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            )}
          >
            <Icon className="w-[18px] h-[18px]" />
          </button>
        ))}
      </nav>

      {/* Settings */}
      <div className="w-full px-3">
        <button
          title="Settings"
          className="w-full h-10 flex items-center justify-center rounded-xl text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors"
        >
          <Settings className="w-[18px] h-[18px]" />
        </button>
      </div>
    </aside>
  );
}
