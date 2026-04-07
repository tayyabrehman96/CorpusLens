"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  apiBaseDisplayLabel,
  apiUrl,
  deleteDocument,
  EvidenceChunk,
  EvidenceFigure,
  fetchDocuments,
  figureSrc,
  pdfHref,
  resetLibrary,
  uploadFile,
  type DocumentRow,
  type IngestProfile,
} from "@/lib/api";

const MODES = [
  { id: "default", label: "Default" },
  { id: "summary", label: "Summary" },
  { id: "limitations", label: "Limitations" },
  { id: "methodology", label: "Methodology" },
  { id: "compare", label: "Compare" },
  { id: "implementation", label: "Implementation" },
  { id: "future_work", label: "Future work" },
] as const;

type ModeId = (typeof MODES)[number]["id"];

type DetailLevel = "concise" | "balanced" | "deep";

const PDF_KIND_LABELS: Record<string, string> = {
  text_native: "Text-based PDF",
  scanned_or_image_heavy: "Scanned / image-heavy",
  low_text_mixed: "Mixed / low text",
  empty: "Empty PDF",
  image_upload: "Image file",
};

function profileBadge(p?: IngestProfile | null): string | null {
  if (!p?.pdf_kind) return null;
  return PDF_KIND_LABELS[p.pdf_kind] ?? p.pdf_kind;
}

function parseSseBlocks(buffer: string): { events: unknown[]; rest: string } {
  const events: unknown[] = [];
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  for (const block of parts) {
    const line = block.trim();
    if (!line.startsWith("data:")) continue;
    const json = line.slice(5).trim();
    try {
      events.push(JSON.parse(json));
    } catch {
      /* skip */
    }
  }
  return { events, rest };
}

