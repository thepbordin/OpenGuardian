import { AlertTriangle, AlertCircle, ChevronRight } from "lucide-react";
import { alerts } from "@/lib/mock-data";

export default function RecentAlerts() {
  return (
    <div className="bg-white rounded-2xl p-5 lg:p-6 shadow-sm border border-slate-100">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="text-base font-semibold text-slate-800">
            Recent Alerts
          </h3>
          <p className="text-slate-400 text-sm">
            Behavioral pattern notifications
          </p>
        </div>
        <button className="text-xs text-indigo-600 font-semibold hover:text-indigo-700 transition-colors">
          View all
        </button>
      </div>

      <div className="space-y-3">
        {alerts.map((alert) => (
          <div
            key={alert.id}
            className={`p-4 rounded-xl border ${
              alert.severity === "critical"
                ? "bg-red-50 border-red-100"
                : "bg-amber-50 border-amber-100"
            }`}
          >
            <div className="flex items-start gap-3">
              <div
                className={`mt-0.5 flex-shrink-0 ${
                  alert.severity === "critical"
                    ? "text-red-500"
                    : "text-amber-500"
                }`}
              >
                {alert.severity === "critical" ? (
                  <AlertCircle className="w-4 h-4" />
                ) : (
                  <AlertTriangle className="w-4 h-4" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-semibold text-slate-800 leading-snug">
                    {alert.title}
                  </p>
                  <span
                    className={`flex-shrink-0 text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wide ${
                      alert.severity === "critical"
                        ? "bg-red-100 text-red-600"
                        : "bg-amber-100 text-amber-600"
                    }`}
                  >
                    {alert.severity}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                  {alert.description}
                </p>
                <div className="flex items-center justify-between mt-2.5">
                  <span className="text-xs text-slate-400">{alert.time}</span>
                  <button className="text-xs text-indigo-600 font-semibold flex items-center gap-0.5 hover:text-indigo-700 transition-colors group">
                    View details
                    <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
