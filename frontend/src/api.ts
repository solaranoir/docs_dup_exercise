import type { JSONContent } from "@tiptap/react";

export type Permission = "owner" | "editor" | "viewer";

export interface User {
  id: number;
  login_key: string;
  display_name: string;
}

export interface DocumentSummary {
  id: string;
  title: string;
  revision: number;
  owner: { id: number; display_name: string };
  permission: Permission;
  updated_at: string;
}

export interface DocumentFull extends DocumentSummary {
  content_json: JSONContent;
  created_at: string;
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
    throw new ApiError(res.status, Array.isArray(detail) ? detail.map((d) => d.msg).join("; ") : detail);
  }
  return data as T;
}

export const api = {
  me: () => request<User>("GET", "/api/me"),
  demoUsers: () => request<User[]>("GET", "/api/demo/users"),
  login: (login_key: string) => request<{ user: User }>("POST", "/api/demo/login", { login_key }),
  logout: () => request<void>("POST", "/api/demo/logout"),
  listDocuments: () => request<DocumentSummary[]>("GET", "/api/documents"),
  createDocument: (title?: string) =>
    request<DocumentFull>("POST", "/api/documents", title ? { title } : {}),
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
  grant: (id: string, user_id: number) =>
    request<Grant>("POST", `/api/documents/${id}/grants`, { user_id, role: "viewer" }),
  revoke: (id: string, user_id: number) =>
    request<void>("DELETE", `/api/documents/${id}/grants/${user_id}`),
};

function form(fields: Record<string, string | Blob>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.append(key, value);
  return data;
}
