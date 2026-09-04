import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./api", () => ({
  ApiError: class ApiError extends Error {
    status: number;

    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
  backend: {
    session: vi.fn().mockResolvedValue({
      auth_enabled: false,
      authenticated: true,
      username: "local",
    }),
    status: vi.fn().mockResolvedValue({
      gemini: true,
      claude: true,
      ollama_enabled: false,
      jw_agent: true,
    }),
    jwStatus: vi.fn().mockResolvedValue({ state: "disconnected" }),
    jobs: vi.fn().mockResolvedValue({ items: [] }),
    videos: vi.fn().mockResolvedValue({
      items: [{
        jwplayer_id: "Video123",
        lesson_name: "Aula de teste",
        status: "Concluído",
        final_category: "Teórica core",
        summary: "Resumo",
      }],
      total: 1,
    }),
  },
  downloadExport: vi.fn(),
}));

describe("validation dialog", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("traps focus and restores it to the review button", async () => {
    render(<App />);

    const resultTabs = await screen.findAllByRole("button", { name: /Resultados/ });
    fireEvent.click(resultTabs[0]);
    const trigger = await screen.findByRole("button", { name: "Revisar Aula de teste" });
    fireEvent.click(trigger);

    const dialog = screen.getByRole("dialog", { name: "Validar classificação" });
    const close = screen.getByRole("button", { name: "Fechar" });
    const save = screen.getByRole("button", { name: "Salvar validação" });
    expect(dialog).toBeInTheDocument();

    save.focus();
    fireEvent.keyDown(window, { key: "Tab" });
    expect(close).toHaveFocus();

    fireEvent.keyDown(window, { key: "Tab", shiftKey: true });
    expect(save).toHaveFocus();

    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });
});
