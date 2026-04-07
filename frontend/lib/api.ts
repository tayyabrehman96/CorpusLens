export const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_URL) ||
  "http://127.0.0.1:8000";

export function apiUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE.replace(/\/$/, "")}${p}`;
}

export type IngestProfile = {
  pdf_kind?: string;
  page_count?: number;
  text_char_estimate?: number;
  embedded_image_blocks?: number;
  chars_per_page_avg?: number;
  hint?: string;
};

export type DocumentRow = {
  id: string;
  title: string;
  original_filename: string;
  mime: string;
  created_at: string;
  chunk_count?: number;
  asset_count?: number;
  ingest_profile?: IngestProfile | null;
};

/** Readable message from FastAPI JSON error bodies. */
export function parseApiErrorText(body: string): string {
  const trimmed = body.trim();
  if (!trimmed) return "Request failed";
  try {
    const j = JSON.parse(trimmed) as { detail?: unknown };
    const d = j.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length > 0) {
      const first = d[0] as { msg?: string };
      if (typeof first?.msg === "string") return first.msg;
    }
  } catch {
    /* not JSON */
  }
  return trimmed;
}

export type EvidenceChunk = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  text: string;
  page_start: number;
  page_end: number;
  score?: number;
};

export type EvidenceFigure = {
  asset_id: string;
  document_id: string;
  document_title: string;
  page: number;
  caption_text: string;
  image_url: string;
  score?: number;
};

export async function fetchDocuments(): Promise<DocumentRow[]> {
  const r = await fetch(apiUrl("/api/documents"), { cache: "no-store" });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(parseApiErrorText(t) || "Failed to list documents");
  }
  return r.json();
}

export async function uploadFile(
  file: File,
  options?: { replaceLibrary?: boolean },
): Promise<DocumentRow> {
  const fd = new FormData();
  fd.append("file", file);
  const q =
    options?.replaceLibrary === true ? "?replace_library=true" : "";
  const r = await fetch(apiUrl(`/api/documents/upload${q}`), {
    method: "POST",
    body: fd,
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(parseApiErrorText(t) || "Upload failed");
  }
  return r.json();
}

export async function resetLibrary(): Promise<void> {
  const r = await fetch(apiUrl("/api/documents/library/reset"), {
    method: "POST",
  });
  if (!r.ok) throw new Error("Reset failed");
}

export async function deleteDocument(id: string): Promise<void> {
  const r = await fetch(apiUrl(`/api/documents/${id}`), { method: "DELETE" });
  if (!r.ok) throw new Error("Delete failed");
}

export function figureSrc(imageUrl: string): string {
  if (imageUrl.startsWith("http")) return imageUrl;
  return apiUrl(imageUrl);
}

export function pdfHref(documentId: string): string {
  return apiUrl(`/api/documents/${documentId}/file`);
}
