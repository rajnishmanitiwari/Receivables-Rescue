// Unconfirmed-date UI: a bucket without a probability renders as neutral (not
// red/amber), an assumed due date stays flagged in the review table until the
// user edits it or taps to confirm, untouched assumed dates are serialised
// blank so /api/analyse keeps them unscheduled, and the planner is never
// called with a reconstructed due date for an unconfirmed row.
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { Aging, ReviewTable, MessageCard, rowsToCsv, stripUnconfirmedDates } from "./App";

global.IS_REACT_ACT_ENVIRONMENT = true;

function render(ui) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  act(() => { root.render(ui); });
  return { el, root };
}

test("aging bucket without a probability renders neutral, not critical", () => {
  const buckets = [
    { bucket: "0-30 days", count: 1, amount: 5000, share: 50, probability: 80 },
    { bucket: "No confirmed due date", count: 1, amount: 5000, share: 50, probability: null },
  ];
  const { el } = render(<Aging buckets={buckets} currency="INR" />);
  const rows = Array.from(el.querySelectorAll(".aging-row"));
  const neutral = rows.find((r) => r.textContent.includes("No confirmed due date"));
  expect(neutral.querySelector(".aging-bar").className).toContain("b-neutral");
  const dated = rows.find((r) => r.textContent.includes("0-30 days"));
  expect(dated.querySelector(".aging-bar").className).not.toContain("b-neutral");
});

function ReviewHarness({ initial }) {
  const [rows, setRows] = useState(initial);
  return <ReviewTable rows={rows} setRows={setRows} currency="INR" />;
}

const ROW = {
  customer: "Acme", invoice_no: "I1", amount: 1000, due_date: "2026-01-10",
  email: "", phone: "", confidence: "high", date_assumed: true,
};

test("assumed due date is flagged in the review table", () => {
  const { el } = render(<ReviewHarness initial={[ROW]} />);
  expect(el.textContent).toContain("We estimated this date");
});

test("editing the due date clears the assumed flag", () => {
  const { el } = render(<ReviewHarness initial={[ROW]} />);
  const dateInput = el.querySelector('input[type="date"]');
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  act(() => {
    setter.call(dateInput, "2026-02-01");
    dateInput.dispatchEvent(new Event("input", { bubbles: true }));
  });
  expect(el.textContent).not.toContain("We estimated this date");
});

test("tapping the flag confirms the date and clears the flag", () => {
  const { el } = render(<ReviewHarness initial={[ROW]} />);
  const flag = el.querySelector("button.assumed");
  expect(flag).not.toBeNull();
  act(() => { flag.click(); });
  expect(el.textContent).not.toContain("We estimated this date");
  // The value itself is untouched: confirming never edits the date.
  expect(el.querySelector('input[type="date"]').value).toBe("2026-01-10");
});

test("a row without an assumed date shows no flag", () => {
  const { el } = render(<ReviewHarness initial={[{ ...ROW, date_assumed: false }]} />);
  expect(el.textContent).not.toContain("We estimated this date");
});

test("serialisation blanks untouched assumed dates, keeps confirmed ones", () => {
  const confirmed = { ...ROW, customer: "Confirmed Co", date_assumed: false };
  const edited = { ...ROW, customer: "Edited Co", due_date: "2026-02-01", date_assumed: false }; // update() cleared the flag
  const csv = rowsToCsv(stripUnconfirmedDates([ROW, confirmed, edited]));
  const lines = csv.split("\n");
  expect(lines[0]).toBe("Customer,Invoice No,Amount,Due Date,Email,Phone");
  // Untouched assumption: due cell goes out blank, so the backend sees an
  // undated row and keeps it in "No confirmed due date" with no draft.
  expect(lines[1]).toBe('"Acme","I1",1000,"","",""');
  expect(lines[2]).toBe('"Confirmed Co","I1",1000,"2026-01-10","",""');
  expect(lines[3]).toBe('"Edited Co","I1",1000,"2026-02-01","",""');
});

test("planner is never asked to act on an unconfirmed row", async () => {
  const m = {
    tier: "firm", tier_label: "Firm follow-up", customer: "Mystery Co",
    invoice_no: "M1", amount: 80000, days_overdue: null, why: "", subject: "",
    email: "X", whatsapp: "X", to_email: "", to_phone: "",
  };
  const calls = [];
  global.fetch = jest.fn(async (url, opts) => { calls.push(String(url)); return { ok: true, json: async () => ({}) }; });
  const { el } = render(<MessageCard m={m} currency="INR" sender="Me" company="MyCo" />);
  act(() => { el.querySelector(".msg-head").click(); });
  const sent = Array.from(el.querySelectorAll("button")).find((b) => b.textContent.trim() === "I sent this message");
  await act(async () => { sent.click(); });
  expect(calls.filter((u) => u.includes("/api/next-action"))).toHaveLength(0);
  expect(el.textContent).toContain("Confirm this bill's due date");
});
