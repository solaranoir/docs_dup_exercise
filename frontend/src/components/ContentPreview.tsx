import { EditorContent, useEditor, type JSONContent } from "@tiptap/react";
import { useEffect } from "react";
import { extensions } from "../editorExtensions";

/** Read-only render of converted content, using the same schema as the editor. */
export function ContentPreview({ content }: { content: JSONContent }) {
  const editor = useEditor({
    extensions,
    content,
    editable: false,
    editorProps: { attributes: { "aria-label": "Import preview", class: "editor-body preview-body" } },
  });
  useEffect(() => {
    editor?.commands.setContent(content, { emitUpdate: false });
  }, [editor, content]);
  return <EditorContent editor={editor} className="editor preview" />;
}