export default function Dashboard() {
  const [docs, setDocs] = useState<DocumentRow[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [mode, setMode] = useState<ModeId>("default");
  const [input, setInput] = useState("");
  const [answer, setAnswer] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [confidence, setConfidence] = useState<number | null>(null);
  const [chunks, setChunks] = useState<EvidenceChunk[]>([]);
  const [figures, setFigures] = useState<EvidenceFigure[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [replaceOnUpload, setReplaceOnUpload] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [retrieveK, setRetrieveK] = useState(12);
  const [detailLevel, setDetailLevel] = useState<DetailLevel>("balanced");
  const [fastMode, setFastMode] = useState(false);

  const refreshDocs = useCallback(async () => {
    setLoadingDocs(true);
    try {
      const list = await fetchDocuments();
      setDocs(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load documents");
    } finally {
      setLoadingDocs(false);
    }
  }, []);

  useEffect(() => {
    refreshDocs();
  }, [refreshDocs]);

  useEffect(() => {
    const valid = new Set(docs.map((d) => d.id));
    setSelected((s) => {
      const next: Record<string, boolean> = {};
      for (const [id, on] of Object.entries(s)) {
        if (on && valid.has(id)) next[id] = true;
      }
      return next;
    });
  }, [docs]);

  const clearDocScope = () => setSelected({});

  const toggleDoc = (id: string) => {
    setSelected((s) => ({ ...s, [id]: !s[id] }));
  };

  const selectedIds = Object.entries(selected)
    .filter(([, v]) => v)
    .map(([k]) => k);

  const scopeIds =
    selectedIds.length === 0 ? null : selectedIds.length === docs.length ? null : selectedIds;

  const indexReady = useMemo(
    () =>
      docs.some(
        (d) => (d.chunk_count ?? 0) > 0 || (d.asset_count ?? 0) > 0,
      ),
    [docs],
  );

  const onUpload = async (files: FileList | null) => {
    if (!files?.length) return;
    const list = Array.from(files);
    const empty = list.find((f) => f.size === 0);
    if (empty) {
      setError(`“${empty.name}” is empty (0 bytes). Pick a real PDF or image.`);
      return;
    }
    setUploading(true);
    setError(null);
    try {
      for (let i = 0; i < list.length; i++) {
        await uploadFile(list[i], {
          replaceLibrary: replaceOnUpload && i === 0,
        });
      }
      setReplaceOnUpload(false);
      setSelected({});
      await refreshDocs();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const onResetLibrary = async () => {
    if (!window.confirm("Remove all documents, vectors, and stored files? This cannot be undone.")) {
      return;
    }
    setResetting(true);
    setError(null);
    try {
      await resetLibrary();
      setSelected({});
      setChunks([]);
      setFigures([]);
      setAnswer("");
      await refreshDocs();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reset failed");
    } finally {
      setResetting(false);
    }
  };

  const onDelete = async (id: string) => {
    try {
      await deleteDocument(id);
      setSelected((s) => {
        const n = { ...s };
        delete n[id];
        return n;
      });
      await refreshDocs();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  };

  const runChat = async () => {
    const msg = input.trim();
    if (!msg || streaming) return;
    setError(null);
    setStreaming(true);
    setAnswer("");
    setChunks([]);
    setFigures([]);
    setConfidence(null);

    let buf = "";
    try {
      const r = await fetch(apiUrl("/api/chat/stream"), {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "text/event-stream" },
        body: JSON.stringify({
          message: msg,
          document_ids: scopeIds,
          mode,
          retrieve_k: retrieveK,
          detail_level: detailLevel,
          fast_mode: fastMode,
        }),
      });
      if (!r.ok) {
        throw new Error(await r.text());
      }
      const reader = r.body?.getReader();
      if (!reader) throw new Error("No response body");
      const decoder = new TextDecoder();
      let acc = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const { events, rest } = parseSseBlocks(buf);
        buf = rest;
        for (const ev of events) {
          const e = ev as {
            type: string;
            content?: string;
            retrieval_confidence?: number;
            message?: string;
            evidence?: { chunks: EvidenceChunk[]; figures: EvidenceFigure[] };
          };
          if (e.type === "meta" && typeof e.retrieval_confidence === "number") {
            setConfidence(e.retrieval_confidence);
          }
          if (e.type === "token" && typeof (e as { content?: unknown }).content === "string") {
            acc += (e as { content: string }).content;
            setAnswer(acc);
          }
          if (e.type === "error") {
            setError(e.message || "LLM error");
          }
          if (e.type === "done" && e.evidence) {
            setChunks(e.evidence.chunks || []);
            setFigures(e.evidence.figures || []);
          }
        }
      }
      const { events } = parseSseBlocks(buf + "\n\n");
      for (const ev of events) {
        const e = ev as {
          type: string;
          evidence?: { chunks: EvidenceChunk[]; figures: EvidenceFigure[] };
        };
        if (e.type === "done" && e.evidence) {
          setChunks(e.evidence.chunks || []);
          setFigures(e.evidence.figures || []);
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setStreaming(false);
    }
  };

  const exportMd = async () => {
    try {
      const r = await fetch(apiUrl("/api/export/markdown"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: "Research Q&A export",
          answer,
          evidence_chunks: chunks,
          evidence_figures: figures,
        }),
      });
      if (!r.ok) throw new Error("Export failed");
      const text = await r.text();
      const blob = new Blob([text], { type: "text/markdown" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "research-notes.md";
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    }
  };

  return (
    <div className="relative min-h-screen bg-grid-faint bg-grid">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(ellipse_55%_45%_at_50%_120%,rgba(37,99,235,0.06),transparent)]" />

      <div className="relative mx-auto max-w-[1720px] px-4 pb-16 pt-10 sm:px-6 lg:px-10">
        <header className="mb-10 flex flex-col gap-6 border-b border-line pb-10 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-dim to-brand shadow-glow">
                <span className="font-display text-lg text-white">C</span>
              </div>
              <div>
                <p className="cl-label text-brand-muted">CorpusLens</p>
                <h1 className="font-display text-3xl tracking-tight text-ink sm:text-4xl">
                  Research console
                </h1>
              </div>
            </div>
            <p className="mt-4 text-sm leading-relaxed text-ink-muted">
              Hybrid retrieval over your PDFs and images — grounded answers, Markdown tables, and citations.
              Configure <code className="rounded-md border border-line bg-surface-raised px-1.5 py-0.5 font-mono text-xs text-brand-muted">NEXT_PUBLIC_API_URL</code> in{" "}
              <code className="rounded-md border border-line bg-surface-raised px-1.5 py-0.5 font-mono text-xs text-brand-muted">.env.local</code> if the API is not on{" "}
              <span className="font-mono text-ink-faint">{apiBaseDisplayLabel()}</span>.
            </p>
          </div>
          <div className="flex flex-wrap gap-2 lg:justify-end">
            <span className="rounded-full border border-line bg-surface-raised px-3 py-1 text-xs font-medium text-ink-muted">
              Local · private RAG
            </span>
            <span className="rounded-full border border-line bg-surface-raised px-3 py-1 text-xs font-medium text-ink-muted">
              BM25 + vectors
            </span>
          </div>
        </header>

        <div className="grid gap-6 xl:grid-cols-[minmax(280px,360px)_minmax(0,1fr)_minmax(280px,400px)]">
          <aside className="flex flex-col gap-5">
            <div className="cl-panel p-5">
              <p className="cl-label">Ingest</p>
              <h2 className="mt-1 text-base font-semibold text-ink">Library &amp; upload</h2>
              <p className="mt-2 text-xs leading-relaxed text-ink-muted">
                <span className="text-ink">PDF</span> (text or scanned) and{" "}
                <span className="text-ink">images</span>. Each file is profiled for text vs scan-heavy content.
              </p>
              <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-xl border border-line bg-surface-raised/60 p-3 text-xs text-ink-muted transition hover:border-lineStrong">
                <input
                  type="checkbox"
                  checked={replaceOnUpload}
                  onChange={(e) => setReplaceOnUpload(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-line bg-surface-solid text-brand focus:ring-brand/40"
                />
                <span>
                  <span className="font-semibold text-ink">Replace entire library</span> on this upload (first file
                  only in a batch). Removes prior docs, chunks, and vectors.
                </span>
              </label>
              <label className="cl-upload-zone mt-4">
                <input
                  type="file"
                  accept=".pdf,application/pdf,image/*"
                  multiple
                  className="hidden"
                  disabled={uploading}
                  onChange={(e) => {
                    const fl = e.target.files;
                    void onUpload(fl);
                    e.target.value = "";
                  }}
                />
                <span className="text-sm font-medium text-ink">
                  {uploading ? (
                    <span className="inline-flex items-center gap-2">
                      <span className="h-2 w-2 animate-pulse rounded-full bg-brand shadow-glow" />
                      Uploading…
                    </span>
                  ) : (
                    "Drop files or click to upload"
                  )}
                </span>
                <span className="mt-1 text-xs text-ink-faint">PDF · PNG · JPEG · WebP …</span>
              </label>
              <button
                type="button"
                onClick={() => onResetLibrary()}
                disabled={resetting || uploading}
                className="cl-btn-danger mt-4"
              >
                {resetting ? "Clearing…" : "Reset library"}
              </button>
            </div>

            <div className="cl-panel flex max-h-[min(52vh,640px)] flex-col p-5">
              <div className="flex shrink-0 items-center justify-between gap-2">
                <div>
                  <p className="cl-label">Sources</p>
                  <h2 className="mt-0.5 text-base font-semibold text-ink">Library</h2>
                </div>
                <button
                  type="button"
                  onClick={() => refreshDocs()}
                  className="rounded-lg border border-line px-2.5 py-1 text-xs font-medium text-brand-muted transition hover:border-brand/30 hover:bg-surface-hover"
                >
                  Refresh
                </button>
              </div>
              <div className="mt-4 min-h-0 flex-1 overflow-hidden">
                {loadingDocs ? (
                  <div className="flex items-center gap-2 text-sm text-ink-muted">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-brand" />
                    Loading…
                  </div>
                ) : docs.length === 0 ? (
                  <p className="text-sm leading-relaxed text-ink-muted">
                    No documents yet. Upload above — Q&amp;A unlocks once content is indexed.
                  </p>
                ) : (
                  <ul className="cl-scrollbar max-h-full space-y-2 overflow-y-auto pr-1 text-sm">
                    {docs.map((d) => (
                      <li
                        key={d.id}
                        className={`group flex gap-3 rounded-xl border p-3 transition ${
                          selected[d.id]
                            ? "border-brand/40 bg-blue-50/80 shadow-[0_0_0_1px_rgba(37,99,235,0.15)]"
                            : "border-line bg-surface-raised/40 hover:border-lineStrong hover:bg-surface-hover/60"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={!!selected[d.id]}
                          onChange={() => toggleDoc(d.id)}
                          className="mt-1 h-4 w-4 shrink-0 rounded border-line bg-surface-solid text-brand focus:ring-brand/40"
                          aria-label={`Scope ${d.title}`}
                        />
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-semibold text-ink">{d.title}</p>
                          <p className="truncate font-mono text-[11px] text-ink-faint">{d.original_filename}</p>
                          <p className="mt-1.5 font-mono text-[10px] text-ink-muted">
                            {(d.chunk_count ?? 0)} chunk{(d.chunk_count ?? 0) === 1 ? "" : "s"}
                            <span className="text-ink-faint"> · </span>
                            {(d.asset_count ?? 0)} asset{(d.asset_count ?? 0) === 1 ? "" : "s"}
                            {(d.chunk_count ?? 0) === 0 && (d.asset_count ?? 0) === 0 ? (
                              <span className="ml-1 text-amber-700">· not searchable</span>
                            ) : null}
                          </p>
                          {profileBadge(d.ingest_profile) && (
                            <p className="mt-1.5 text-[11px] text-ink-muted" title={d.ingest_profile?.hint ?? ""}>
                              <span className="rounded-md border border-line bg-surface-solid px-2 py-0.5 font-medium text-ink-muted">
                                {profileBadge(d.ingest_profile)}
                              </span>
                              {d.ingest_profile?.page_count != null ? (
                                <span className="ml-1.5 text-ink-faint">{d.ingest_profile.page_count} pp.</span>
                              ) : null}
                            </p>
                          )}
                          <div className="mt-2 flex flex-wrap gap-3 opacity-90 transition group-hover:opacity-100">
                            <a
                              href={pdfHref(d.id)}
                              target="_blank"
                              rel="noreferrer"
                              className="text-xs font-medium text-brand-muted hover:text-brand"
                            >
                              Open
                            </a>
                            <button
                              type="button"
                              onClick={() => onDelete(d.id)}
                              className="text-xs font-medium text-red-600 hover:text-red-700"
                            >
                              Remove
                            </button>
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="mt-4 shrink-0 space-y-2 border-t border-line pt-4 text-xs text-ink-faint">
                <p>
                  Checked items <span className="text-ink-muted">restrict</span> retrieval. Leave all off to use the
                  full library.
                </p>
                {scopeIds != null && scopeIds.length > 0 ? (
                  <button
                    type="button"
                    onClick={() => clearDocScope()}
                    className="font-semibold text-brand-muted hover:text-brand"
                  >
                    Clear scope → search everything
                  </button>
                ) : null}
              </div>
            </div>
          </aside>

          <main className="flex min-h-0 flex-col gap-5">
            {!loadingDocs && !indexReady && (
              <div
                className="cl-panel-solid border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-950"
                role="status"
              >
                <p className="font-semibold text-amber-900">Nothing searchable yet</p>
                <p className="mt-1.5 text-xs leading-relaxed text-amber-900/90">
                  Upload a real PDF (header <code className="rounded bg-amber-100 px-1 font-mono text-[11px] text-amber-950">%PDF</code>)
                  or an image. Failed uploads surface as errors instead of ghost rows. You should see chunk counts on
                  each library card when indexing succeeds.
                </p>
              </div>
            )}

            <div className="cl-panel p-5 lg:p-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="cl-label">Query</p>
                  <h2 className="mt-1 text-lg font-semibold text-ink">Ask your corpus</h2>
                </div>
                {confidence !== null && (
                  <div className="rounded-full border border-line bg-surface-raised px-3 py-1 font-mono text-xs text-brand-muted">
                    Match {(confidence * 100).toFixed(0)}%
                  </div>
                )}
              </div>

              <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <div>
                  <label className="cl-label">Answer mode</label>
                  <select
                    value={mode}
                    onChange={(e) => setMode(e.target.value as ModeId)}
                    className="cl-select mt-2"
                  >
                    {MODES.map((m) => (
                      <option key={m.id} value={m.id} className="bg-white text-slate-900">
                        {m.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="cl-label">
                    Context breadth · <span className="font-mono text-brand-muted">{retrieveK}</span>
                  </label>
                  <input
                    type="range"
                    min={4}
                    max={28}
                    step={1}
                    value={retrieveK}
                    onChange={(e) => setRetrieveK(Number(e.target.value))}
                    className="mt-4 h-1.5 w-full cursor-pointer appearance-none rounded-full bg-surface-raised accent-brand"
                  />
                </div>
                <div>
                  <label className="cl-label">Depth</label>
                  <select
                    value={detailLevel}
                    onChange={(e) => setDetailLevel(e.target.value as DetailLevel)}
                    className="cl-select mt-2"
                  >
                    <option value="concise" className="bg-white text-slate-900">
                      Concise
                    </option>
                    <option value="balanced" className="bg-white text-slate-900">
                      Balanced
                    </option>
                    <option value="deep" className="bg-white text-slate-900">
                      Deep · tables
                    </option>
                  </select>
                </div>
                <div className="flex flex-col justify-end">
                  <label className="flex cursor-pointer items-center gap-2.5 rounded-xl border border-line bg-surface-raised/50 px-3 py-2.5 text-xs text-ink-muted transition hover:border-lineStrong">
                    <input
                      type="checkbox"
                      checked={fastMode}
                      onChange={(e) => setFastMode(e.target.checked)}
                      className="h-4 w-4 rounded border-line bg-surface-solid text-brand focus:ring-brand/40"
                    />
                    <span>
                      <span className="font-semibold text-ink">Fast mode</span>
                      <span className="text-ink-faint"> — lean context, no figures</span>
                    </span>
                  </label>
                </div>
              </div>

              {scopeIds != null && scopeIds.length > 0 ? (
                <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-950">
                  <span className="font-semibold text-amber-900">Scoped:</span> only{" "}
                  {scopeIds.length === 1 ? "one checked source" : `${scopeIds.length} checked sources`}. Empty answers?
                  Clear checkboxes in the library.
                </p>
              ) : (
                <p className="mt-4 text-xs text-ink-faint">
                  Retrieving from the <span className="font-medium text-ink-muted">full library</span> — no scope
                  filters.
                </p>
              )}

              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="What does the evidence say about…"
                rows={4}
                className="cl-input mt-4 min-h-[120px] resize-y leading-relaxed"
              />

              <div className="mt-4 flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => runChat()}
                  disabled={streaming || !input.trim() || !indexReady}
                  title={
                    !indexReady
                      ? "Upload and index at least one PDF or image before asking questions."
                      : undefined
                  }
                  className="cl-btn-primary min-w-[120px]"
                >
                  {streaming ? (
                    <span className="inline-flex items-center gap-2">
                      <span className="h-2 w-2 animate-pulseSoft rounded-full bg-white/80" />
                      Generating…
                    </span>
                  ) : (
                    "Run query"
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => exportMd()}
                  disabled={!answer}
                  className="cl-btn-ghost"
                >
                  Export Markdown
                </button>
              </div>
              {error && (
                <p className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
                  {error}
                </p>
              )}
            </div>

            <div className="cl-panel flex min-h-[280px] flex-1 flex-col p-5 lg:p-6">
              <p className="cl-label">Synthesis</p>
              <h2 className="mt-1 text-lg font-semibold text-ink">Answer</h2>
              <div className="answer-md cl-scrollbar prose prose-sm prose-slate mt-4 max-w-none flex-1 overflow-y-auto pb-2 prose-headings:scroll-mt-4 prose-headings:font-semibold prose-headings:text-slate-900 prose-p:text-slate-700 prose-li:text-slate-700 prose-strong:text-slate-900 prose-a:text-brand prose-code:rounded-md prose-code:border prose-code:border-line prose-code:bg-slate-100 prose-code:px-1 prose-code:text-slate-800 prose-pre:bg-slate-100 prose-pre:text-slate-800 prose-th:border prose-th:border-line prose-td:border prose-td:border-line prose-table:text-sm">
                {answer ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
                ) : (
                  <p className="text-sm leading-relaxed text-ink-muted not-prose">
                    Streamed Markdown appears here — headings, lists, and pipe tables. LLM:{" "}
                    <code className="font-mono text-xs text-brand-muted">hf_local</code> (under{" "}
                    <code className="font-mono text-xs text-brand-muted">backend/data/hf_hub</code>) or{" "}
                    <code className="font-mono text-xs text-brand-muted">ollama</code> via{" "}
                    <code className="font-mono text-xs text-brand-muted">.env</code>.
                  </p>
                )}
              </div>
            </div>
          </main>

          <aside className="flex flex-col gap-5">
            <div className="cl-panel flex max-h-[min(42vh,520px)] flex-col p-5">
              <p className="cl-label">Provenance</p>
              <h2 className="mt-1 text-base font-semibold text-ink">Text evidence</h2>
              {chunks.length === 0 ? (
                <p className="mt-3 text-xs leading-relaxed text-ink-muted">
                  Retrieved passages and similarity scores show here after each answer.
                </p>
              ) : (
                <div className="cl-scrollbar mt-4 max-h-[min(34vh,420px)] overflow-auto rounded-xl border border-line">
                  <table className="w-full min-w-[260px] border-collapse text-left text-xs">
                    <thead className="sticky top-0 z-10 bg-surface-solid text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
                      <tr>
                        <th className="border-b border-line px-3 py-2.5">Source</th>
                        <th className="border-b border-line px-2 py-2.5">Pg</th>
                        <th className="border-b border-line px-2 py-2.5">Sim</th>
                      </tr>
                    </thead>
                    <tbody>
                      {chunks.map((c) => (
                        <tr
                          key={c.chunk_id}
                          className="border-b border-line/80 align-top transition hover:bg-surface-hover/50"
                        >
                          <td className="max-w-[140px] px-3 py-2 font-medium text-ink">{c.document_title}</td>
                          <td className="whitespace-nowrap px-2 py-2 font-mono text-ink-muted">
                            {c.page_start}
                            {c.page_end !== c.page_start ? `–${c.page_end}` : ""}
                          </td>
                          <td className="px-2 py-2 font-mono text-brand-muted">
                            {c.score != null ? `${(c.score * 100).toFixed(0)}%` : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <ul className="cl-scrollbar max-h-[22vh] space-y-2 overflow-y-auto border-t border-line p-3">
                    {chunks.map((c) => (
                      <li
                        key={`${c.chunk_id}-snip`}
                        className="rounded-lg border border-line/80 bg-surface-raised/40 p-3 text-xs text-ink-muted"
                      >
                        <p className="line-clamp-5 leading-relaxed">{c.text}</p>
                        <a
                          href={pdfHref(c.document_id)}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-2 inline-block text-xs font-medium text-brand-muted hover:text-brand"
                        >
                          Open source
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="cl-panel flex max-h-[min(48vh,560px)] flex-col p-5">
              <p className="cl-label">Visual</p>
              <h2 className="mt-1 text-base font-semibold text-ink">Figures</h2>
              {figures.length === 0 ? (
                <p className="mt-3 text-xs leading-relaxed text-ink-muted">
                  Ask about diagrams, charts, or figures — matching crops surface here when retrieval includes visuals.
                </p>
              ) : (
                <ul className="cl-scrollbar mt-4 max-h-[min(40vh,480px)] space-y-4 overflow-y-auto pr-1">
                  {figures.map((f) => (
                    <li
                      key={f.asset_id}
                      className="overflow-hidden rounded-xl border border-line bg-surface-raised/30 p-3"
                    >
                      <p className="text-xs font-semibold text-ink">
                        {f.document_title}{" "}
                        <span className="font-mono font-normal text-ink-faint">· p.{f.page}</span>
                      </p>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={figureSrc(f.image_url)}
                        alt={f.caption_text || "figure"}
                        className="mt-3 max-h-52 w-full rounded-lg object-contain ring-1 ring-line"
                      />
                      <p className="mt-2 text-xs text-ink-muted">{f.caption_text}</p>
                      <a
                        href={pdfHref(f.document_id)}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2 inline-block text-xs font-medium text-brand-muted hover:text-brand"
                      >
                        Open PDF
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
