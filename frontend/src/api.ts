import type { JSONContent } from "@tiptap/react";

export type Permission = "owner" | "editor" | "viewer";

export interface User {
  id: number;
  display_name: string;
  email: string | null;
  login_key: string | null;
}

export interface AuthMethods {
  providers: { name: string; label: string }[];
  demo: boolean;
}

/** Seeded identity from the local/test-only demo switcher (ADR-004). */
export interface DemoUser extends User {
  login_key: string;
}

export interface DocumentSummary {
  id: string;
  title: string;
  revision: number;
  owner: { id: number; display_name: string };
  permission: Permission;
  created_at: string;
  updated_at: string;
  /** Set when the owner archived it (DOC-021): hidden from lists and read-only. */
  archived_at: string | null;
  /** When the signed-in user last opened it (DOC-022). */
  last_opened_at: string | null;
  /** The signed-in user's own folder and tags (ADR-010); nobody else sees them. */
  folder_id: number | null;
  tags: string[];
}

/** A built-in template (ADR-011): metadata and an outline for the picker's preview. */
export interface TemplateSummary {
  id: string;
  version: number;
  name: string;
  description: string;
  sections: { heading: string; fields: string[] }[];
}

/** A document in the owner's Trash (DOC-031, ADR-012). */
export interface TrashItem {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  deleted_at: string;
  /** When it will be removed for good. */
  purge_after: string;
}

export interface Folder {
  id: number;
  name: string;
  document_count: number;
}

export interface TagSummary {
  tags: { tag: string; count: number }[];
  suggestions: string[];
}

/** A search hit (DOC-017): plain text around the first body match, or the opening lines. */
export interface SearchResult extends DocumentSummary {
  snippet: string | null;
}

export interface DocumentFull extends DocumentSummary {
  content_json: JSONContent;
}

export interface ImportPreview {
  title: string;
  content_json: JSONContent;
  warnings: string[];
  source_name: string;
  source_type: string;
}

export interface Attachment {
  id: string;
  original_name: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
}

export interface Grant {
  user_id: number;
  display_name: string;
  email: string | null;
  role: string;
  created_at: string;
}

export type ImportMode = "append" | "replace";

/** Accepted upload types; must match backend/app/uploads.py. */
export const UPLOAD_ACCEPT = ".txt,.md,.markdown,.docx";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : ((detail as { message?: string })?.message ?? `HTTP ${status}`));
    this.status = status;
    this.detail = detail;
  }
}

// Empty base = same origin (Vite proxy locally, Render rewrite in production).
const BASE = import.meta.env.VITE_API_BASE_URL ?? "";

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  const res = await fetch(`${BASE}${path}`, {
    method,
    credentials: "include",
    headers: body === undefined || isForm ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  });
  if (res.status === 204) return undefined as T;
  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail ?? res.statusText;
    throw new ApiError(res.status, Array.isArray(detail) ? detail.map((d) => String(d.msg).replace(/^Value error, /, "")).join("; ") : detail);
  }
  return data as T;
}

/** ``filename*=UTF-8''…`` (preferred) or ``filename="…"`` from a Content-Disposition header. */
export function dispositionFilename(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1] ?? "");
    } catch {
      /* fall through to the ASCII name */
    }
  }
  return /filename="([^"]+)"/i.exec(header)?.[1] ?? fallback;
}

/** A file download through fetch, so errors (403, 429, 503…) surface as messages rather than
 * being saved as a file. */
async function download(
  path: string,
  fallback: string,
): Promise<{ blob: Blob; filename: string; headers: Headers }> {
  const res = await fetch(`${BASE}${path}`, { credentials: "include" });
  if (!res.ok) {
    const data: unknown = await res.json().catch(() => null);
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new ApiError(res.status, typeof detail === "string" ? detail : res.statusText);
  }
  return {
    blob: await res.blob(),
    filename: dispositionFilename(res.headers.get("Content-Disposition"), fallback),
    headers: res.headers,
  };
}

