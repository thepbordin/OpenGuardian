export const behaviorScoreData = [
  { day: "Mon", score: 82 },
  { day: "Tue", score: 85 },
  { day: "Wed", score: 88 },
  { day: "Thu", score: 84 },
  { day: "Fri", score: 79 },
  { day: "Sat", score: 75 },
  { day: "Sun", score: 85 },
];

export const activityTrendData = [
  { day: "Mon", gaming: 1.2, education: 3.5, social: 0.8, video: 0.5 },
  { day: "Tue", gaming: 2.0, education: 3.2, social: 1.0, video: 0.8 },
  { day: "Wed", gaming: 1.5, education: 4.0, social: 1.2, video: 0.6 },
  { day: "Thu", gaming: 2.5, education: 2.8, social: 0.9, video: 1.2 },
  { day: "Fri", gaming: 3.0, education: 2.5, social: 1.5, video: 1.0 },
  { day: "Sat", gaming: 4.2, education: 1.0, social: 2.0, video: 1.5 },
  { day: "Sun", gaming: 3.8, education: 0.8, social: 1.8, video: 0.8 },
];

export const baselineData = [
  { category: "Gaming", baseline: 1.0, current: 4.2, unit: "hrs/day" },
  { category: "Education", baseline: 3.5, current: 3.1, unit: "hrs/day" },
  { category: "Social", baseline: 0.8, current: 1.2, unit: "hrs/day" },
  { category: "Video", baseline: 0.5, current: 0.8, unit: "hrs/day" },
];

export const alerts = [
  {
    id: 1,
    title: "Late-night activity detected",
    description:
      "Social activity occurred at 2:14 AM outside typical usage hours.",
    severity: "warning" as const,
    time: "2 hours ago",
  },
  {
    id: 2,
    title: "Possible grooming pattern detected",
    description:
      "Gaming activity followed by a new messaging contact outside known network.",
    severity: "critical" as const,
    time: "5 hours ago",
  },
  {
    id: 3,
    title: "Unusual gaming session length",
    description:
      "Continuous gaming session exceeded 4 hours — significantly above baseline.",
    severity: "warning" as const,
    time: "Yesterday",
  },
];

export const connectors = [
  {
    name: "Network Activity",
    status: "active" as const,
    lastSync: "2 min ago",
  },
  {
    name: "Discord Activity",
    status: "active" as const,
    lastSync: "15 min ago",
  },
  {
    name: "Location Signals",
    status: "disabled" as const,
    lastSync: "N/A",
  },
];
