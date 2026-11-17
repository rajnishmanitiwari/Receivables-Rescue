// Wiring regression: a logged "I sent this message" must reach /api/next-action
// with its tier intact (dropped tier = repeated same-tier drafts instead of HOLD),
// and the UI-only session id must not leak into the payload.
import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { FollowUp } from "./App";
import { localIso } from "./promiseDate";

global.IS_REACT_ACT_ENVIRONMENT = true;

function setup() {
  const calls = [];
  global.fetch = jest.fn(async (url, opts) => {
    calls.push({ url: String(url), body: JSON.parse(opts.body) });
    return { ok: true, json: async () => ({ kind: "hold", reason: "minimum gap since last follow-up", until: "2026-11-20" }) };
  });
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  act(() => { root.render(<FollowUp m={{ invoice_no: "INV-1", customer: "Acme", amount: 100, days_overdue: 25, tier: "firm" }} />); });
  return { calls, el, root };
}

test("sent event reaches the API with its tier and without the session id", async () => {
  const { calls, el } = setup();
  const btn = Array.from(el.querySelectorAll("button")).find((b) => b.textContent === "I sent this message");
  await act(async () => { btn.click(); });
  expect(calls).toHaveLength(1);
  expect(calls[0].url).toContain("/api/next-action");
  expect(calls[0].body.events).toHaveLength(1);
  const ev = calls[0].body.events[0];
  expect(ev.type).toBe("sent");
  expect(ev.tier).toBe("firm");
  expect(ev.day).toBe(localIso(new Date()));
  expect(Object.keys(ev)).not.toContain("id");
});

test("a pasted reply carries the editable received-on day, defaulting to local today", async () => {
  const { calls, el } = setup();
  const replied = Array.from(el.querySelectorAll("button")).find((b) => b.textContent === "They replied");
  await act(async () => { replied.click(); });
  const ta = el.querySelector("textarea");
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
  await act(async () => { setter.call(ta, "will pay by friday"); ta.dispatchEvent(new Event("input", { bubbles: true })); });
  const go = Array.from(el.querySelectorAll("button")).find((b) => b.textContent.trim() === "Work out the next step");
  await act(async () => { go.click(); });
  const reply = calls[0].body.events[0];
  expect(reply.type).toBe("reply");
  expect(reply.day).toBe(localIso(new Date()));
  expect(reply.text).toBe("will pay by friday");
});

test("plan requests carry the client's local today (no server-clock fallback)", async () => {
  const { calls, el } = setup();
  const btn = Array.from(el.querySelectorAll("button")).find((b) => b.textContent === "I sent this message");
  await act(async () => { btn.click(); });
  expect(calls[0].body.today).toBe(localIso(new Date()));
});

test("a future reply received-on date is rejected, not logged", async () => {
  const { calls, el } = setup();
  const replied = Array.from(el.querySelectorAll("button")).find((b) => b.textContent === "They replied");
  await act(async () => { replied.click(); });
  const dayInput = el.querySelector('input[type=date]');
  const setDate = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  await act(async () => { setDate.call(dayInput, "2999-01-01"); dayInput.dispatchEvent(new Event("input", { bubbles: true })); });
  const ta = el.querySelector("textarea");
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
  await act(async () => { setter.call(ta, "will pay by friday"); ta.dispatchEvent(new Event("input", { bubbles: true })); });
  const go = Array.from(el.querySelectorAll("button")).find((b) => b.textContent.trim() === "Work out the next step");
  await act(async () => { go.click(); });
  expect(calls).toHaveLength(0);
  expect(el.textContent).toContain("cannot be in the future");
});

