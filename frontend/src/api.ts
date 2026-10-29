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
  const res = await fetch(`${BASE}${path}`, {
    method,
    credentials: "include",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
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
};
