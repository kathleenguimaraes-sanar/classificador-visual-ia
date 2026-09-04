import type {
  AuthSession,
  ImportResult,
  Job,
  JWStatus,
  ServiceStatus,
  Video,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
let accessToken: string | null = null;

interface LoginResponse extends AuthSession {
  access_token?: string;
  token_type?: string;
  expires_in?: number;
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export function clearAccessToken() {
  accessToken = null;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const isFormData = init.body instanceof FormData;
  const requestAccessToken = accessToken;

  if (init.body && !isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (requestAccessToken && !path.endsWith("/auth/login")) {
    headers.set("Authorization", `Bearer ${requestAccessToken}`);
  }

  const response = await fetch(apiUrl(path), {
    ...init,
    headers,
  });

  let body: unknown = null;
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    body = await response.json();
  } else {
    body = await response.text();
  }

  if (!response.ok) {
    const detail =
      typeof body === "object" && body && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `A API respondeu com status ${response.status}.`;

    if (
      response.status === 401
      && !path.startsWith("/api/auth/")
      && accessToken === requestAccessToken
    ) {
      clearAccessToken();
      window.dispatchEvent(new Event("cetrus:unauthorized"));
    }

    throw new ApiError(detail, response.status);
  }

  return body as T;
}

export const backend = {
  session: () => api<AuthSession>("/api/auth/session"),
  login: async (username: string, password: string) => {
    clearAccessToken();
    const result = await api<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    accessToken = result.access_token ?? null;
    return {
      auth_enabled: result.auth_enabled,
      authenticated: result.authenticated,
      username: result.username,
    };
  },
  logout: async () => {
    try {
      return await api<AuthSession>("/api/auth/logout", { method: "POST" });
    } finally {
      clearAccessToken();
    }
  },
  status: () => api<ServiceStatus>("/api/status"),
  jwStatus: (library: string, propertyId: string, verify = false) =>
    api<JWStatus>(
      `/api/jw/status?${new URLSearchParams({
        library,
        property_id: propertyId,
        verify: String(verify),
      })}`,
    ),
  jwLogin: (payload: Record<string, string>) =>
    api<JWStatus>("/api/jw/login", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  switchLibrary: (library: string, propertyId: string) =>
    api<JWStatus>("/api/jw/switch-library", {
      method: "POST",
      body: JSON.stringify({ library, property_id: propertyId }),
    }),
  importSpreadsheet: (formData: FormData) =>
    api<ImportResult>("/api/import-and-process", {
      method: "POST",
      body: formData,
    }),
  startEligible: (payload: Record<string, unknown>) =>
    api<{ jobs: Job[]; media_count: number; message?: string }>(
      "/api/start-eligible",
      { method: "POST", body: JSON.stringify(payload) },
    ),
  analyzeOne: (payload: Record<string, unknown>) =>
    api<{ jobs: Job[]; message: string }>("/api/analyze-jwplayer", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  jobs: () => api<{ items: Job[] }>("/api/jobs"),
  videos: () => api<{ items: Video[]; total: number }>("/api/videos"),
  validate: (payload: {
    jwplayer_id: string;
    final_category: string;
    summary: string;
    validated: boolean;
  }) =>
    api<{ ok: boolean }>("/api/validate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

export async function downloadExport(format: "csv" | "xlsx", year = "") {
  const params = year ? `?year=${encodeURIComponent(year)}` : "";
  const requestAccessToken = accessToken;
  const headers = new Headers();
  if (requestAccessToken) headers.set("Authorization", `Bearer ${requestAccessToken}`);
  const response = await fetch(apiUrl(`/api/export.${format}${params}`), {
    headers,
  });

  if (!response.ok) {
    if (response.status === 401 && accessToken === requestAccessToken) {
      clearAccessToken();
      window.dispatchEvent(new Event("cetrus:unauthorized"));
    }
    throw new ApiError("Não foi possível gerar a exportação.", response.status);
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = `portfolio_cetrus.${format}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}
