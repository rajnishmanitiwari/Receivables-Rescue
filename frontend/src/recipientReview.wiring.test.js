import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import App from "./App";
global.IS_REACT_ACT_ENVIRONMENT = true;
const ROW = { customer: "Bluepeak Logistics", invoice_no: "INV-C30", amount: 45000,
  due_date: "2026-10-15", email: "sales@seller.test", phone: "+91 99887 66554",
  recipient_review_required: true, recipient_unconfirmed: true };
async function mount(rows) {
  global.fetch = jest.fn(async url => ({ ok: true, json: async () => String(url).includes("health") ?
    { upload: true, pdf: true } : String(url).includes("extract") ? { rows } : {} }));
  const el = document.createElement("div"); document.body.appendChild(el);
  const root = createRoot(el); await act(async () => root.render(<App />));
  const input = el.querySelector('input[type=file]');
  Object.defineProperty(input, "files", { value: [new File(["x"], "bill.pdf")] });
  await act(async () => input.dispatchEvent(new Event("change", { bubbles: true })));
  return {el,root};
}
const button = (el, text) => [...el.querySelectorAll("button")].find(b => b.textContent === text);
const analysisCalls = () => global.fetch.mock.calls.filter(c => String(c[0]).includes("/analyse"));
async function click(el, text) { await act(async () => button(el,text).click()); }
async function change(input,value) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(input,value);
    input.dispatchEvent(new Event("input",{bubbles:true}));
  });
}

test("document name and contacts require affirmative review before analyse; confirmation retires error", async () => {
  const {el,root}=await mount([ROW]);
  expect(el.querySelector(".recipient-check").textContent).toContain("Bluepeak Logistics");
  expect(el.querySelector(".recipient-check").textContent).toContain("sales@seller.test");
  await click(el,"Show me who to chase"); expect(analysisCalls()).toHaveLength(0);
  expect(el.querySelector('[role=alert]').textContent).toContain("Check and confirm");
  await click(el,"Confirm name and contacts");
  expect(el.querySelector(".recipient-check")).toBeNull();
  expect(el.querySelector('[role=alert]')).toBeNull();
  await click(el,"Show me who to chase"); expect(analysisCalls()).toHaveLength(1);
  await act(async()=>root.unmount());el.remove();
});

test("editing a confirmed document name clears old contacts and reopens review", async () => {
  const {el,root}=await mount([ROW]);
  await click(el,"Confirm name and contacts");
  const inputs=el.querySelectorAll(".review-table tbody input");
  await change(inputs[0],"Correct Debtor");
  expect(inputs[4].value).toBe("");expect(inputs[5].value).toBe("");
  expect(el.querySelector(".recipient-check").textContent).toContain("Correct Debtor");
  await click(el,"Show me who to chase");expect(analysisCalls()).toHaveLength(0);
  await click(el,"Confirm name and contacts");
  await change(inputs[4],"new@debtor.test");
  expect(el.querySelector(".recipient-check").textContent).toContain("new@debtor.test");
  await click(el,"Show me who to chase");expect(analysisCalls()).toHaveLength(0);
  await act(async()=>root.unmount());el.remove();
});

test("each document row must be confirmed; blank name cannot be confirmed; manual and CSV unaffected", async () => {
  const {el,root}=await mount([ROW,{...ROW,customer:"",invoice_no:"INV-2"}]);
  const confirms=[...el.querySelectorAll(".recipient-check button")];expect(confirms[1].disabled).toBe(true);
  await act(async()=>confirms[0].click());
  await click(el,"Show me who to chase");expect(analysisCalls()).toHaveLength(0);
  expect(el.querySelector('[role=alert]').textContent).toContain("no customer name");
  await act(async()=>root.unmount());el.remove();
  const csv=await mount([{...ROW,recipient_review_required:undefined,recipient_unconfirmed:undefined}]);
  expect(csv.el.querySelector(".recipient-check")).toBeNull();
  await click(csv.el,"Show me who to chase");expect(analysisCalls()).toHaveLength(1);
  await act(async()=>csv.root.unmount());csv.el.remove();
});


test("old API document source still requires review during rolling updates", async () => {
  const {el,root}=await mount([{...ROW,source:"bill.PDF",recipient_review_required:undefined,recipient_unconfirmed:undefined}]);
  expect(el.querySelector(".recipient-check")).not.toBeNull();
  await click(el,"Show me who to chase");expect(analysisCalls()).toHaveLength(0);
  await act(async()=>root.unmount());el.remove();
});

test("zero-amount provisional rows do not block otherwise valid reviewed bills", async () => {
  const {el,root}=await mount([{...ROW,recipient_review_required:undefined,recipient_unconfirmed:undefined}, {...ROW,amount:0}]);
  await click(el,"Show me who to chase");expect(analysisCalls()).toHaveLength(1);
  await act(async()=>root.unmount());el.remove();
});

test("recipient confirmation does not confirm an assumed due date", async () => {
  const {el,root}=await mount([{...ROW,date_assumed:true,date_assumed_reason:"ambiguous"}]);
  await click(el,"Confirm name and contacts");
  expect(el.querySelector("button.assumed")).not.toBeNull();
  await click(el,"Show me who to chase");
  const payload=JSON.parse(analysisCalls()[0][1].body);
  expect(payload.data).not.toContain("2026-10-15");
  await act(async()=>root.unmount());el.remove();
});
