/** Client-side mirror of backend/app/organization.py normalisation (ADR-010). */
export const TAG_MAX = 32;
export const TAGS_PER_DOCUMENT = 20;

export function normalizeTag(raw: string): string {
  return raw.trim().toLowerCase().replace(/\s+/g, "-");
}

export function validTag(tag: string): boolean {
  return tag.length >= 1 && tag.length <= TAG_MAX && /^[\p{L}\p{N}\-_./+#]+$/u.test(tag);
}
