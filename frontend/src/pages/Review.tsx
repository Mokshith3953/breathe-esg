import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import {
  getRecords, approveRecord, rejectRecord, flagRecord, bulkApprove, addNote,
} from "../api/client";
import type { ActivityRecord, RecordStatus, Category, Scope } from "../api/types";
import { CATEGORY_LABELS, SCOPE_LABELS } from "../api/types";
import { StatusBadge, ScopeBadge, SourceBadge } from "../components/Badge";

const PAGE_SIZE = 50;

function fmtDate(s: string) {
  return new Date(s).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function DetailPanel({ record, onClose, onAction }: {
  record: ActivityRecord;
  onClose: () => void;
  onAction: () => void;
}) {
  const [note, setNote] = useState(record.review_note ?? "");
  const [saving, setSaving] = useState(false);

  async function doAction(action: "approve" | "reject" | "flag") {
    setSaving(true);
    try {
      if (action === "approve") await approveRecord(record.id, note);
      if (action === "reject") await rejectRecord(record.id, note);
      if (action === "flag") await flagRecord(record.id, note);
      onAction();
      onClose();
    } finally { setSaving(false); }
  }

  async function saveNote() {
    setSaving(true);
    try { await addNote(record.id, note); } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-start justify-end" onClick={onClose}>
      <div className="bg-white w-full max-w-lg h-full overflow-y-auto shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <h3 className="font-semibold text-gray-900">Record #{record.id}</h3>
          <button onClick={onClose} className="btn-ghost text-lg">✕</button>
        </div>

        <div className="p-5 space-y-4">
          <div className="flex gap-2 flex-wrap">
            <StatusBadge status={record.status as RecordStatus} />
            <ScopeBadge scope={record.scope as Scope} />
            <SourceBadge source={record.source_type} />
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div><span className="text-gray-500">Category</span><p className="font-medium">{CATEGORY_LABELS[record.category as Category] ?? record.category}</p></div>
            <div><span className="text-gray-500">Period</span><p className="font-medium">{fmtDate(record.period_start)} – {fmtDate(record.period_end)}</p></div>
            <div><span className="text-gray-500">Original qty</span><p className="font-medium font-mono">{record.quantity_value} {record.quantity_unit}</p></div>
            <div><span className="text-gray-500">Normalised qty</span><p className="font-medium font-mono">{Number(record.normalized_value).toFixed(3)} {record.normalized_unit}</p></div>
            <div><span className="text-gray-500">Location</span><p className="font-medium">{record.location || "—"}</p></div>
            <div><span className="text-gray-500">Vendor</span><p className="font-medium">{record.vendor || "—"}</p></div>
          </div>

          {record.description && (
            <div className="text-sm">
              <span className="text-gray-500">Description</span>
              <p className="font-medium mt-0.5">{record.description}</p>
            </div>
          )}

          {/* Extra source-specific fields */}
          {Object.keys(record.extra ?? {}).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Source Data</p>
              <div className="bg-gray-50 rounded p-3 text-xs font-mono space-y-1">
                {Object.entries(record.extra).map(([k, v]) =>
                  v ? <div key={k}><span className="text-gray-400">{k}:</span> <span>{String(v)}</span></div> : null
                )}
              </div>
            </div>
          )}

          {/* Anomalies */}
          {(record.anomalies ?? []).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-orange-700 uppercase mb-2">Anomalies</p>
              <div className="space-y-2">
                {record.anomalies!.map((a) => (
                  <div key={a.id} className={`text-xs px-3 py-2 rounded border ${a.severity === "high" ? "bg-red-50 border-red-200 text-red-800" : a.severity === "medium" ? "bg-yellow-50 border-yellow-200 text-yellow-800" : "bg-gray-50 border-gray-200 text-gray-700"}`}>
                    <strong>{a.anomaly_type}</strong>: {a.message}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Review note */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Review note</label>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              className="input resize-none"
              placeholder="Add a note…"
            />
            <button onClick={saveNote} disabled={saving} className="mt-1 text-xs text-brand-600 hover:underline">
              Save note
            </button>
          </div>

          {/* Actions */}
          <div className="flex gap-2 pt-2 border-t">
            <button disabled={saving || record.status === "approved"} onClick={() => doAction("approve")} className="btn-primary">
              Approve
            </button>
            <button disabled={saving || record.status === "flagged"} onClick={() => doAction("flag")} className="btn-secondary">
              Flag
            </button>
            <button disabled={saving || record.status === "rejected"} onClick={() => doAction("reject")} className="btn-danger">
              Reject
            </button>
          </div>

          {/* Audit trail */}
          {(record.audit_trail ?? []).length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Audit Trail</p>
              <div className="space-y-1">
                {record.audit_trail!.map((e) => (
                  <div key={e.id} className="text-xs text-gray-600 flex gap-2">
                    <span className="text-gray-400 shrink-0">{new Date(e.timestamp).toLocaleString("en-GB")}</span>
                    <span><strong>{e.actor_name}</strong> {e.event}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Review() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [records, setRecords] = useState<ActivityRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [detail, setDetail] = useState<ActivityRecord | null>(null);
  const [bulking, setBulking] = useState(false);

  const statusFilter = searchParams.get("status") ?? "";
  const scopeFilter = searchParams.get("scope") ?? "";
  const sourceFilter = searchParams.get("source_type") ?? "";
  const page = Number(searchParams.get("page") ?? "1");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await getRecords({
        status: statusFilter || undefined,
        scope: scopeFilter || undefined,
        source_type: sourceFilter || undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setRecords(r.data.results);
      setTotal(r.data.count);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, scopeFilter, sourceFilter, page]);

  useEffect(() => { load(); }, [load]);

  function setParam(key: string, val: string) {
    const next = new URLSearchParams(searchParams);
    if (val) next.set(key, val); else next.delete(key);
    next.delete("page");
    setSearchParams(next);
  }

  function toggleSelect(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (selected.size === records.length) setSelected(new Set());
    else setSelected(new Set(records.map((r) => r.id)));
  }

  async function doBulkApprove() {
    if (selected.size === 0) return;
    setBulking(true);
    try {
      await bulkApprove([...selected]);
      setSelected(new Set());
      load();
    } finally { setBulking(false); }
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-gray-900">Review Queue</h1>
        <p className="text-sm text-gray-500 mt-0.5">{total} records — approve, reject, or flag before locking for audit</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-5">
        <select value={statusFilter} onChange={(e) => setParam("status", e.target.value)} className="select text-sm">
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="flagged">Flagged</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
        <select value={scopeFilter} onChange={(e) => setParam("scope", e.target.value)} className="select text-sm">
          <option value="">All scopes</option>
          <option value="1">Scope 1</option>
          <option value="2">Scope 2</option>
          <option value="3">Scope 3</option>
        </select>
        <select value={sourceFilter} onChange={(e) => setParam("source_type", e.target.value)} className="select text-sm">
          <option value="">All sources</option>
          <option value="SAP">SAP</option>
          <option value="UTILITY">Utility</option>
          <option value="TRAVEL">Travel</option>
        </select>

        {selected.size > 0 && (
          <button onClick={doBulkApprove} disabled={bulking} className="btn-primary ml-auto">
            Approve {selected.size} selected
          </button>
        )}
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="table-header w-10">
                  <input type="checkbox" checked={selected.size === records.length && records.length > 0} onChange={toggleAll} className="rounded" />
                </th>
                <th className="table-header">Period</th>
                <th className="table-header">Source</th>
                <th className="table-header">Scope</th>
                <th className="table-header">Category</th>
                <th className="table-header">Qty (normalised)</th>
                <th className="table-header">Location</th>
                <th className="table-header">Status</th>
                <th className="table-header">Flags</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading && (
                <tr><td colSpan={9} className="table-cell text-center text-gray-400 py-8">Loading…</td></tr>
              )}
              {!loading && records.length === 0 && (
                <tr><td colSpan={9} className="table-cell text-center text-gray-400 py-8">No records match these filters.</td></tr>
              )}
              {!loading && records.map((r) => (
                <tr
                  key={r.id}
                  className="hover:bg-gray-50 cursor-pointer"
                  onClick={() => setDetail(r)}
                >
                  <td className="table-cell" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selected.has(r.id)}
                      onChange={() => toggleSelect(r.id)}
                      className="rounded"
                    />
                  </td>
                  <td className="table-cell whitespace-nowrap">
                    <span className="text-xs">{fmtDate(r.period_start)}</span>
                  </td>
                  <td className="table-cell"><SourceBadge source={r.source_type} /></td>
                  <td className="table-cell"><ScopeBadge scope={r.scope as Scope} /></td>
                  <td className="table-cell text-xs">{CATEGORY_LABELS[r.category as Category] ?? r.category}</td>
                  <td className="table-cell font-mono text-xs">
                    {Number(r.normalized_value).toLocaleString("en", { maximumFractionDigits: 1 })} {r.normalized_unit}
                  </td>
                  <td className="table-cell text-xs max-w-xs truncate">{r.location || "—"}</td>
                  <td className="table-cell"><StatusBadge status={r.status as RecordStatus} /></td>
                  <td className="table-cell">
                    {(r.anomaly_count ?? 0) > 0 && (
                      <span className="text-xs font-medium text-orange-600">⚠ {r.anomaly_count}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-gray-100 text-sm">
            <span className="text-gray-500">
              {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total}
            </span>
            <div className="flex gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setParam("page", String(page - 1))}
                className="btn-secondary"
              >← Prev</button>
              <button
                disabled={page >= totalPages}
                onClick={() => setParam("page", String(page + 1))}
                className="btn-secondary"
              >Next →</button>
            </div>
          </div>
        )}
      </div>

      {detail && (
        <DetailPanel
          record={detail}
          onClose={() => setDetail(null)}
          onAction={load}
        />
      )}
    </div>
  );
}
