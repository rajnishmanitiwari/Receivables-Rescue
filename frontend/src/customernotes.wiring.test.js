// Missing-customer gate: extraction never invents a debtor. A row with no
// customer name must surface a live note that retires once the user types
// the name, and analyse is blocked while any row lacks one.
import { customerNotes } from "./App";

const NAMED = { customer: "Acme Traders", amount: 1000 };
const BLANK = { customer: "", amount: 500 };

test("customerNotes flags rows with no customer and retires when filled", () => {
  expect(customerNotes([])).toEqual([]);
  expect(customerNotes([NAMED])).toEqual([]);
  const notes = customerNotes([NAMED, BLANK]);
  expect(notes).toHaveLength(1);
  expect(notes[0]).toContain("no customer name");
  expect(notes[0]).toContain("never guess");
  // Whitespace-only counts as missing; a typed name retires the note.
  expect(customerNotes([{ customer: "   ", amount: 5 }])).toHaveLength(1);
  expect(customerNotes([{ ...BLANK, customer: "Bluepeak Ventures" }])).toEqual([]);
});

test("customerNotes counts every missing row", () => {
  const notes = customerNotes([BLANK, BLANK, NAMED]);
  expect(notes[0]).toContain("2 bill(s)");
});
