// Wiring regressions for owner-recorded review ("I reviewed this") and
// re-consent ("They asked to hear from you again"): both are explicit per-card
// clicks, dated local today, and re-consent needs its attestation ticked.
import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { FollowUp } from "./App";
import { localIso } from "./promiseDate";

global.IS_REACT_ACT_ENVIRONMENT = true;

// The decision banner renders after the first logged event, so each test logs
// one ("I sent this message") and the mock answers with the decision under test.
function setup(decision) {
  const calls = [];
  global.fetch = jest.fn(async (url, opts) => {
    calls.push({ url: String(url), body: JSON.parse(opts.body) });
    return { ok: true, json: async () => decision };
  });
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  act(() => { root.render(<FollowUp m={{ invoice_no: "INV-1", customer: "Acme", amount: 100, days_overdue: 25, tier: "firm" }} />); });
  return { calls, el, root };
}

const btn = (el, text) => Array.from(el.querySelectorAll("button")).find((b) => b.textContent.trim() === text);

async function logSent(el) {
  await act(async () => { btn(el, "I sent this message").click(); });
}

test("'I reviewed this' shows on a pause and logs a resolved event dated local today", async () => {
  const { calls, el } = setup({ kind: "pause", reason: "dispute recorded; a person must resolve it" });
  await logSent(el);
  const b = btn(el, "I reviewed this");
  expect(b).toBeTruthy();
  await act(async () => { b.click(); });
  expect(calls).toHaveLength(2);
  const ev = calls[1].body.events[1];
  expect(ev.type).toBe("resolved");
  expect(ev.day).toBe(localIso(new Date()));
});

test("'I reviewed this' shows on a human/dispute or not-understood decision", async () => {
  const { el } = setup({ kind: "human", reason: "opt-out recorded with an open dispute; a person must resolve it - no further contact unless you record an explicit re-consent" });
  await logSent(el);
  expect(btn(el, "I reviewed this")).toBeTruthy();
});

test("no review or re-consent affordance on an ordinary draft (no default, no bulk)", async () => {
  const { el } = setup({ kind: "draft", reason: "25 days overdue", tier: "firm" });
  await logSent(el);
  expect(btn(el, "I reviewed this")).toBeFalsy();
  expect(btn(el, "They asked to hear from you again")).toBeFalsy();
});

test("re-consent needs the attestation before it can be recorded", async () => {
  const { calls, el } = setup({ kind: "stop", reason: "contact opt-out recorded" });
  await logSent(el);
  const open = btn(el, "They asked to hear from you again");
  expect(open).toBeTruthy();
  await act(async () => { open.click(); });
  expect(btn(el, "Record re-consent").disabled).toBe(true);
  await act(async () => { el.querySelector(".fu-check input[type=checkbox]").click(); });
  expect(btn(el, "Record re-consent").disabled).toBe(false);
  await act(async () => { btn(el, "Record re-consent").click(); });
  expect(calls).toHaveLength(2);
  const ev = calls[1].body.events[1];
  expect(ev.type).toBe("reconsent");
  expect(ev.day).toBe(localIso(new Date()));
});

test("the optional re-consent note reaches the payload; the attestation copy is shown", async () => {
  const { calls, el } = setup({ kind: "stop", reason: "contact opt-out recorded" });
  await logSent(el);
  await act(async () => { btn(el, "They asked to hear from you again").click(); });
  expect(el.textContent).toContain("The contact asked to be contacted again (in writing or a reply).");
  const note = el.querySelector("input[type=text]");
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  await act(async () => { setter.call(note, "called, asked to resume"); note.dispatchEvent(new Event("input", { bubbles: true })); });
  await act(async () => { el.querySelector(".fu-check input[type=checkbox]").click(); });
  await act(async () => { btn(el, "Record re-consent").click(); });
  expect(calls[1].body.events[1].text).toBe("called, asked to resume");
});

test("resumed output shows the contact history (resumption is never silent)", async () => {
  const { el } = setup({ kind: "draft", reason: "29 days overdue (contact history: opted out 2026-11-10; re-consent recorded 2026-11-18)", tier: "firm" });
  await logSent(el);
  expect(el.textContent).toContain("opted out 2026-11-10");
  expect(el.textContent).toContain("re-consent recorded 2026-11-18");
});
