import { afterEach, describe, expect, it, vi } from "vitest";
import {
  api,
  apiUrl,
  backend,
  clearAccessToken,
  downloadExport,
} from "./api";

describe("api client", () => {
  afterEach(() => {
    clearAccessToken();
    vi.restoreAllMocks();
  });

  it("uses the configured API path", () => {
    expect(apiUrl("/api/status")).toMatch(/\/api\/status$/);
  });

  it("sends JSON requests without browser credentials", async () => {
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
        method: "POST",
      }),
    );
    expect(fetchMock.mock.calls[0][1]).not.toHaveProperty("credentials");
    const request = fetchMock.mock.calls[0][1];
    expect(new Headers(request?.headers).get("Content-Type")).toBe(
      "application/json",
    );
  });

  it("stores the login token in memory and sends it as Bearer", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        auth_enabled: true,
        authenticated: true,
        username: "operador",
        access_token: "signed-token",
        token_type: "Bearer",
        expires_in: 3600,
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));

    const session = await backend.login("operador", "senha");
    await api("/api/status");

    expect(session).toEqual({
      auth_enabled: true,
      authenticated: true,
      username: "operador",
    });
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get("Authorization")).toBeNull();
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get("Authorization")).toBe(
      "Bearer signed-token",
    );
  });

  it("sends the Bearer token when downloading exports", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        auth_enabled: true,
        authenticated: true,
        username: "operador",
        access_token: "download-token",
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }))
      .mockResolvedValueOnce(new Response("csv", { status: 200 }));
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:test");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    await backend.login("operador", "senha");
    await downloadExport("csv");

    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get("Authorization")).toBe(
      "Bearer download-token",
    );
  });

  it("exposes backend errors and announces expired sessions", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        auth_enabled: true,
        authenticated: true,
        username: "operador",
        access_token: "expired-token",
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Sessão expirada." }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        auth_enabled: true,
        authenticated: false,
        username: "",
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));
    const listener = vi.fn();
    window.addEventListener("cetrus:unauthorized", listener);

    await backend.login("operador", "senha");
    await expect(api("/api/status")).rejects.toMatchObject(
      {
        message: "Sessão expirada.",
        status: 401,
      },
    );
    expect(listener).toHaveBeenCalledOnce();
    await backend.session();
    expect(new Headers(fetchMock.mock.calls[2][1]?.headers).get("Authorization")).toBeNull();

    window.removeEventListener("cetrus:unauthorized", listener);
  });

  it("does not let a stale 401 clear a newly issued token", async () => {
    let resolveStaleRequest: ((response: Response) => void) | undefined;
    const staleResponse = new Promise<Response>((resolve) => {
      resolveStaleRequest = resolve;
    });
    const loginResponse = (token: string) => new Response(JSON.stringify({
      auth_enabled: true,
      authenticated: true,
      username: "operador",
      access_token: token,
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(loginResponse("old-token"))
      .mockReturnValueOnce(staleResponse)
      .mockResolvedValueOnce(loginResponse("new-token"))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));
    const listener = vi.fn();
    window.addEventListener("cetrus:unauthorized", listener);

    await backend.login("operador", "senha");
    const staleRequest = api("/api/status");
    await backend.login("operador", "senha");
    resolveStaleRequest?.(new Response(JSON.stringify({ detail: "Expirado" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    }));
    await expect(staleRequest).rejects.toMatchObject({ status: 401 });
    await api("/api/status");

    expect(listener).not.toHaveBeenCalled();
    expect(new Headers(fetchMock.mock.calls[3][1]?.headers).get("Authorization")).toBe(
      "Bearer new-token",
    );
    window.removeEventListener("cetrus:unauthorized", listener);
  });
});
