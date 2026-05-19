import { describe, it, expect, vi, beforeEach } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ForgotPasswordClient from "@/app/forgot-password/ForgotPasswordClient";
import ResetPasswordClient from "@/app/reset-password/ResetPasswordClient";
import { fetchWithCsrf } from "@/lib/fetch-with-csrf";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";

const mockPush = vi.fn();
const mockSearchParamGet = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => ({ get: mockSearchParamGet }),
}));

vi.mock("@/lib/fetch-with-csrf", () => ({
  fetchWithCsrf: vi.fn(),
}));

vi.mock("@/lib/supabase/client", () => ({
  createSupabaseBrowserClient: vi.fn(),
}));

describe("password reset auth clients", () => {
  const mockGetSession = vi.fn();
  const mockSignOut = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState(null, "", "/");
    mockSearchParamGet.mockReturnValue(null);
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: "recovery-token" } },
    });
    mockSignOut.mockResolvedValue({ error: null });
    (createSupabaseBrowserClient as any).mockReturnValue({
      auth: {
        getSession: mockGetSession,
        signOut: mockSignOut,
      },
    });
    (fetchWithCsrf as any).mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({}),
    });
  });

  it("submits forgot-password requests through the admin API and shows generic success copy", async () => {
    const user = userEvent.setup();
    render(<ForgotPasswordClient />);

    expect(
      screen.getByRole("heading", { level: 1, name: /reset your password/i }),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText(/email/i), " user@example.com ");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    await waitFor(() => {
      expect(fetchWithCsrf).toHaveBeenCalledWith(
        "/api/admin/auth/forgot-password",
        expect.objectContaining({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: "user@example.com" }),
        }),
      );
    });
    expect(
      screen.getByText(
        (_content, element) =>
          element?.textContent ===
          "If user@example.com is registered, you'll receive a reset link within a minute.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/check your inbox/i);
  });

  it("keeps password-reset admin proxy endpoints available before login", () => {
    const source = readFileSync(
      join(process.cwd(), "src/app/api/admin/[...path]/route.ts"),
      "utf-8",
    );

    expect(source).toContain("'auth/forgot-password'");
    expect(source).toContain("'auth/reset-password'");
  });

  it("shows a generic forgot-password failure when the admin API fails", async () => {
    const user = userEvent.setup();
    (fetchWithCsrf as any).mockResolvedValueOnce({
      ok: false,
      json: vi.fn().mockResolvedValue({ detail: "User not found" }),
    });

    render(<ForgotPasswordClient />);

    await user.type(screen.getByLabelText(/email/i), "missing@example.com");
    await user.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Failed to send reset email. Please try again.",
    );
    expect(screen.queryByText(/user not found/i)).not.toBeInTheDocument();
  });

  it("announces expired forgot-password links as alerts", () => {
    mockSearchParamGet.mockImplementation((key: string) =>
      key === "error" ? "link_expired" : null,
    );

    render(<ForgotPasswordClient />);

    expect(screen.getByRole("alert")).toHaveTextContent(
      /your reset link has expired/i,
    );
  });

  it("lets the reset backend enforce password policy and surfaces detail messages", async () => {
    const user = userEvent.setup();
    (fetchWithCsrf as any).mockResolvedValueOnce({
      ok: false,
      json: vi
        .fn()
        .mockResolvedValue({ detail: "Password must include a symbol." }),
    });

    render(<ResetPasswordClient />);

    expect(
      screen.getByRole("heading", { level: 1, name: /set new password/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      /checking reset session/i,
    );
    await screen.findByRole("button", { name: /update password/i });
    await user.type(screen.getByLabelText(/^new password$/i), "short");
    await user.type(screen.getByLabelText(/confirm new password/i), "short");
    await user.click(screen.getByRole("button", { name: /update password/i }));

    await waitFor(() => {
      expect(fetchWithCsrf).toHaveBeenCalledWith(
        "/api/admin/auth/reset-password",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ new_password: "short" }),
        }),
      );
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Password must include a symbol.",
    );
  });

  it("scrubs legacy recovery hash tokens after Supabase processes the session", async () => {
    window.history.replaceState(
      null,
      "",
      "/reset-password#access_token=secret-token&refresh_token=refresh-token&type=recovery",
    );

    render(<ResetPasswordClient />);

    await screen.findByRole("button", { name: /update password/i });
    expect(window.location.pathname).toBe("/reset-password");
    expect(window.location.hash).toBe("");
    expect(window.location.href).not.toContain("secret-token");
    expect(window.location.href).not.toContain("refresh-token");
  });

  it("shows the expired reset-link state when no recovery session is available", async () => {
    mockGetSession.mockResolvedValueOnce({ data: { session: null } });

    render(<ResetPasswordClient />);

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: /reset link expired/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      /reset link is invalid or has expired/i,
    );
    expect(
      screen.getByRole("button", { name: /request a new link/i }),
    ).toBeInTheDocument();
    expect(fetchWithCsrf).not.toHaveBeenCalled();
  });

  it("shows a status after successfully updating a password", async () => {
    const user = userEvent.setup();

    render(<ResetPasswordClient />);

    await screen.findByRole("button", { name: /update password/i });
    await user.type(
      screen.getByLabelText(/^new password$/i),
      "StrongReset123!",
    );
    await user.type(
      screen.getByLabelText(/confirm new password/i),
      "StrongReset123!",
    );
    await user.click(screen.getByRole("button", { name: /update password/i }));

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: /password updated/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/sign in/i);
  });
});
