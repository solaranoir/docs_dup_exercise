import { expect, test } from "@playwright/test";
import { loginAs, newDocument } from "./fixtures";

// Demo script step 10: invalid extension, oversize upload, stale revision, malformed JSON.
// Stale revision (409) is covered in editor_persistence.spec.ts; invalid extension in
// import_formats.spec.ts and attachments.spec.ts.

const OVERSIZE = Buffer.alloc(10 * 1024 * 1024 + 1, "a");

test("oversize import and attachment are rejected with a clear message", async ({ page }) => {
  await loginAs(page, "alice");
  await page.getByRole("button", { name: "Import file" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/^File/).setInputFiles({ name: "big.txt", mimeType: "text/plain", buffer: OVERSIZE });
  await expect(dialog.getByRole("alert")).toContainText("larger than 10 MB");
  await dialog.getByRole("button", { name: "Close" }).click();

  await newDocument(page);
  const panel = page.getByRole("region", { name: "Attachments" });
  await panel.getByLabel("Attach file").setInputFiles({ name: "big.txt", mimeType: "text/plain", buffer: OVERSIZE });
  await expect(panel.getByRole("alert")).toContainText("larger than 10 MB");
  await expect(panel.getByText("No attachments.")).toBeVisible();
});

test("empty title is not saved", async ({ page }) => {
  await loginAs(page, "alice");
  await newDocument(page);
  await page.getByLabel("Document title").fill("   ");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("alert")).toContainText("Title is required.");
  await expect(page.getByRole("status")).toHaveText("Save failed");
});

test("malformed or unsafe document JSON is rejected by the API without changing data", async ({ page }) => {
  await loginAs(page, "alice");
  const url = await newDocument(page);
  const id = url.split("/").pop()!;
  const api = `/api/documents/${id}`;

  const malformed = await page.request.patch(api, {
    headers: { "Content-Type": "application/json" },
    data: "{not json",
  });
  expect(malformed.status()).toBe(422);

  const unsafe = await page.request.patch(api, {
    data: {
      expected_revision: 1,
      content_json: { type: "doc", content: [{ type: "html", text: "<img src=x onerror=alert(1)>" }] },
    },
  });
  expect(unsafe.status()).toBe(422);

  const doc = await (await page.request.get(api)).json();
  expect(doc.revision).toBe(1);
  expect(JSON.stringify(doc.content_json)).not.toContain("onerror");
});
