import { Wifi, MessageSquare, MapPin, RefreshCw, Plus } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { connectors } from "@/lib/mock-data";

const iconMap: Record<string, LucideIcon> = {
  "Network Activity": Wifi,
  "Discord Activity": MessageSquare,
  "Location Signals": MapPin,
};

export default function DataSources() {
  return (
    <div className="bg-white rounded-2xl p-5 lg:p-6 shadow-sm border border-slate-100">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="text-base font-semibold text-slate-800">
            Data Sources
          </h3>
          <p className="text-slate-400 text-sm">Connected monitors</p>
        </div>
        <button className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-400 transition-colors">
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      <div className="space-y-2.5">
        {connectors.map((connector) => {
          const Icon: LucideIcon = iconMap[connector.name] ?? Wifi;
          return (
            <div
              key={connector.name}
              className="flex items-center justify-between p-3 rounded-xl bg-slate-50 hover:bg-slate-100/60 transition-colors"
            >
              <div className="flex items-center gap-3">
                <div
                  className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 ${
                    connector.status === "active"
                      ? "bg-emerald-50"
                      : "bg-slate-100"
                  }`}
                >
                  <Icon
                    className={`w-4 h-4 ${
                      connector.status === "active"
                        ? "text-emerald-600"
                        : "text-slate-400"
                    }`}
                  />
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-700 leading-none">
                    {connector.name}
                  </p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Sync: {connector.lastSync}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                {connector.status === "active" && (
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                )}
                <span
                  className={`text-xs px-2.5 py-1 rounded-full font-semibold ${
                    connector.status === "active"
                      ? "bg-emerald-50 text-emerald-600"
                      : "bg-slate-100 text-slate-400"
                  }`}
                >
                  {connector.status === "active" ? "Active" : "Disabled"}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 pt-4 border-t border-slate-100">
        <button className="w-full py-2 text-sm text-indigo-600 font-semibold hover:bg-indigo-50 rounded-xl transition-colors flex items-center justify-center gap-1.5">
          <Plus className="w-4 h-4" />
          Add Data Source
        </button>
      </div>
    </div>
  );
}
