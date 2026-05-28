import { useState, useEffect } from "react";
import { ingestFile, getIngestionRuns } from "../api/client";
import type { IngestionRun } from "../api/types";
import FileUpload from "../components/FileUpload";

type SourceKey = "sap" | "utility" | "travel";

const SOURCES: { key: SourceKey; label: string; accept: string; hint: string; description: string }[] = [
  {
    key: "sap",
    label: "SAP MB51 Export",
    accept: ".txt,.csv",
    hint: "Pipe-delimited flat file from SE16/MB51 transaction",
    description:
      "Pipe-delimited ALV export with SAP field names (MBLNR, BUDAT, BWART, WERKS, MENGE, MEINS). Handles German column names and YYYYMMDD or DD.MM.YYYY dates. Movement types 201, 261, 101, 501.",
  },
  {
    key: "utility",
    label: "Utility Portal CSV",
    accept: ".csv",
    hint: "CSV export from your utility provider's customer portal",
    description:
      "Standard portal CSV with account number, meter number, billing period start/end, kWh usage, peak demand. Billing periods do not have to align with calendar months.",
  },
  {
    key: "travel",
    label: "Concur / Navan Travel Export",
    accept: ".csv",
    hint: "CSV export from corporate travel management platform",
    description:
      "Concur or Navan trip export with segment type (AIR/HOTEL/CAR/RAIL), origin, destination, distance, and duration. Air segments with IATA airport codes but no distance will be flagged for great-circle calculation.",
  },
];

const RUN_STATUS_STYLES: Record<string, string> = {
  done: "text-green-700 bg-green-50",
  failed: "text-red-700 bg-red-50",
  processing: "text-blue-700 bg-blue-50",
  pending: "text-gray-600 bg-gray-50",
};

function fmtDate(s: string) {
  return new Date(s).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

export default function Ingest() {
  const [runs, setRuns] = useState<IngestionRun[]>([]);
  const [uploading, setUploading] = useState<SourceKey | null>(null);
  const [results, setResults] = useState<Record<SourceKey, { ok: boolean; msg: string } | null>>({
    sap: null, utility: null, travel: null,
  });

  async function loadRuns() {
    try {
      const r = await getIngestionRuns();
      setRuns(r.data);
    } catch {}
  }

  useEffect(() => { loadRuns(); }, []);

  async function handleFile(source: SourceKey, file: File) {
    setUploading(source);
    setResults((prev) => ({ ...prev, [source]: null }));
    try {
      const r = await ingestFile(source, file);
      const { rows_parsed, rows_errored, duplicate_warning } = r.data;
      let msg = `Ingested ${rows_parsed} records`;
      if (rows_errored > 0) msg += `, ${rows_errored} errors`;
      if (duplicate_warning) msg += ` — ${duplicate_warning}`;
      setResults((prev) => ({ ...prev, [source]: { ok: true, msg } }));
      loadRuns();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Upload failed";
      setResults((prev) => ({ ...prev, [source]: { ok: false, msg } }));
    } finally {
      setUploading(null);
    }
  }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Ingest Data</h1>
        <p className="text-sm text-gray-500 mt-0.5">Upload files from any of the three source types. Each upload creates an ingestion run with a full audit trail.</p>
      </div>

      <div className="space-y-5 mb-10">
        {SOURCES.map(({ key, label, accept, hint, description }) => (
          <div key={key} className="card p-5">
            <div className="flex items-start gap-4 mb-4">
              <div className="flex-1">
                <h2 className="text-sm font-semibold text-gray-900">{label}</h2>
                <p className="text-xs text-gray-500 mt-0.5">{description}</p>
              </div>
            </div>

            <FileUpload
              accept={accept}
              label={`Drop ${label} file here`}
              hint={hint}
              disabled={!!uploading}
              onFile={(f) => handleFile(key, f)}
            />

            {uploading === key && (
              <div className="mt-3 text-sm text-blue-600 flex items-center gap-2">
                <span className="animate-spin">⟳</span> Processing…
              </div>
            )}

            {results[key] && (
              <div className={`mt-3 text-sm px-3 py-2 rounded border ${results[key]!.ok ? "text-green-700 bg-green-50 border-green-200" : "text-red-700 bg-red-50 border-red-200"}`}>
                {results[key]!.ok ? "✓ " : "✗ "}
                {results[key]!.msg}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Ingestion history */}
      <div className="card">
        <div className="px-5 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700">Ingestion History</h2>
        </div>
        {runs.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-gray-400">No ingestion runs yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="table-header">File</th>
                  <th className="table-header">Source</th>
                  <th className="table-header">Uploaded</th>
                  <th className="table-header">Parsed</th>
                  <th className="table-header">Errors</th>
                  <th className="table-header">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {runs.map((run) => (
                  <tr key={run.id} className="hover:bg-gray-50">
                    <td className="table-cell font-mono text-xs max-w-xs truncate">{run.original_filename}</td>
                    <td className="table-cell">{run.source_type}</td>
                    <td className="table-cell text-gray-500 whitespace-nowrap">{fmtDate(run.uploaded_at)}</td>
                    <td className="table-cell text-green-700">{run.rows_parsed}</td>
                    <td className="table-cell text-red-600">{run.rows_errored || "—"}</td>
                    <td className="table-cell">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${RUN_STATUS_STYLES[run.status] ?? ""}`}>
                        {run.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
