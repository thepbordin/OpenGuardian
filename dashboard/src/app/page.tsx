"use client";

import { useState } from "react";
import Sidebar from "@/components/sidebar";
import Header from "@/components/header";
import MobileNav from "@/components/mobile-nav";
import BehaviorScore from "@/components/dashboard/behavior-score";
import ActivityCards from "@/components/dashboard/activity-cards";
import ActivityChart from "@/components/dashboard/activity-chart";
import BaselineComparison from "@/components/dashboard/baseline-comparison";
import RecentAlerts from "@/components/dashboard/recent-alerts";
import AiSummary from "@/components/dashboard/ai-summary";
import DataSources from "@/components/dashboard/data-sources";

export default function DashboardPage() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <>
      {/* Full-screen rounded dashboard container */}
      <div className="h-screen bg-neutral-900 p-0 sm:p-3 lg:p-5 overflow-hidden">
        <div className="h-full flex bg-white rounded-none sm:rounded-2xl lg:rounded-3xl shadow-sm overflow-hidden border-0 sm:border sm:border-slate-200/60">
          {/* Icon-only sidebar */}
          <Sidebar activeItem="dashboard" />

          {/* Main content column */}
          <div className="flex-1 flex flex-col overflow-hidden min-w-0">
            <Header onMenuClick={() => setMobileNavOpen(true)} />

            {/* Scrollable content */}
            <main className="flex-1 overflow-y-auto bg-slate-50/40 p-4 md:p-5 lg:p-6">
              {/* Profile selector chip */}
              <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-2">
                  <div className="flex items-center gap-2.5 bg-white rounded-xl px-3.5 py-2 shadow-sm border border-slate-100">
                    <div className="relative">
                      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-violet-400 to-indigo-500 flex items-center justify-center text-white text-xs font-bold">
                        A
                      </div>
                      <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-400 border-2 border-white" />
                    </div>
                    <span className="text-sm font-semibold text-slate-800">
                      Alex
                    </span>
                    <span className="text-xs text-slate-400 font-medium hidden sm:inline">
                      Child profile
                    </span>
                  </div>
                </div>
                <p className="text-xs text-slate-400 hidden sm:block">
                  Last updated: Today at 10:32 AM
                </p>
              </div>

              {/* Row 1 — Behavior Score + Activity Cards */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
                <div className="lg:col-span-1">
                  <BehaviorScore />
                </div>
                <div className="lg:col-span-2">
                  <ActivityCards />
                </div>
              </div>

              {/* Row 2 — Activity Trend Chart */}
              <div className="mb-4">
                <ActivityChart />
              </div>

              {/* Row 3 — Baseline vs Current + Recent Alerts */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
                <BaselineComparison />
                <RecentAlerts />
              </div>

              {/* Row 4 — AI Summary + Data Sources */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                <div className="lg:col-span-2">
                  <AiSummary />
                </div>
                <div className="lg:col-span-1">
                  <DataSources />
                </div>
              </div>
            </main>
          </div>
        </div>
      </div>

      {/* Mobile drawer nav (rendered outside the rounded card) */}
      <MobileNav
        open={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
      />
    </>
  );
}
