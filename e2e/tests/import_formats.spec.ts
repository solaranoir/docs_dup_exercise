import { expect, test } from "@playwright/test";
import { FIXTURES, loginAs, newDocument } from "./fixtures";

test("import .txt as a new document", async ({ page }) => {
  await loginAs(page, "alice");
  await page.getByRole("button", { name: "Import file" }).click();
  const dialog = page.getByRole("dialog", { name: "Import file as new document" });
  await dialog.getByLabel(/^File/).setInputFiles(`${FIXTURES}/sample.txt`);
  await expect(dialog.getByText("Converted without losing supported formatting.")).toBeVisible();
  await expect(dialog.getByLabel("Import preview")).toContainText("Meeting notes");
  await expect(dialog.getByLabel("Title")).toHaveValue("sample");
  await dialog.getByLabel("Title").fill("Imported text");
  await dialog.getByRole("button", { name: "Create document" }).click();

  await expect(page).toHaveURL(/#\/doc\//);
  await expect(page.getByLabel("Document title")).toHaveValue("Imported text");
  await expect(page.getByLabel("Document body")).toContainText("Second paragraph after a blank line.");
});

test("import .docx as a new document shows fidelity warnings", async ({ page }) => {
  await loginAs(page, "alice");
  await page.getByRole("button", { name: "Import file" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/^File/).setInputFiles(`${FIXTURES}/sample.docx`);
  const warnings = dialog.getByRole("note", { name: "Conversion warnings" });
  await expect(warnings).toContainText("Tables are not supported and were removed.");
  await dialog.getByRole("button", { name: "Create document" }).click();

  const body = page.getByLabel("Document body");
  await expect(body.locator("h1")).toHaveText("Quarterly Report");
  await expect(body.locator("strong")).toHaveText("strongly");
  await expect(body.locator("em")).toHaveText("quarter");
  await expect(body.locator("u")).toHaveText("Underlined note");
  await expect(body.locator("ul > li")).toHaveText(["New customers", "Lower churn"]);
  await expect(body.locator("ol > li")).toHaveText(["Plan budget", "Hire team"]);
});

test("import .md into an existing draft with Append, then Replace", async ({ page }) => {
  await loginAs(page, "alice");
  await newDocument(page);
  const body = page.getByLabel("Document body");
  await body.click();
  await page.keyboard.type("Existing line");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("All changes saved");

  await page.getByRole("button", { name: "Import…" }).click();
  let dialog = page.getByRole("dialog", { name: "Import into this document" });
  await dialog.getByLabel(/^File/).setInputFiles(`${FIXTURES}/sample.md`);
  await expect(dialog.getByRole("note", { name: "Conversion warnings" })).toContainText(
    "Embedded HTML was removed.",
  );
  await expect(dialog.getByLabel("Append to the end")).toBeChecked();
  await dialog.getByRole("button", { name: "Append content" }).click();
  await expect(dialog).toBeHidden();
  await expect(body.locator("p").first()).toHaveText("Existing line");
  await expect(body.locator("h1")).toHaveText("Project Plan");
  await expect(page.getByRole("status")).toHaveText("All changes saved");

  await page.reload();
  await expect(body).toContainText("Existing line");
  await expect(body.locator("h1")).toHaveText("Project Plan");

  await page.getByRole("button", { name: "Import…" }).click();
  dialog = page.getByRole("dialog", { name: "Import into this document" });
  await dialog.getByLabel(/^File/).setInputFiles(`${FIXTURES}/sample.txt`);
  await dialog.getByLabel("Replace all content").check();
  page.once("dialog", (confirm) => {
    expect(confirm.message()).toContain("Replace the entire document");
    void confirm.accept();
  });
  await dialog.getByRole("button", { name: "Replace content" }).click();
  await expect(dialog).toBeHidden();
  await expect(body).not.toContainText("Existing line");
  await expect(body).toContainText("Meeting notes");
});

test("unsupported upload shows an actionable error", async ({ page }) => {
  await loginAs(page, "alice");
  await page.getByRole("button", { name: "Import file" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/^File/).setInputFiles({
    name: "malware.exe",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("MZ"),
  });
  await expect(dialog.getByRole("alert")).toContainText("Unsupported file type. Use .txt, .md or .docx.");
  await expect(dialog.getByRole("button", { name: "Create document" })).toHaveCount(0);
});
