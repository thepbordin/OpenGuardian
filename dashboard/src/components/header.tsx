"use client";

import { Search, Bell, ChevronDown, Menu } from "lucide-react";

interface HeaderProps {
  title?: string;
  onMenuClick?: () => void;
}

export default function Header({
  title = "Overview",
  onMenuClick,
}: HeaderProps) {
  return (
    <header className="flex-shrink-0 h-16 bg-white border-b border-slate-100 flex items-center justify-between px-5 lg:px-6">
      <div className="flex items-center gap-3">
        {/* Mobile hamburger */}
        <button
          onClick={onMenuClick}
          className="md:hidden w-9 h-9 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-500 transition-colors"
        >
          <Menu className="w-5 h-5" />
        </button>
        <div>
          <p className="text-[10px] text-slate-400 uppercase tracking-widest font-semibold leading-none mb-1">
            OpenGuardian
          </p>
          <h1 className="text-lg font-semibold text-slate-800 leading-none">
            {title}
          </h1>
        </div>
      </div>

      <div className="flex items-center gap-1.5">
        <button className="w-9 h-9 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-500 transition-colors">
          <Search className="w-4 h-4" />
        </button>
        <button className="relative w-9 h-9 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-500 transition-colors">
          <Bell className="w-4 h-4" />
          <span className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full bg-red-500" />
        </button>
        <div className="ml-2 flex items-center gap-2 cursor-pointer group">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-400 to-violet-500 flex items-center justify-center text-white text-sm font-semibold flex-shrink-0">
            P
          </div>
          <div className="hidden sm:block leading-none">
            <p className="text-sm font-medium text-slate-700">Parent</p>
            <p className="text-xs text-slate-400">Guardian</p>
          </div>
          <ChevronDown className="hidden sm:block w-3 h-3 text-slate-400" />
        </div>
      </div>
    </header>
  );
}
