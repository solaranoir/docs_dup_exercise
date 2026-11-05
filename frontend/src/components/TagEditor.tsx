import { useId, useState, type KeyboardEvent } from "react";
import { normalizeTag, TAG_MAX, TAGS_PER_DOCUMENT, validTag } from "../organize";

/**
 * Chips plus an input. Enter or comma adds a tag; each chip has a labelled remove button.
 * Suggestions come from the user's own tags and the starter set (ADR-010).
 */
export function TagEditor({
  tags,
  suggestions,
  onChange,
}: {
  tags: string[];
  suggestions: string[];
  onChange: (tags: string[]) => void;
}) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const listId = useId();
  const inputId = useId();

  const add = () => {
    const tag = normalizeTag(draft.replace(/,/g, ""));
    if (!tag) return;
    if (!validTag(tag)) {
      setError(`Tags are up to ${TAG_MAX} letters, numbers or - _ . / + #`);
      return;
    }
    if (!tags.includes(tag)) {
      if (tags.length >= TAGS_PER_DOCUMENT) {
        setError(`At most ${TAGS_PER_DOCUMENT} tags per document`);
        return;
      }
      onChange([...tags, tag].sort());
    }
    setDraft("");
    setError(null);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add();
    } else if (e.key === "Backspace" && draft === "" && tags.length > 0) {
      onChange(tags.slice(0, -1));
    }
  };

  return (
    <div className="tag-editor">
      <label htmlFor={inputId}>Tags</label>
      <ul className="tag-chips" aria-label="Tags on this document">
        {tags.map((tag) => (
          <li key={tag} className="tag-chip">
            {tag}
            <button type="button" aria-label={`Remove tag ${tag}`} onClick={() => onChange(tags.filter((t) => t !== tag))}>
              ×
            </button>
          </li>
        ))}
      </ul>
      <input
        id={inputId}
        list={listId}
        value={draft}
        placeholder={tags.length ? "Add tag" : "pota, antenna…"}
        maxLength={TAG_MAX + 8}
        onChange={(e) => {
          setDraft(e.target.value);
          setError(null);
        }}
        onKeyDown={onKeyDown}
        onBlur={add}
        aria-describedby={error ? `${inputId}-error` : undefined}
      />
      <datalist id={listId}>
        {suggestions
          .filter((s) => !tags.includes(s))
          .map((s) => (
            <option key={s} value={s} />
          ))}
      </datalist>
      {error && (
        <p id={`${inputId}-error`} role="alert" className="field-error">
          {error}
        </p>
      )}
    </div>
  );
}
