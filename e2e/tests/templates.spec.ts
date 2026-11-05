import { expect, test } from "@playwright/test";
import { loginAs, uniqueTitle } from "./fixtures";

test("templates: preview, create a dated document, fill a field, reload, search", async ({ page }) => {
  // Charlie: other specs only create blank documents as Charlie.
  const marker = uniqueTitle("AO91").replace(" ", "x"); // one searchable word
  await loginAs(page, "charlie");

  await page.getByRole("button", { name: "New document" }).click();
  const dialog = page.getByRole("dialog", { name: "New document" });
  await expect(dialog.getByRole("radio", { name: "Blank document" })).toBeChecked();
  const satellite = dialog.getByRole("radio", { name: "Satellite Observation Log" });
  await expect(satellite).toHaveAccessibleDescription(/satellite pass/);
  await satellite.check();
  const preview = dialog.getByRole("region", { name: "Preview" });
  await expect(preview.getByText("Uplink · Downlink · CTCSS / PL tone · Doppler notes")).toBeVisible();
  await dialog.getByRole("button", { name: "Create" }).click();

  // An ordinary document, titled with today's local date and the template's sections.
  await expect(page).toHaveURL(/\/doc\/[\w-]+$/);
  const title = page.getByLabel("Document title");
  await expect(title).toHaveValue(/^Satellite Observation Log, \d{4}-\d{2}-\d{2}$/);
  const body = page.getByLabel("Document body");
  await expect(body.getByRole("heading", { name: "Reception", level: 2 })).toBeVisible();

  // Fill in a labelled line: typing at its end is plain text, not part of the bold label.
  // Click the end of the line, as a person would (End scrolls instead on macOS Chromium).
  const line = body.locator("p", { hasText: /^Satellite:/ });
  const box = await line.boundingBox();
  await line.click({ position: { x: box!.width - 4, y: box!.height / 2 } });
  await page.keyboard.type(marker);
  await expect(body.locator("strong", { hasText: marker })).toHaveCount(0);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("All changes saved");

  await page.reload();
  await expect(body.getByText(`Satellite: ${marker}`)).toBeVisible();

  // Found by search like any other document.
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  await page.getByLabel("Search documents").fill(marker);
  const results = page.getByRole("region", { name: "Search results" });
  await expect(results.getByRole("link", { name: /^Satellite Observation Log, / })).toHaveCount(1);
});