test("suggestion confirm lands on the server-echoed reply_index, not list-last", async () => {
  // Two replies: first today, second backdated. Server suggests from reply_index 0.
  const calls = [];
  let round = 0;
  global.fetch = jest.fn(async (url, opts) => {
    calls.push({ url: String(url), body: JSON.parse(opts.body) });
    round += 1;
    const payload = round === 2
      ? { kind: "human", reason: "promise without a date",
          suggested_promise_date: { date: "2026-11-20", phrase: "by friday", reply_day: localIso(new Date()), rule: "weekday", reply_index: 0 } }
      : { kind: "human", reason: "latest reply not understood" };
    return { ok: true, json: async () => payload };
  });
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  act(() => { root.render(<FollowUp m={{ invoice_no: "INV-2", customer: "Acme", amount: 100, days_overdue: 25, tier: "firm" }} />); });
  const setTA = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
  const logReply = async (text) => {
    const replied = Array.from(el.querySelectorAll("button")).find((b) => b.textContent === "They replied");
    await act(async () => { replied.click(); });
    const ta = el.querySelector("textarea");
    await act(async () => { setTA.call(ta, text); ta.dispatchEvent(new Event("input", { bubbles: true })); });
    const go = Array.from(el.querySelectorAll("button")).find((b) => b.textContent.trim() === "Work out the next step");
    await act(async () => { go.click(); });
  };
  await logReply("will pay by friday");
  // backdate the received-on input, then log the second reply
  const replied2 = Array.from(el.querySelectorAll("button")).find((b) => b.textContent === "They replied");
  await act(async () => { replied2.click(); });
  const dayInput = el.querySelector('input[type=date]');
  const setDate = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  await act(async () => { setDate.call(dayInput, "2020-01-01"); dayInput.dispatchEvent(new Event("input", { bubbles: true })); });
  const ta2 = el.querySelector("textarea");
  await act(async () => { setTA.call(ta2, "still chasing accounts"); ta2.dispatchEvent(new Event("input", { bubbles: true })); });
  const go2 = Array.from(el.querySelectorAll("button")).find((b) => b.textContent.trim() === "Work out the next step");
  await act(async () => { go2.click(); });
  // chip shows (from the mocked suggestion); Use it
  const useBtn = Array.from(el.querySelectorAll("button")).find((b) => b.textContent.startsWith("Use "));
  expect(useBtn).toBeTruthy();
  await act(async () => { useBtn.click(); });
  const lastCall = calls[calls.length - 1].body;
  expect(lastCall.events[0].promise_date).toBe("2026-11-20");
  expect(lastCall.events[1].promise_date).toBeUndefined();
});

test("a suggestion whose echo does not match the event gets no confirm path", async () => {
  // reply_index day mismatch: the chip must not offer Use/Pick (never a guess).
  const calls = [];
  global.fetch = jest.fn(async (url, opts) => {
    calls.push({ url: String(url), body: JSON.parse(opts.body) });
    return { ok: true, json: async () => ({ kind: "human", reason: "promise without a date",
      suggested_promise_date: { date: "2026-11-20", phrase: "by friday", reply_day: "2020-01-01", rule: "weekday", reply_index: 0 } }) };
  });
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  act(() => { root.render(<FollowUp m={{ invoice_no: "INV-3", customer: "Acme", amount: 100, days_overdue: 25, tier: "firm" }} />); });
  const replied = Array.from(el.querySelectorAll("button")).find((b) => b.textContent === "They replied");
  await act(async () => { replied.click(); });
  const ta = el.querySelector("textarea");
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
  await act(async () => { setter.call(ta, "will pay by friday"); ta.dispatchEvent(new Event("input", { bubbles: true })); });
  const go = Array.from(el.querySelectorAll("button")).find((b) => b.textContent.trim() === "Work out the next step");
  await act(async () => { go.click(); });
  const useBtn = Array.from(el.querySelectorAll("button")).find((b) => b.textContent.startsWith("Use "));
  const pickBtn = Array.from(el.querySelectorAll("button")).find((b) => b.textContent === "Pick another date");
  expect(useBtn).toBeFalsy();
  expect(pickBtn).toBeFalsy();
});
