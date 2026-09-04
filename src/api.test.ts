import { afterEach, describe, expect, it, vi } from "vitest";
import { api, apiUrl } from "./api";

describe("api client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uses the configured API path", () => {
    expect(apiUrl("/api/status")).toMatch(/\/api\/status$/);
  });

  it("sends JSON requests with credentials", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await api("/api/example", {
      method: "POST",
      body: JSON.stringify({ value: 1 }),
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/example$/),
      expect.objectContaining({
        credentials: "include",
        method: "POST",
      }),
    );
    const request = fetchMock.mock.calls[0][1];
    expect(new Headers(request?.headers).get("Content-Type")).toBe(
      "application/json",
    );
  });

  it("exposes backend errors and announces expired sessions", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Sessão expirada." }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const listener = vi.fn();
    window.addEventListener("cetrus:unauthorized", listener);

    await expect(api("/api/status")).rejects.toMatchObject(
      {
        message: "Sessão expirada.",
        status: 401,
      },
    );
    expect(listener).toHaveBeenCalledOnce();

    window.removeEventListener("cetrus:unauthorized", listener);
  });
});