export const api = {
  me: () => request<User>("GET", "/api/me"),
  authMethods: () => request<AuthMethods>("GET", "/api/auth/methods"),
  signInUrl: (provider: string) => `${BASE}/api/auth/${encodeURIComponent(provider)}/start`,
  demoUsers: () => request<DemoUser[]>("GET", "/api/demo/users"),
  login: (login_key: string) => request<{ user: User }>("POST", "/api/demo/login", { login_key }),
  logout: () => request<void>("POST", "/api/auth/logout"),
  listDocuments: (archived = false) =>
    request<DocumentSummary[]>("GET", archived ? "/api/documents?archived=true" : "/api/documents"),
  /** Own and shared, unarchived documents matching every word; best first, at most 50. */
  searchDocuments: (q: string, filters: { folder?: string | null; tag?: string | null } = {}) => {
    const params = new URLSearchParams({ q });
    if (filters.folder) params.set("folder", filters.folder);
    if (filters.tag) params.set("tag", filters.tag);
    return request<SearchResult[]>("GET", `/api/documents/search?${params}`);
  },
  /** Moves the document to the Trash; restorable for 30 days. Owner only. */
  deleteDocument: (id: string) => request<void>("DELETE", `/api/documents/${id}`),
  listTrash: () => request<{ retention_days: number; items: TrashItem[] }>("GET", "/api/trash"),
  restoreFromTrash: (id: string) => request<TrashItem>("POST", `/api/trash/${id}/restore`),
  deleteForever: (id: string) => request<void>("DELETE", `/api/trash/${id}`),
  archiveDocument: (id: string) => request<DocumentFull>("POST", `/api/documents/${id}/archive`),
  restoreDocument: (id: string) => request<DocumentFull>("POST", `/api/documents/${id}/restore`),
  duplicateDocument: (id: string) => request<DocumentFull>("POST", `/api/documents/${id}/duplicate`),
  listFolders: () => request<Folder[]>("GET", "/api/folders"),
  createFolder: (name: string) => request<Folder>("POST", "/api/folders", { name }),
  renameFolder: (id: number, name: string) => request<Folder>("PATCH", `/api/folders/${id}`, { name }),
  deleteFolder: (id: number) => request<void>("DELETE", `/api/folders/${id}`),
  listTags: () => request<TagSummary>("GET", "/api/tags"),
  setFolder: (id: string, folderId: number | null) =>
    request<{ folder_id: number | null }>("PUT", `/api/documents/${id}/folder`, { folder_id: folderId }),
  setTags: (id: string, tags: string[]) =>
    request<{ tags: string[] }>("PUT", `/api/documents/${id}/tags`, { tags }),
  createDocument: (options: { title?: string; template?: string } = {}) =>
    request<DocumentFull>("POST", "/api/documents", options),
  listTemplates: () => request<TemplateSummary[]>("GET", "/api/templates"),
  /** Markdown: a .md, or a .zip with the document's attachments (DOC-028, DOC-030). */
  exportDocument: (id: string) => download(`/api/documents/${id}/export`, "document.md"),
  /** Every document the user owns, archived included, as one .zip (DOC-033). */
  exportAll: async () => {
    const file = await download("/api/export", "solara-docs-export.zip");
    // Attachments storage couldn't provide; listed in the archive's index.md.
    const missing = Number(file.headers.get("X-Export-Missing-Attachments") ?? 0) || 0;
    return { ...file, missing };
  },
  getDocument: (id: string) => request<DocumentFull>("GET", `/api/documents/${id}`),
  updateDocument: (
    id: string,
    body: { expected_revision: number; title?: string; content_json?: JSONContent },
  ) => request<DocumentFull>("PATCH", `/api/documents/${id}`, body),

  previewImport: (file: File) => request<ImportPreview>("POST", "/api/imports", form({ file })),
  createFromImport: (title: string, content_json: JSONContent) =>
    request<DocumentFull>("POST", "/api/documents", { title, content_json }),
  importInto: (id: string, file: File, mode: ImportMode, expected_revision: number) =>
    request<{ document: DocumentFull; warnings: string[] }>(
      "POST",
      `/api/documents/${id}/imports`,
      form({ file, mode, expected_revision: String(expected_revision) }),
    ),

  listAttachments: (id: string) => request<Attachment[]>("GET", `/api/documents/${id}/attachments`),
  uploadAttachment: (id: string, file: File) =>
    request<Attachment>("POST", `/api/documents/${id}/attachments`, form({ file })),
  deleteAttachment: (id: string, attachmentId: string) =>
    request<void>("DELETE", `/api/documents/${id}/attachments/${attachmentId}`),
  attachmentUrl: (id: string, attachmentId: string) =>
    `${BASE}/api/documents/${id}/attachments/${attachmentId}`,

  listGrants: (id: string) => request<Grant[]>("GET", `/api/documents/${id}/grants`),
  grant: (id: string, email: string) =>
    request<Grant>("POST", `/api/documents/${id}/grants`, { email, role: "viewer" }),
  revoke: (id: string, user_id: number) =>
    request<void>("DELETE", `/api/documents/${id}/grants/${user_id}`),
};

function form(fields: Record<string, string | Blob>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.append(key, value);
  return data;
}
