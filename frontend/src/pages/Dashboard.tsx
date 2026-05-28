import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getDashboardStats } from "../api/client";
import type { DashboardStats } from "../api/types";
import StatCard from "../components/StatCard";

function fmtDate(s: string) {
  return new Date(s).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

const RUN_STATUS_STYLES: Record<string, string> = {
  done: "text-green-700 bg-green-50",
  failed: "text-red-700 bg-red-50",
  processing: "text-blue-700 bg-blue-50",
  pending: "text-gray-600 bg-gray-50",
};

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getDashboardStats()
      .then((r) => setStats(r.data))
      .catch(() => setError("Failed to load stats"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-8 text-gray-500">Loading…</div>;
  if (error) return <div className="p-8 text-red-600">{error}</div>;
  if (!stats) return null;

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-0.5">Overview of ingested emissions data</p>
      </div>

      {/* Status overview */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
        <StatCard label="Total Records" value={stats.total_records} />
        <StatCard label="Pending" value={stats.pending} color="yellow" />
        <StatCard label="Approved" value={stats.approved} color="green" />
        <StatCard label="Rejected" value={stats.rejected} color="red" />
        <StatCard label="Flagged" value={stats.flagged} color="orange" />
        <StatCard label="Anomalies" value={stats.anomaly_count} color={stats.anomaly_count > 0 ? "orange" : "default"} />
      </div>

      <div className="grid md:grid-cols-2 gap-6 mb-8">
        {/* Scope breakdown */}
        <div className="card p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">By Scope</h2>
          <div className="space-y-3">
            {Object.entries(stats.scope_breakdown).map(([scope, data]) => (
              <div key={scope}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="font-medium text-gray-700">{data.label}</span>
                  <span className="text-gray-500">{data.count}</span>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-brand-500 rounded-full"
                    style={{ width: stats.total_records ? `${(data.count / stats.total_records) * 100}%` : "0%" }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Category breakdown */}
        <div className="card p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">By Category</h2>
          <div className="space-y-2">
            {Object.entries(stats.category_breakdown).map(([cat, data]) => (
              <div key={cat} className="flex justify-between text-sm">
                <span className="text-gray-600">{data.label}</span>
                <span className="font-medium text-gray-900">{data.count}</span>
              </div>
            ))}
            {Object.keys(stats.category_breakdown).length === 0 && (
              <p className="text-sm text-gray-400">No records yet. <Link to="/ingest" className="text-brand-600 hover:underline">Upload data →</Link></p>
            )}
          </div>
        </div>
      </div>

      {/* Recent ingestion runs */}
      <div className="card">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700">Recent Ingestion Runs</h2>
          <Link to="/ingest" className="text-xs text-brand-600 hover:underline">Upload new →</Link>
        </div>
        {stats.recent_runs.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-gray-400">
            No ingestion runs yet.{" "}
            <Link to="/ingest" className="text-brand-600 hover:underline">Upload your first file →</Link>
          </div>
        ) : (
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="table-header">File</th>
                <th className="table-header">Source</th>
                <th className="table-header">Uploaded</th>
                <th className="table-header">Rows</th>
                <th className="table-header">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {stats.recent_runs.map((run) => (
                <tr key={run.id} className="hover:bg-gray-50">
                  <td className="table-cell font-mono text-xs">{run.original_filename}</td>
                  <td className="table-cell">{run.source_type}</td>
                  <td className="table-cell text-gray-500">{fmtDate(run.uploaded_at)}</td>
                  <td className="table-cell">
                    <span className="text-green-700">{run.rows_parsed}</span>
                    {run.rows_errored > 0 && (
                      <span className="text-red-600 ml-1">/ {run.rows_errored} err</span>
                    )}
                  </td>
                  <td className="table-cell">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${RUN_STATUS_STYLES[run.status] ?? ""}`}>
                      {run.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Quick actions */}
      <div className="mt-6 flex gap-3">
        <Link to="/review?status=pending" className="btn-primary">
          Review pending ({stats.pending})
        </Link>
        {stats.flagged > 0 && (
          <Link to="/review?status=flagged" className="btn-secondary">
            Review flagged ({stats.flagged})
          </Link>
        )}
        {stats.anomaly_count > 0 && (
          <Link to="/anomalies" className="btn-secondary">
            View anomalies ({stats.anomaly_count})
          </Link>
        )}
      </div>
    </div>
  );
}
