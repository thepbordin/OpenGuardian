"use client";

import { TrendingUp } from "lucide-react";
import { ResponsiveContainer, AreaChart, Area, Tooltip } from "recharts";
import { behaviorScoreData } from "@/lib/mock-data";

export default function BehaviorScore() {
  return (
    <div className="bg-gradient-to-br from-indigo-500 via-indigo-600 to-violet-700 rounded-2xl p-5 text-white relative overflow-hidden h-full min-h-[220px]">
      {/* Decorative circles */}
      <div className="absolute -top-8 -right-8 w-36 h-36 rounded-full bg-white/[0.06] pointer-events-none" />
      <div className="absolute -bottom-8 -left-8 w-28 h-28 rounded-full bg-white/[0.06] pointer-events-none" />

      <div className="relative flex flex-col h-full">
        <div className="flex items-start justify-between mb-4">
          <div>
            <p className="text-indigo-200 text-[10px] font-semibold uppercase tracking-widest mb-2">
              Behavior Stability Score
            </p>
            <div className="flex items-end gap-2">
              <span className="text-5xl font-bold tracking-tight">85%</span>
              <div className="flex items-center gap-1 pb-1.5 text-emerald-300 text-sm font-semibold">
                <TrendingUp className="w-4 h-4" />
                +2.4%
              </div>
            </div>
            <p className="text-indigo-300 text-xs mt-1">vs. last week</p>
          </div>
          <div className="w-11 h-11 rounded-xl bg-white/10 backdrop-blur-sm flex items-center justify-center text-xl flex-shrink-0">
            🛡️
          </div>
        </div>

        <div className="flex-1 min-h-[80px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={behaviorScoreData}
              margin={{ top: 4, right: 0, bottom: 0, left: 0 }}
            >
              <defs>
                <linearGradient
                  id="scoreGradient"
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop offset="5%" stopColor="#ffffff" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#ffffff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="score"
                stroke="#ffffff"
                strokeWidth={2}
                fill="url(#scoreGradient)"
                dot={false}
                activeDot={{ r: 3, fill: "#ffffff", strokeWidth: 0 }}
              />
              <Tooltip
                contentStyle={{
                  background: "rgba(255,255,255,0.15)",
                  backdropFilter: "blur(8px)",
                  border: "1px solid rgba(255,255,255,0.2)",
                  borderRadius: "10px",
                  color: "#fff",
                  fontSize: "12px",
                  padding: "6px 10px",
                }}
                itemStyle={{ color: "#fff" }}
                labelStyle={{
                  color: "rgba(255,255,255,0.7)",
                  fontSize: "11px",
                }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <p className="text-indigo-300 text-xs mt-2">7-day trend</p>
      </div>
    </div>
  );
}
