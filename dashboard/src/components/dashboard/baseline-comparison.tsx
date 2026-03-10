import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { baselineData } from "@/lib/mock-data";

type CategoryConfig = { bg: string; text: string; bar: string };

const categoryConfig: Record<string, CategoryConfig> = {
  Gaming: { bg: "bg-violet-100", text: "text-violet-600", bar: "bg-violet-400" },
  Education: { bg: "bg-sky-100", text: "text-sky-600", bar: "bg-sky-400" },
  Social: { bg: "bg-rose-100", text: "text-rose-600", bar: "bg-rose-400" },
  Video: { bg: "bg-amber-100", text: "text-amber-600", bar: "bg-amber-400" },
};

function getChangeColor(category: string, isIncrease: boolean) {
  if (category === "Education")
    return isIncrease ? "text-amber-500" : "text-emerald-600";
  return isIncrease ? "text-amber-600" : "text-emerald-600";
}

export default function BaselineComparison() {
  return (
    <div className="bg-white rounded-2xl p-5 lg:p-6 shadow-sm border border-slate-100">
      <div className="mb-5">
        <h3 className="text-base font-semibold text-slate-800">
          Baseline vs Current
        </h3>
        <p className="text-slate-400 text-sm">
          Compared to established behavior patterns
        </p>
      </div>

      <div className="space-y-3">
        {baselineData.map((item) => {
          const diff = item.current - item.baseline;
          const pct = Math.abs((diff / item.baseline) * 100).toFixed(0);
          const isIncrease = diff > 0;
          const isNeutral = diff === 0;
          const config = categoryConfig[item.category] ?? categoryConfig["Gaming"];
          const changeColor = getChangeColor(item.category, isIncrease);

          // Bar widths relative to 2× baseline as max
          const maxVal = item.baseline * 2;
          const currentWidth = Math.min((item.current / maxVal) * 100, 100);
          const baselinePos = Math.min((item.baseline / maxVal) * 100, 100);

          return (
            <div
              key={item.category}
              className="p-3.5 rounded-xl bg-slate-50 hover:bg-slate-100/60 transition-colors"
            >
              <div className="flex items-center justify-between mb-2.5">
                <div className="flex items-center gap-2.5">
                  <div
                    className={`w-7 h-7 rounded-lg ${config.bg} flex items-center justify-center flex-shrink-0`}
                  >
                    <span className={`text-[11px] font-bold ${config.text}`}>
                      {item.category[0]}
                    </span>
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-slate-700 leading-none">
                      {item.category}
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Baseline: {item.baseline} {item.unit}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm font-bold text-slate-800 leading-none">
                    {item.current} {item.unit}
                  </p>
                  <div
                    className={`flex items-center justify-end gap-0.5 text-xs font-semibold mt-0.5 ${
                      isNeutral ? "text-slate-400" : changeColor
                    }`}
                  >
                    {isNeutral ? (
                      <Minus className="w-3 h-3" />
                    ) : isIncrease ? (
                      <TrendingUp className="w-3 h-3" />
                    ) : (
                      <TrendingDown className="w-3 h-3" />
                    )}
                    {isNeutral ? "—" : `${isIncrease ? "+" : "-"}${pct}%`}
                  </div>
                </div>
              </div>

              {/* Progress bar */}
              <div className="relative h-1.5 bg-slate-200 rounded-full overflow-hidden">
                <div
                  className={`absolute left-0 top-0 h-full rounded-full ${config.bar} opacity-70 transition-all`}
                  style={{ width: `${currentWidth}%` }}
                />
              </div>
              {/* Baseline marker */}
              <div className="relative h-0">
                <div
                  className="absolute -top-2 w-0.5 h-3 bg-slate-400 rounded-full"
                  style={{ left: `${baselinePos}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
