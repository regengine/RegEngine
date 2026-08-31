import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const mediaRoot = path.join(frontendRoot, "public", "media");
const frameRoot = await mkdtemp(path.join(tmpdir(), "regengine-inflow-magic-"));
const baseUrl = process.env.INFLOW_CAPTURE_URL || "http://127.0.0.1:4310/tools/inflow-lab";

const stages = [
    ["raw", "See the messy feed"],
    ["normalize", "Watch it become traceability"],
    ["detect", "Catch the defect"],
    ["trace", "Follow the lot"],
    ["evidence", "See the evidence package"],
];

const localChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await chromium.launch({
    headless: true,
    ...(existsSync(localChrome) ? { executablePath: localChrome } : {}),
});
const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1,
    reducedMotion: "reduce",
});
const pageErrors = [];
page.on("pageerror", (error) => pageErrors.push(error.message));

try {
    await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });
    const story = page.getByTestId("inflow-magic-story");
    await story.waitFor({ state: "visible", timeout: 30_000 });
    await page.waitForTimeout(1_200);
    const firstStage = page.locator("#inflow-magic-tab-raw");
    if ((await story.count()) === 0 || (await firstStage.count()) === 0) {
        const bodyText = (await page.locator("body").innerText()).slice(0, 1_000);
        throw new Error(`Inflow Magic Story disappeared after hydration. Current URL: ${page.url()}\n${bodyText}`);
    }
    const visualStage = page.getByTestId("magic-visual-stage");
    const naturalFrame = await visualStage.boundingBox();
    const storyFrame = await story.boundingBox();
    const gridTemplate = await visualStage.evaluate((element) => getComputedStyle(element.parentElement?.parentElement || element).gridTemplateColumns);
    process.stdout.write(`Capture viewport ${page.viewportSize()?.width}x${page.viewportSize()?.height}; story ${storyFrame?.width}x${storyFrame?.height}; stage ${naturalFrame?.width}x${naturalFrame?.height}; grid ${gridTemplate}\n`);
    await visualStage.evaluate((element) => {
        element.style.width = "960px";
        element.style.height = "540px";
        element.style.minHeight = "540px";
    });

    for (const [index, [id, name]] of stages.entries()) {
        await page.locator(`#inflow-magic-tab-${id}`).click();
        await page.getByRole("heading", { name, exact: true }).waitFor({ state: "visible" });
        await page.waitForTimeout(120);
        await visualStage.screenshot({
            path: path.join(frameRoot, `stage-${index + 1}.png`),
            animations: "disabled",
        });
    }

    await visualStage.evaluate((element) => {
        element.style.removeProperty("width");
        element.style.removeProperty("height");
        element.style.removeProperty("min-height");
    });
    await page.locator("#inflow-magic-tab-raw").click();
    await story.screenshot({ path: path.join(frameRoot, "story-desktop.png"), animations: "disabled" });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(300);
    const mobileStoryFrame = await story.boundingBox();
    const mobileStageFrame = await visualStage.boundingBox();
    const mobileGridTemplate = await visualStage.evaluate((element) => getComputedStyle(element.parentElement?.parentElement || element).gridTemplateColumns);
    process.stdout.write(`Mobile story ${mobileStoryFrame?.width}x${mobileStoryFrame?.height}; stage ${mobileStageFrame?.width}x${mobileStageFrame?.height}; grid ${mobileGridTemplate}\n`);
    await story.screenshot({ path: path.join(frameRoot, "story-mobile.png"), animations: "disabled" });
    if (pageErrors.length) {
        throw new Error(`Browser errors during capture:\n${pageErrors.join("\n")}`);
    }
} finally {
    await browser.close();
}

const inputs = stages.flatMap((_, index) => ["-loop", "1", "-t", "2.6", "-i", path.join(frameRoot, `stage-${index + 1}.png`)]);
const normalizedFrames = stages
    .map((_, index) => `[${index}:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0x020617,format=yuv420p[v${index}]`)
    .join(";");
const transitions = [
    "[v0][v1]xfade=transition=fade:duration=0.5:offset=2.1[x1]",
    "[x1][v2]xfade=transition=fade:duration=0.5:offset=4.2[x2]",
    "[x2][v3]xfade=transition=fade:duration=0.5:offset=6.3[x3]",
    "[x3][v4]xfade=transition=fade:duration=0.5:offset=8.4[outv]",
].join(";");
const filter = `${normalizedFrames};${transitions}`;
const mp4Path = path.join(mediaRoot, "inflow-lab-magic-loop.mp4");
const webmPath = path.join(mediaRoot, "inflow-lab-magic-loop.webm");
const posterPath = path.join(mediaRoot, "inflow-lab-magic-poster.png");

function run(command, args) {
    const result = spawnSync(command, args, { cwd: frontendRoot, encoding: "utf8" });
    if (result.status !== 0) {
        throw new Error(`${command} failed:\n${result.stderr || result.stdout}`);
    }
}

run("ffmpeg", [
    "-y",
    ...inputs,
    "-filter_complex",
    filter,
    "-map",
    "[outv]",
    "-t",
    "10.9",
    "-an",
    "-c:v",
    "libx264",
    "-crf",
    "24",
    "-preset",
    "medium",
    "-movflags",
    "+faststart",
    mp4Path,
]);

run("ffmpeg", [
    "-y",
    "-i",
    mp4Path,
    "-an",
    "-c:v",
    "libvpx-vp9",
    "-crf",
    "36",
    "-b:v",
    "0",
    webmPath,
]);

run("ffmpeg", [
    "-y",
    "-i",
    path.join(frameRoot, "stage-3.png"),
    "-vf",
    "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0x020617",
    "-frames:v",
    "1",
    posterPath,
]);

process.stdout.write(`Captured Inflow Lab media in ${mediaRoot}\n`);
process.stdout.write(`Temporary source frames: ${frameRoot}\n`);
