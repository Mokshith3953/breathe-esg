import type { RecordStatus, Scope } from "../api/types";

const STATUS_STYLES: Record<RecordStatus, string> = {
  pending: "bg-yellow-50 text-yellow-800 border-yellow-200",
  approved: "bg-green-50 text-green-800 border-green-200",
  rejected: "bg-red-50 text-red-800 border-red-200",
  flagged: "bg-orange-50 text-orange-800 border-orange-200",
};

const STATUS_LABELS: Record<RecordStatus, string> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
  flagged: "Flagged",
};

export function StatusBadge({ status }: { status: RecordStatus }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${STATUS_STYLES[status]}`}>
      {STATUS_LABELS[status]}
    </span>
  );
}

const SCOPE_STYLES: Record<Scope, string> = {
  1: "bg-blue-50 text-blue-800 border-blue-200",
  2: "bg-purple-50 text-purple-800 border-purple-200",
  3: "bg-teal-50 text-teal-800 border-teal-200",
};

export function ScopeBadge({ scope }: { scope: Scope }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${SCOPE_STYLES[scope]}`}>
      Scope {scope}
    </span>
  );
}

const SEV_STYLES: Record<string, string> = {
  low: "bg-gray-50 text-gray-700 border-gray-200",
  medium: "bg-yellow-50 text-yellow-800 border-yellow-200",
  high: "bg-red-50 text-red-800 border-red-200",
};

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${SEV_STYLES[severity] ?? SEV_STYLES.low}`}>
      {severity}
    </span>
  );
}

const SOURCE_STYLES: Record<string, string> = {
  SAP: "bg-slate-50 text-slate-800 border-slate-200",
  UTILITY: "bg-sky-50 text-sky-800 border-sky-200",
  TRAVEL: "bg-violet-50 text-violet-800 border-violet-200",
};

const SOURCE_LABELS: Record<string, string> = {
  SAP: "SAP",
  UTILITY: "Utility",
  TRAVEL: "Travel",
};

export function SourceBadge({ source }: { source: string | null }) {
  if (!source) return null;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${SOURCE_STYLES[source] ?? "bg-gray-50 text-gray-700 border-gray-200"}`}>
      {SOURCE_LABELS[source] ?? source}
    </span>
  );
}
