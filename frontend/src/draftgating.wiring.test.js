// Wiring regressions: a restricted plan (stop/pause/human/none) must not leave a
// sendable draft on the card, and a draft decision must replace the card's
// badge, body and send/copy payloads with the decided tier's message.
import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { MessageCard } from "./App";

global.IS_REACT_ACT_ENVIRONMENT = true;

const M = {
  tier: "firm", tier_label: "Firm follow-up", customer: "Acme Traders",
  invoice_no: "INV-1", amount: 1000, days_overdue: 38, due_date: "2026-10-15", why: "original why",
  subject: "Overdue: INV-1", email: "ORIGINAL EMAIL", whatsapp: "ORIGINAL WHATSAPP",
  to_email: "ap@acme.example", to_phone: "+919999999999",
};

function setup(decision) {
  const calls = [];
  global.fetch = jest.fn(async (url, opts) => {
    calls.push({ url: String(url), body: JSON.parse(opts.body) });
    return { ok: true, json: async () => decision };
  });
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  act(() => { root.render(<MessageCard m={M} currency="INR" sender="Me" company="MyCo" />); });
  act(() => { el.querySelector(".msg-head").click(); });
  return { calls, el, root };
}

const btn = (el, text) => Array.from(el.querySelectorAll("button")).find((b) => b.textContent.trim() === text);
const link = (el, text) => Array.from(el.querySelectorAll("a")).find((a) => a.textContent.trim() === text);

async function logSent(el) {
  await act(async () => { btn(el, "I sent this message").click(); });
}

test("stop: no draft, no copy, no send; header shows the state", async () => {
  const { el } = setup({ kind: "stop", reason: "contact opt-out recorded", tier: null, until: null });
  await logSent(el);
  expect(el.querySelector(".msg-head").textContent).toContain("Stop chasing");
  expect(btn(el, "Copy message")).toBeFalsy();
  expect(link(el, "Send on WhatsApp")).toBeFalsy();
  expect(el.querySelector(".msg-text")).toBeFalsy();
  expect(el.textContent).toContain("No message to send while this one is stopped");
});

test("pause: no draft, no send; header shows paused", async () => {
  const { el } = setup({ kind: "pause", reason: "dispute recorded; a person must resolve it", tier: null, until: null });
  await logSent(el);
  expect(el.querySelector(".msg-head").textContent).toContain("Pause chasing");
  expect(link(el, "Send on WhatsApp")).toBeFalsy();
  expect(btn(el, "Copy message")).toBeFalsy();
});

test("human: no draft, no send; header shows needs-your-call", async () => {
  const { el } = setup({ kind: "human", reason: "latest reply not understood", tier: null, until: null });
  await logSent(el);
  expect(el.querySelector(".msg-head").textContent).toContain("Needs your call");
  expect(link(el, "Send on WhatsApp")).toBeFalsy();
});

test("draft decision replaces badge, body and the send payload with the decided tier", async () => {
  const { el } = setup({
    kind: "draft", reason: "38 days overdue", tier: "escalation", until: null,
    message: { tier: "escalation", tier_label: "Escalation", why: "escalation why",
               subject: "Action needed: INV-1", email: "ESCALATION EMAIL", whatsapp: "ESCALATION WHATSAPP" },
  });
  await logSent(el);
  expect(el.querySelector(".msg-head").textContent).toContain("Escalation");
  expect(el.querySelector(".msg-text").textContent).toBe("ESCALATION WHATSAPP");
  const send = link(el, "Send on WhatsApp");
  expect(send).toBeTruthy();
  expect(send.href).toContain(encodeURIComponent("ESCALATION WHATSAPP"));
  expect(el.textContent).not.toContain("ORIGINAL WHATSAPP");
});

test("draft decision without a message falls back to the original draft", async () => {
  const { el } = setup({ kind: "draft", reason: "38 days overdue", tier: "firm", until: null });
  await logSent(el);
  expect(el.querySelector(".msg-head").textContent).toContain("Firm follow-up");
  expect(el.querySelector(".msg-text").textContent).toBe("ORIGINAL WHATSAPP");
  expect(link(el, "Send on WhatsApp")).toBeTruthy();
});

test("hold keeps a visible draft", async () => {
  const { el } = setup({ kind: "hold", reason: "minimum gap since last follow-up", until: "2026-11-20", tier: null });
  await logSent(el);
  expect(el.querySelector(".msg-text")).toBeTruthy();
  expect(link(el, "Send on WhatsApp")).toBeTruthy();
});

test("plan request carries the card context so the API can draft the decided tier", async () => {
  const { calls, el } = setup({ kind: "draft", reason: "x", tier: "firm", until: null });
  await logSent(el);
  const body = calls[0].body;
  expect(body.customer).toBe("Acme Traders");
  expect(body.email).toBe("ap@acme.example");
  expect(body.phone).toBe("+919999999999");
  expect(body.sender).toBe("Me");
  expect(body.company).toBe("MyCo");
  expect(body.currency).toBe("INR");
});
