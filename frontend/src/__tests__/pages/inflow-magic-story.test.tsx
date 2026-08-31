import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { InflowMagicStory } from "@/app/tools/inflow-lab/components/InflowMagicStory";

const { capture } = vi.hoisted(() => ({ capture: vi.fn() }));

vi.mock("@/lib/posthog-provider", () => ({
    usePostHog: () => ({ capture }),
}));

describe("Inflow Lab visual story", () => {
    beforeEach(() => capture.mockClear());

    it("shows the complete raw-data-to-evidence narrative and real product media", () => {
        const { container } = render(
            <InflowMagicStory
                eventCount={7}
                readinessScore={82}
                exceptionCount={2}
                selectedLot="TLC-VISUAL-001"
            />
        );

        expect(
            screen.getByRole("heading", {
                name: "Watch messy supplier activity become defensible evidence.",
            })
        ).toBeInTheDocument();
        expect(screen.getByRole("tab", { name: /See the messy feed/i })).toBeInTheDocument();
        expect(screen.getByRole("tab", { name: /Watch it become traceability/i })).toBeInTheDocument();
        expect(screen.getByRole("tab", { name: /Catch the defect/i })).toBeInTheDocument();
        expect(screen.getByRole("tab", { name: /Follow the lot/i })).toBeInTheDocument();
        expect(screen.getByRole("tab", { name: /See the evidence package/i })).toBeInTheDocument();

        const video = screen.getByLabelText("Inflow Lab visual walkthrough");
        expect(video).toHaveAttribute("poster", "/media/inflow-lab-magic-poster.png");
        expect(video).not.toHaveAttribute("autoplay");
        expect(container.querySelector('source[type="video/webm"]')).toHaveAttribute(
            "src",
            "/media/inflow-lab-magic-loop.webm"
        );
        expect(container.querySelector('track[kind="captions"]')).toHaveAttribute(
            "src",
            "/media/inflow-lab-magic-captions.vtt"
        );
    });

    it("lets a visitor move from the hidden defect to the lot trace", async () => {
        const user = userEvent.setup();
        render(
            <InflowMagicStory
                eventCount={7}
                readinessScore={82}
                exceptionCount={2}
                selectedLot="TLC-VISUAL-001"
            />
        );

        await user.click(screen.getByRole("tab", { name: /Catch the defect/i }));
        expect(await screen.findByText("ship_to_location = null")).toBeInTheDocument();
        expect(screen.getByLabelText("Readiness score 82 out of 100")).toBeInTheDocument();

        await user.click(screen.getByRole("tab", { name: /Follow the lot/i }));
        expect(await screen.findByText("TLC-VISUAL-001")).toBeInTheDocument();
        expect(screen.getByText("Destination?")).toBeInTheDocument();
    });

    it("supports roving keyboard navigation through the transformation", async () => {
        const user = userEvent.setup();
        render(
            <InflowMagicStory
                eventCount={7}
                readinessScore={82}
                exceptionCount={2}
                selectedLot="TLC-VISUAL-001"
            />
        );

        const rawStage = screen.getByRole("tab", { name: /See the messy feed/i });
        rawStage.focus();
        await user.keyboard("{ArrowRight}{ArrowRight}");

        expect(screen.getByRole("tab", { name: /Catch the defect/i })).toHaveFocus();
        expect(await screen.findByText("ship_to_location = null")).toBeInTheDocument();
        expect(capture).toHaveBeenLastCalledWith(
            "INFLOW_MAGIC_STAGE_SELECTED",
            expect.objectContaining({ stage: "detect", interaction: "keyboard" })
        );
    });

    it("starts the guided scenario from the story conclusion", async () => {
        const user = userEvent.setup();
        const onStartGuidedRun = vi.fn();
        render(
            <InflowMagicStory
                eventCount={7}
                readinessScore={82}
                exceptionCount={2}
                selectedLot="TLC-VISUAL-001"
                onStartGuidedRun={onStartGuidedRun}
            />
        );

        await user.click(screen.getByRole("button", { name: "Run this test scenario" }));
        expect(onStartGuidedRun).toHaveBeenCalledTimes(1);
        expect(capture).toHaveBeenCalledWith(
            "INFLOW_MAGIC_GUIDED_RUN_STARTED",
            expect.objectContaining({ source: "visual_story" })
        );
    });

    it("keeps the interactive story available when video playback fails", () => {
        render(
            <InflowMagicStory
                eventCount={7}
                readinessScore={82}
                exceptionCount={2}
                selectedLot="TLC-VISUAL-001"
            />
        );

        fireEvent.error(screen.getByLabelText("Inflow Lab visual walkthrough"));

        expect(screen.getByRole("status")).toHaveTextContent("The walkthrough could not load.");
        expect(capture).toHaveBeenCalledWith("INFLOW_MAGIC_VIDEO_FAILED", { source: "visual_story" });
    });
});
