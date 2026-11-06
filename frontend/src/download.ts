/** Hands a fetched file to the browser's normal download flow. */
export function saveFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.style.display = "none";
  document.body.append(a);
  a.click();
  a.remove();
  // Revoke after the click has been handled; revoking immediately can cancel the download.
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** Opens the browser's print dialog (Save as PDF) with the document's own title as the
 * suggested file name, then restores the tab title (DOC-029, ADR-012). */
export function printDocument(title: string): void {
  const previous = document.title;
  document.title = title;
  const restore = () => {
    document.title = previous;
    window.removeEventListener("afterprint", restore);
  };
  window.addEventListener("afterprint", restore);
  window.print();
}
