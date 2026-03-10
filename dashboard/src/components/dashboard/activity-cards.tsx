import {
  Gamepad2,
  BookOpen,
  MessageCircle,
  PlayCircle,
  TrendingUp,
  TrendingDown,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

type Activity = {
  id: string;
  label: string;
  hours: string;
  change: string;
  changeLabel: string;
  direction: "up" | "down";
  icon: LucideIcon;
  bg: string;
  border: string;
  iconBg: string;
  iconColor: string;
  changeColor: string;
};

const activities: Activity[] = [
  {
    id: "gaming",
    label: "Gaming",
    hours: "2.5 hrs",
    change: "+12%",
    changeLabel: "this week",
    direction: "up",
    icon: Gamepad2,
    bg: "bg-violet-50",
    border: "border-violet-100",
    iconBg: "bg-violet-100",
    iconColor: "text-violet-600",
    changeColor: "text-amber-600",
  },
  {
    id: "education",
    label: "Education",
    hours: "3.1 hrs",
    change: "-5%",
    changeLabel: "this week",
    direction: "down",
    icon: BookOpen,
    bg: "bg-sky-50",
    border: "border-sky-100",
    iconBg: "bg-sky-100",
    iconColor: "text-sky-600",
    changeColor: "text-emerald-600",
  },
  {
    id: "social",
    label: "Social",
    hours: "1.2 hrs",
    change: "+8%",
    changeLabel: "this week",
    direction: "up",
    icon: MessageCircle,
    bg: "bg-rose-50",
    border: "border-rose-100",
    iconBg: "bg-rose-100",
    iconColor: "text-rose-600",
    changeColor: "text-amber-600",
  },
  {
    id: "video",
    label: "Video",
    hours: "0.8 hrs",
    change: "+3%",
    changeLabel: "this week",
    direction: "up",
    icon: PlayCircle,
    bg: "bg-amber-50",
    border: "border-amber-100",
    iconBg: "bg-amber-100",
    iconColor: "text-amber-600",
    changeColor: "text-slate-500",
  },
];

export default function ActivityCards() {
  return (
    <div className="grid grid-cols-2 gap-3 h-full">
      {activities.map((activity) => {
        const Icon = activity.icon;
        const TrendIcon =
          activity.direction === "up" ? TrendingUp : TrendingDown;
        return (
          <div
            key={activity.id}
            className={`${activity.bg} border ${activity.border} rounded-2xl p-4 flex flex-col justify-between`}
          >
            <div
              className={`w-9 h-9 rounded-xl ${activity.iconBg} flex items-center justify-center mb-3`}
            >
              <Icon className={`w-4 h-4 ${activity.iconColor}`} />
            </div>
            <div>
              <p className="text-slate-500 text-xs font-medium mb-0.5">
                {activity.label} Activity
              </p>
              <p className="text-2xl font-bold text-slate-800 leading-none mb-1.5">
                {activity.hours}
              </p>
              <div
                className={`flex items-center gap-1 ${activity.changeColor} text-xs font-semibold`}
              >
                <TrendIcon className="w-3 h-3" />
                <span>
                  {activity.change} {activity.changeLabel}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
