"use client";

import { useEffect } from "react";
import {
  X,
  Shield,
  LayoutDashboard,
  Bell,
  Activity,
  ShieldAlert,
  BarChart3,
  Database,
  Settings,
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

interface MobileNavProps {
  open: boolean;
  onClose: () => void;
  activeItem?: string;
}

export default function MobileNav({
  open,
  onClose,
  activeItem = "dashboard",
}: MobileNavProps) {
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/30 z-40 md:hidden"
        onClick={onClose}
      />
      {/* Drawer */}
      <div className="fixed left-0 top-0 h-full w-64 bg-white z-50 md:hidden shadow-2xl flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-indigo-600 flex items-center justify-center">
              <Shield className="w-4 h-4 text-white" />
            </div>
            <span className="font-semibold text-slate-800">OpenGuardian</span>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-500 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
          {navItems.map(({ icon: Icon, label, id }) => (
            <button
              key={id}
              className={cn(
                "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors",
                activeItem === id
                  ? "bg-indigo-50 text-indigo-600"
                  : "text-slate-600 hover:bg-slate-50"
              )}
              onClick={onClose}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </button>
          ))}
        </nav>

        <div className="p-3 border-t border-slate-100">
          <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors">
            <Settings className="w-4 h-4 flex-shrink-0" />
            Settings
          </button>
        </div>
      </div>
    </>
  );
}
