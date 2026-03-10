"use client";

import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { activityTrendData } from "@/lib/mock-data";

const COLORS = {
  gaming: "#8B5CF6",
  education: "#0EA5E9",
  social: "#F43F5E",
  video: "#F59E0B",
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl shadow-lg p-3 text-xs">
        <p className="font-semibold text-slate-700 mb-2">{label}</p>
        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
        {payload.map((entry: any) => (
          <div
            key={entry.dataKey}
            className="flex items-center gap-2 mb-1 last:mb-0"
          >
            <span
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{ background: entry.color }}
            />
            <span className="text-slate-500 capitalize">{entry.dataKey}:</span>
            <span className="font-semibold text-slate-700">{entry.value}h</span>
          </div>
        ))}
      </div>
    );
  }
  return null;
};

export default function ActivityChart() {
  return (
    <div className="bg-white rounded-2xl p-5 lg:p-6 shadow-sm border border-slate-100">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
        <div>
          <h3 className="text-base font-semibold text-slate-800">
            Activity Overview
          </h3>
          <p className="text-slate-400 text-sm">
            Daily activity by category (hours)
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <button className="px-3 py-1.5 text-xs font-semibold bg-indigo-600 text-white rounded-lg">
            This Week
          </button>
          <button className="px-3 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-100 rounded-lg transition-colors">
            Last Month
          </button>
        </div>
      </div>
      <div className="h-56 sm:h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={activityTrendData}
            barGap={2}
            barCategoryGap="32%"
            margin={{ top: 0, right: 0, left: -8, bottom: 0 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="#F1F5F9"
              vertical={false}
            />
            <XAxis
              dataKey="day"
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 12, fill: "#94A3B8", fontWeight: 500 }}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 11, fill: "#CBD5E1" }}
              unit="h"
              width={28}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: "#F8FAFC" }} />
            <Legend
              iconType="circle"
              iconSize={7}
              formatter={(value) =>
                value.charAt(0).toUpperCase() + value.slice(1)
              }
              wrapperStyle={{
                paddingTop: "16px",
                fontSize: "12px",
                color: "#64748B",
              }}
            />
            <Bar
              dataKey="gaming"
              fill={COLORS.gaming}
              radius={[5, 5, 0, 0]}
              maxBarSize={18}
            />
            <Bar
              dataKey="education"
              fill={COLORS.education}
              radius={[5, 5, 0, 0]}
              maxBarSize={18}
            />
            <Bar
              dataKey="social"
              fill={COLORS.social}
              radius={[5, 5, 0, 0]}
              maxBarSize={18}
            />
            <Bar
              dataKey="video"
              fill={COLORS.video}
              radius={[5, 5, 0, 0]}
              maxBarSize={18}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
