export interface User {
  id: number;
  username: string;
  name: string;
  email: string;
}

export interface Tenant {
  id: number;
  name: string;
  slug: string;
}

export type SourceType = "SAP" | "UTILITY" | "TRAVEL";
export type RecordStatus = "pending" | "approved" | "rejected" | "flagged";
export type Scope = 1 | 2 | 3;
export type Category =
  | "fuel_combustion"
  | "electricity"
  | "travel_air"
  | "travel_hotel"
  | "travel_ground"
  | "procurement";

export const CATEGORY_LABELS: Record<Category, string> = {
  fuel_combustion: "Fuel Combustion",
  electricity: "Purchased Electricity",
  travel_air: "Business Travel – Air",
  travel_hotel: "Business Travel – Hotel",
  travel_ground: "Business Travel – Ground",
  procurement: "Purchased Goods & Services",
};

export const SCOPE_LABELS: Record<Scope, string> = {
  1: "Scope 1",
  2: "Scope 2",
  3: "Scope 3",
};

export const SOURCE_LABELS: Record<SourceType, string> = {
  SAP: "SAP Fuel & Procurement",
  UTILITY: "Utility Electricity",
  TRAVEL: "Corporate Travel",
};

export interface IngestionRun {
  id: number;
  data_source: number;
  data_source_name: string;
  source_type: SourceType;
  uploaded_by: number | null;
  uploaded_by_name: string | null;
  uploaded_at: string;
  original_filename: string;
  file_hash: string;
  status: "pending" | "processing" | "done" | "failed";
  rows_parsed: number;
  rows_errored: number;
  error_log: { row: number; message: string }[];
}

export interface AuditEvent {
  id: number;
  event: string;
  actor: number | null;
  actor_name: string;
  timestamp: string;
  diff: Record<string, unknown>;
}

export interface Anomaly {
  id: number;
  run: number;
  raw_record: number | null;
  activity_record: number | null;
  anomaly_type: string;
  severity: "low" | "medium" | "high";
  message: string;
  detail: Record<string, unknown>;
  resolved: boolean;
  created_at: string;
}

export interface ActivityRecord {
  id: number;
  tenant: number;
  scope: Scope;
  category: Category;
  period_start: string;
  period_end: string;
  quantity_value: string;
  quantity_unit: string;
  normalized_value: string;
  normalized_unit: string;
  location: string;
  vendor: string;
  description: string;
  extra: Record<string, unknown>;
  status: RecordStatus;
  review_note: string;
  reviewed_by: number | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  is_edited: boolean;
  created_at: string;
  updated_at: string;
  source_type: SourceType | null;
  anomaly_count?: number;
  audit_trail?: AuditEvent[];
  anomalies?: Anomaly[];
}

export interface RecordListResponse {
  count: number;
  page: number;
  page_size: number;
  results: ActivityRecord[];
}

export interface DashboardStats {
  total_records: number;
  pending: number;
  approved: number;
  rejected: number;
  flagged: number;
  anomaly_count: number;
  scope_breakdown: Record<string, { label: string; count: number }>;
  category_breakdown: Record<string, { label: string; count: number }>;
  recent_runs: IngestionRun[];
}
