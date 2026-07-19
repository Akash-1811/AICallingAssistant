import { useCallback, useEffect, useRef, useState } from "react";
import { formatTimestamp } from "../api/conversations";
import {
  deleteKnowledgeSource,
  listKnowledgeSources,
  syncAllKnowledge,
  syncKnowledgeSource,
  uploadKnowledgeFile,
  type KnowledgeSource,
} from "../api/knowledge";
import appStyles from "../App.module.css";
import styles from "./KnowledgeBasePage.module.css";

const STORAGE_LIMIT = 15 * 1024 * 1024;
const STATUS_LABEL = { ready: "Ready", processing: "Syncing…", failed: "Failed" } as const;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function KnowledgeBasePage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [totalBytes, setTotalBytes] = useState(0);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const data = await listKnowledgeSources();
    setSources(data.items);
    setTotalBytes(data.total_bytes);
    setLoading(false);
  }, []);

  useEffect(() => {
    void refresh().catch(() => setLoading(false));
  }, [refresh]);

  useEffect(() => {
    if (!sources.some((row) => row.status === "processing")) return;
    const timer = window.setInterval(() => void refresh().catch(() => undefined), 3000);
    return () => window.clearInterval(timer);
  }, [sources, refresh]);

  const run = useCallback(
    async (action: () => Promise<unknown>, fail = "Request failed") => {
      setNote(null);
      try {
        await action();
        await refresh();
      } catch (err) {
        setNote(err instanceof Error ? err.message : fail);
      }
    },
    [refresh],
  );

  const uploadFiles = useCallback(
    async (files: FileList | File[]) => {
      const list = Array.from(files);
      if (!list.length) return;
      setUploading(true);
      setNote(null);
      try {
        for (const file of list) await uploadKnowledgeFile(file);
        setNote(`Uploaded ${list.length} file${list.length > 1 ? "s" : ""}. Indexing in background.`);
        await refresh();
      } catch (err) {
        setNote(err instanceof Error ? err.message : "Upload failed");
      } finally {
        setUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [refresh],
  );

  const storagePct = Math.min(100, Math.round((totalBytes / STORAGE_LIMIT) * 100));
  const systemActive = sources.some((row) => row.status === "ready" || row.status === "processing");

  return (
    <div className={appStyles.content}>
      <div className={appStyles.mainCol}>
        <header className={styles.kbHero}>
          <div className={styles.kbHeroLeft}>
            <p className={styles.kbEyebrow}>Knowledge engine</p>
            <h1 className={styles.kbHeroTitle}>
              <span className={styles.kbHeroTitleDark}>Your team's </span>
              <span className={styles.kbHeroTitleAccent}>source of truth.</span>
            </h1>
            <p className={styles.kbHeroBody}>
              Upload pricing sheets, FAQs, and brochures. Live coaching and Ask AI will cite this content on calls.
            </p>
          </div>
          <div className={styles.kbHeroStatus}>
            <span className={styles.kbStatusLabel}>System status</span>
            <div className={styles.kbStatusRow}>
              <span className={styles.kbStatusDot} aria-hidden="true" data-active={systemActive} />
              <span>{systemActive ? "Knowledge active" : "Add your first document"}</span>
            </div>
          </div>
        </header>

        <section
          className={styles.kbDropzone}
          aria-label="Add documents"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            if (!uploading) void uploadFiles(event.dataTransfer.files);
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            className={styles.kbFileInput}
            accept=".pdf,.txt,.csv,.json,text/plain,text/csv,application/pdf,application/json"
            multiple
            tabIndex={-1}
            aria-hidden="true"
            onChange={(event) => {
              if (event.target.files) void uploadFiles(event.target.files);
            }}
          />
          <div className={styles.kbDropIcon} aria-hidden="true">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none">
              <path d="M7 18a4 4 0 0 1-1.76-7.58 5 5 0 0 1 9.52.58A3.5 3.5 0 0 1 17.5 18H7z" stroke="currentColor" strokeWidth="1.5" />
              <path d="M12 11v6M9 13l3-3 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </div>
          <h2 className={styles.kbDropTitle}>Add documents</h2>
          <p className={styles.kbDropHint}>Drop PDF, TXT, CSV, or JSON files here (max 15 MB each).</p>
          <button
            type="button"
            className={styles.kbBtnPrimary}
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? "Uploading…" : "Select files"}
          </button>
          {note ? <p className={styles.kbDropNote}>{note}</p> : null}
        </section>

        <section className={styles.kbLibrary}>
          <div className={styles.kbLibraryHead}>
            <h2 className={styles.kbLibraryTitle}>Document library</h2>
            <span className={styles.kbLibraryMeta}>
              {loading ? "Loading…" : `${sources.length} source${sources.length === 1 ? "" : "s"}`}
            </span>
          </div>
          <div className={styles.kbTableScroll}>
            {sources.length ? (
              <table className={styles.kbTable}>
                <thead>
                  <tr>
                    <th scope="col">Source name</th>
                    <th scope="col">Type</th>
                    <th scope="col">Last sync</th>
                    <th scope="col">Status</th>
                    <th scope="col" />
                  </tr>
                </thead>
                <tbody>
                  {sources.map((row) => (
                    <tr key={row.id}>
                      <td title={row.error || undefined}>{row.filename}</td>
                      <td>{row.file_type.toUpperCase()}</td>
                      <td>{formatTimestamp(row.synced_at || row.created_at)}</td>
                      <td>
                        <span
                          className={
                            row.status === "ready"
                              ? styles.kbBadgeOk
                              : row.status === "processing"
                                ? styles.kbBadgePending
                                : styles.kbBadgeFailed
                          }
                        >
                          {STATUS_LABEL[row.status]}
                        </span>
                      </td>
                      <td className={styles.kbActions}>
                        {row.status === "failed" ? (
                          <button
                            type="button"
                            className={styles.kbLinkBtn}
                            onClick={() => void run(() => syncKnowledgeSource(row.id), "Sync failed")}
                          >
                            Retry
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className={styles.kbLinkBtn}
                          onClick={() => void run(() => deleteKnowledgeSource(row.id), "Delete failed")}
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className={styles.kbEmpty}>No documents yet. Upload a file to train your assistant.</p>
            )}
          </div>
        </section>
      </div>

      <aside className={appStyles.rightPanel}>
        <div className={styles.syncCard}>
          <div className={styles.syncCardHead}>
            <RefreshIcon />
            <h3 className={styles.syncCardTitle}>Sync</h3>
          </div>
          <p className={styles.syncHint}>Re-index ready and failed documents for a fresh embedding pass.</p>
          <button
            type="button"
            className={styles.manualSyncBtn}
            disabled={busy}
            onClick={() => {
              setBusy(true);
              void run(async () => {
                const result = await syncAllKnowledge();
                setNote(
                  result.queued
                    ? `Re-syncing ${result.queued} document${result.queued > 1 ? "s" : ""}.`
                    : "Nothing to sync.",
                );
              }, "Sync failed").finally(() => setBusy(false));
            }}
          >
            <RefreshIcon />
            {busy ? "Queueing…" : "Re-sync all"}
          </button>
        </div>

        <div className={styles.storageCard}>
          <p className={styles.storageEyebrow}>Storage</p>
          <p className={styles.storagePct}>{storagePct}%</p>
          <div className={styles.storageTrack}>
            <div className={styles.storageFill} style={{ width: `${storagePct}%` }} />
          </div>
          <p className={styles.storageHint}>
            {formatBytes(totalBytes)} of {formatBytes(STORAGE_LIMIT)} used.
          </p>
        </div>
      </aside>
    </div>
  );
}

function RefreshIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M23 4v6h-6M1 20v-6h6" />
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
    </svg>
  );
}
