import axios from "axios";
import type {
  User, DashboardStats, IngestionRun, RecordListResponse,
  ActivityRecord, Anomaly,
} from "./types";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "/api",
  headers: { "Content-Type": "application/json" },
});

// Attach token from localStorage to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("auth_token");
  if (token) {
    config.headers.Authorization = `Token ${token}`;
  }
  return config;
});

// Redirect to login on 401
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("auth_token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

// Auth
export const login = (username: string, password: string) =>
  api.post<{ token: string; user: User }>("/auth/login/", { username, password });

export const logout = () => api.post("/auth/logout/");
export const getMe = () => api.get<User>("/auth/me/");

// Dashboard
export const getDashboardStats = () => api.get<DashboardStats>("/dashboard/stats/");

// Ingestion
export const ingestFile = (source: "sap" | "utility" | "travel", file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post<{ run_id: number; rows_parsed: number; rows_errored: number; duplicate_warning?: string }>(
    `/ingest/${source}/`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
};

export const getIngestionRuns = (sourceType?: string) =>
  api.get<IngestionRun[]>("/ingestion-runs/", { params: sourceType ? { source_type: sourceType } : {} });

// Records
export interface RecordFilters {
  status?: string;
  scope?: string;
  category?: string;
  source_type?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  page_size?: number;
}

export const getRecords = (filters: RecordFilters = {}) =>
  api.get<RecordListResponse>("/records/", { params: filters });

export const getRecord = (id: number) => api.get<ActivityRecord>(`/records/${id}/`);

export const approveRecord = (id: number, note?: string) =>
  api.post<ActivityRecord>(`/records/${id}/approve/`, { note });

export const rejectRecord = (id: number, note?: string) =>
  api.post<ActivityRecord>(`/records/${id}/reject/`, { note });

export const flagRecord = (id: number, note?: string) =>
  api.post<ActivityRecord>(`/records/${id}/flag/`, { note });

export const addNote = (id: number, note: string) =>
  api.patch(`/records/${id}/note/`, { review_note: note });

export const bulkApprove = (ids: number[]) =>
  api.post<{ approved: number }>("/records/bulk-approve/", { ids });

// Anomalies
export interface AnomalyFilters {
  severity?: string;
  resolved?: boolean;
  source_type?: string;
  page?: number;
}

export const getAnomalies = (filters: AnomalyFilters = {}) =>
  api.get<{ count: number; results: Anomaly[] }>("/anomalies/", { params: filters });

export const resolveAnomaly = (id: number) =>
  api.post(`/anomalies/${id}/resolve/`);
