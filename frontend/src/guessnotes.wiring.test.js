// Stale-warning regression: import notes about guessed due dates must reflect
// the live rows. Confirming a guessed date must retire its "not scheduled for
// chasing" note before any chase draft appears below it, while unrelated
// import notes (skipped rows, duplicates, undated) stay untouched.
import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import App, { guessNotes } from "./App";

global.IS_REACT_ACT_ENVIRONMENT = true;

const AMBIGUOUS_ROW = {
  customer: "Beta Corp", invoice_no: "INV-2", amount: 2000, due_date: "2026-06-05",
  email: "", phone: "", confidence: "high", date_assumed: true, date_assumed_reason: "ambiguous",
};
const CONFIRMED_ROW = {
  customer: "Acme Traders", invoice_no: "INV-1", amount: 1000, due_date: "2026-06-25",
  email: "", phone: "", confidence: "high", date_assumed: false, date_assumed_reason: "",
};

test("guessNotes counts only unconfirmed guessed dates, by reason", () => {
  expect(guessNotes([])).toEqual([]);
  expect(guessNotes([CONFIRMED_ROW])).toEqual([]);
  const notes = guessNotes([AMBIGUOUS_ROW, CONFIRMED_ROW]);
  expect(notes).toHaveLength(1);
  expect(notes[0]).toContain("could be read day-first or month-first");
  expect(notes[0]).toContain("not scheduled for chasing");
  // A confirmed guess no longer counts.
  expect(guessNotes([{ ...AMBIGUOUS_ROW, date_assumed: false }])).toEqual([]);
  // Positional guesses get their own accurate note.
  const pos = guessNotes([{ ...AMBIGUOUS_ROW, date_assumed_reason: "positional" }]);
  expect(pos).toHaveLength(1);
  expect(pos[0]).toContain("without a header row");
  // Dates computed from an ambiguous base get their own month-off warning.
  const ac = guessNotes([{ ...AMBIGUOUS_ROW, date_assumed_reason: "ambiguous-computed" }]);
  expect(ac).toHaveLength(1);
  expect(ac[0]).toContain("computed from an invoice date");
  expect(ac[0]).toContain("a month off");
  expect(ac[0]).toContain("not scheduled for chasing");
  // A confirmed ambiguous-computed guess no longer counts.
  expect(guessNotes([{ ...AMBIGUOUS_ROW, date_assumed_reason: "ambiguous-computed", date_assumed: false }])).toEqual([]);
});

function mountApp(extractPayload) {
  global.fetch = jest.fn(async (url) => {
    const u = String(url);
    if (u.includes("/api/health")) return { ok: true, json: async () => ({ upload: true, pdf: true, vision: false }) };
    if (u.includes("/api/extract")) return { ok: true, json: async () => extractPayload };
    return { ok: true, json: async () => ({}) };
  });
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  act(() => { root.render(<App />); });
  return { el, root };
}

function noteTexts(el) {
  return Array.from(el.querySelectorAll(".notes div")).map((d) => d.textContent);
}

test("confirming an ambiguous date retires its warning; other import notes survive", async () => {
  const { el } = mountApp({
    rows: [CONFIRMED_ROW, AMBIGUOUS_ROW],
    notes: [
      "1 date(s) like 05/06/2026 could be read day-first or month-first (matching the rest of the column, but still only a guess). Shown day-first, unconfirmed; those bills are not scheduled for chasing. Confirm or fix the dates where you review them.",
      "Skipped 1 row(s) with no usable amount.",
    ],
  });
  const input = el.querySelector('input[type=file]');
  const file = new File(["x"], "bills.csv", { type: "text/csv" });
  await act(async () => { input.dispatchEvent(new Event("change", { bubbles: true })); });
  // jsdom does not populate files on dispatch; call the handler path directly.
  await act(async () => {
    Object.defineProperty(input, "files", { value: [file], configurable: true });
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await act(async () => { await Promise.resolve(); });

  let texts = noteTexts(el);
  // The static backend string is replaced by the derived live note (no duplicate),
  // and the unrelated import note survives untouched.
  expect(texts.filter((t) => t.includes("could be read day-first or month-first"))).toHaveLength(1);
  expect(texts.some((t) => t.includes("matching the rest of the column"))).toBe(false);
  expect(texts.some((t) => t.includes("Skipped 1 row(s)"))).toBe(true);

  // Confirm the guessed date on the Beta row: the ambiguous note must retire.
  const betaRow = Array.from(el.querySelectorAll(".review-table tbody tr"))
    .find((tr) => Array.from(tr.querySelectorAll("input")).some((i) => i.value.includes("Beta")));
  const btn = betaRow.querySelector("button.assumed");
  expect(btn).toBeTruthy();
  await act(async () => { btn.click(); });
  texts = noteTexts(el);
  expect(texts.some((t) => t.includes("could be read day-first or month-first"))).toBe(false);
  expect(texts.some((t) => t.includes("Skipped 1 row(s)"))).toBe(true);
});
