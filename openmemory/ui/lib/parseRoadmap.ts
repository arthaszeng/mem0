export type ReleaseStatus = "completed" | "in_progress" | "upcoming";

export interface FeatureData {
  name: string;
  description: string;
  status: ReleaseStatus;
}

export interface ReleaseData {
  version: string;
  title: string;
  status: ReleaseStatus;
  date: string;
  icon: string;
  description: string;
  features: FeatureData[];
}

const STATUS_MAP: Record<string, ReleaseStatus> = {
  completed: "completed",
  in_progress: "in_progress",
  upcoming: "upcoming",
};

const CHECKBOX_STATUS: Record<string, ReleaseStatus> = {
  x: "completed",
  "-": "in_progress",
  " ": "upcoming",
};

const HEADER_RE = /^##\s+(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+)$/;
const FEATURE_RE = /^-\s+\[([ x\-])\]\s+\*\*(.+?)\*\*\s*[—–-]\s*(.+)$/;

export function parseRoadmap(markdown: string): ReleaseData[] {
  const releases: ReleaseData[] = [];
  const lines = markdown.split("\n");

  let current: ReleaseData | null = null;
  let needDescription = false;

  for (const line of lines) {
    const trimmed = line.trim();

    if (!trimmed || trimmed.startsWith("#") && !trimmed.startsWith("##") || trimmed.startsWith("<!--")) continue;

    const headerMatch = trimmed.match(HEADER_RE);
    if (headerMatch) {
      if (current) releases.push(current);
      const rawStatus = headerMatch[3].trim();
      current = {
        version: headerMatch[1].trim(),
        title: headerMatch[2].trim(),
        status: STATUS_MAP[rawStatus] ?? "upcoming",
        date: headerMatch[4].trim(),
        icon: headerMatch[5].trim(),
        description: "",
        features: [],
      };
      needDescription = true;
      continue;
    }

    if (current && needDescription && !trimmed.startsWith("-") && !trimmed.startsWith("<!--")) {
      current.description = trimmed;
      needDescription = false;
      continue;
    }

    if (current) {
      const featureMatch = trimmed.match(FEATURE_RE);
      if (featureMatch) {
        current.features.push({
          name: featureMatch[2].trim(),
          description: featureMatch[3].trim(),
          status: CHECKBOX_STATUS[featureMatch[1]] ?? "upcoming",
        });
      }
    }
  }

  if (current) releases.push(current);
  return releases;
}
