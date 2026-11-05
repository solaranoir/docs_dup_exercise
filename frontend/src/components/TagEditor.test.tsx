import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { TagEditor } from "./TagEditor";

function Harness({ initial = [] as string[] }) {
  const [tags, setTags] = useState(initial);
  return <TagEditor tags={tags} suggestions={["pota", "satellite"]} onChange={setTags} />;
}

const chips = () => screen.queryAllByRole("listitem").map((li) => li.firstChild?.textContent);

describe("TagEditor", () => {
  it("adds normalised tags with Enter or comma, without duplicates", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByLabelText("Tags");
    await user.type(input, "Field Day{Enter}POTA,pota{Enter}");
    expect(chips()).toEqual(["field-day", "pota"]);
  });

  it("removes with the chip button or Backspace on an empty input", async () => {
    const user = userEvent.setup();
    render(<Harness initial={["cw", "pota"]} />);
    await user.click(screen.getByRole("button", { name: "Remove tag cw" }));
    expect(chips()).toEqual(["pota"]);
    await user.type(screen.getByLabelText("Tags"), "{Backspace}");
    expect(chips()).toEqual([]);
  });

  it("explains invalid tags instead of saving them", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(screen.getByLabelText("Tags"), "a<b{Enter}");
    expect(screen.getByRole("alert")).toHaveTextContent("Tags are up to 32");
    expect(chips()).toEqual([]);
  });
});
