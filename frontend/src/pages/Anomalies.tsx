import { useState, useEffect, useCallback } from "react";
import { getAnomalies, resolveAnomaly } from "../api/client";
import type { Anomaly } from "../api/types";
import { SeverityBadge, SourceBadge } from "../components/Badge";

const TYPE_LABELS: Record<string, string> = {
  missing_field: "Missing Field",
  unknown_unit: "Unknown Unit",
  zero_qty: "Zero Quantity",
  outlier: "Outlier",
  duplicate: "Duplicate",
  parse_error: "Parse Error",
  unknown_code: "Unknown Code",
};

function fmtDate(s: string) {
  return new Date(s).toLocaleString("en-GB", { dateStyle: "short", timeStyle: "short" });
}

export default function Anomalies() {
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [severityFilter, setSeverityFilter] = useState("");
  const [showResolved, setShowResolved] = useState(false);
  const [sourceFilter, setSourceFilter] = useState("");
  const [resolving, setResolving] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await getAnomalies({
        severity: severityFilter || undefined,
        resolved: showResolved ? undefined : false,
        source_type: sourceFilter || undefined,
      });
      setAnomalies(r.data.results);
      setTotal(r.data.count);
    } finally {
      setLoading(false);
    }
  }, [severityFilter, showResolved, sourceFilter]);

  useEffect(() => { load(); }, [load]);

  async function handleResolve(id: number) {
    setResolving(id);
    try {
      await resolveAnomaly(id);
      load();
    } finally { setResolving(null); }
  }

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-gray-900">Anomalies</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Issues flagged during ingestion or normalisation. Resolve them once investigated.
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-5 items-center">
        <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)} className="select text-sm">
          <option value="">All severities</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)} className="select text-sm">
          <option value="">All sources</option>
          <option value="SAP">SAP</option>
          <option value="UTILITY">Utility</option>
          <option value="TRAVEL">Travel</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
          <input type="checkbox" checked={showResolved} onChange={(e) => setShowResolved(e.target.checked)} className="rounded" />
          Show resolved
        </label>
        <span className="ml-auto text-sm text-gray-500">{total} anomalies</span>
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="table-header">Severity</th>
                <th className="table-header">Type</th>
                <th className="table-header">Message</th>
                <th className="table-header">Run</th>
                <th className="table-header">Detected</th>
                <th className="table-header">Status</th>
                <th className="table-header"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading && (
                <tr><td colSpan={7} className="table-cell text-center text-gray-400 py-8">Loading…</td></tr>
              )}
              {!loading && anomalies.length === 0 && (
                <tr><td colSpan={7} className="table-cell text-center text-gray-400 py-8">No anomalies found.</td></tr>
              )}
              {!loading && anomalies.map((a) => (
                <tr key={a.id} className={`hover:bg-gray-50 ${a.resolved ? "opacity-50" : ""}`}>
                  <td className="table-cell"><SeverityBadge severity={a.severity} /></td>
                  <td className="table-cell text-xs font-medium text-gray-700">{TYPE_LABELS[a.anomaly_type] ?? a.anomaly_type}</td>
                  <td className="table-cell text-sm text-gray-700 max-w-sm">
                    <p>{a.message}</p>
                    {Object.keys(a.detail ?? {}).length > 0 && (
                      <details className="mt-1">
                        <summary className="text-xs text-gray-400 cursor-pointer">Details</summary>
                        <pre className="text-xs text-gray-500 mt-1 whitespace-pre-wrap">{JSON.stringify(a.detail, null, 2)}</pre>
                      </details>
                    )}
                  </td>
                  <td className="table-cell text-xs text-gray-500">#{a.run}</td>
                  <td className="table-cell text-xs text-gray-500 whitespace-nowrap">{fmtDate(a.created_at)}</td>
                  <td className="table-cell">
                    {a.resolved ? (
                      <span className="text-xs text-gray-400">Resolved</span>
                    ) : (
                      <span className="text-xs text-orange-600 font-medium">Open</span>
                    )}
                  </td>
                  <td className="table-cell">
                    {!a.resolved && (
                      <button
                        onClick={() => handleResolve(a.id)}
                        disabled={resolving === a.id}
                        className="btn-ghost text-xs"
                      >
                        {resolving === a.id ? "…" : "Resolve"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
