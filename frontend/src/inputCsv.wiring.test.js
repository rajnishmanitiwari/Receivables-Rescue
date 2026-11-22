import React from "react";
import {createRoot} from "react-dom/client";
import {act} from "react-dom/test-utils";
import App, {rowsToCsv, stripUnconfirmedDates} from "./App";
import {chaseCsv} from "./chaseCsv";
global.IS_REACT_ACT_ENVIRONMENT = true;
HTMLElement.prototype.scrollIntoView = jest.fn();
const row = {customer:'Acme "North", Ltd', invoice_no:'INV-"39"', amount:5000, due_date:'2026-10-15', email:'ap@example.test', phone:'+919999999999'};
const expected = 'Customer,Invoice No,Amount,Due Date,Email,Phone\n"Acme ""North"", Ltd","INV-""39""",5000,"2026-10-15","ap@example.test","+919999999999"';
test('analysis transport escapes embedded quotes without replacing identity characters', () => {
  const before = {...row};
  expect(rowsToCsv([row])).toBe(expected);
  expect(row).toEqual(before);
});
test('transport preserves multiline, Unicode and formula-like input text without download markers', () => {
  expect(rowsToCsv([{...row, customer:'=\"日本\"\nSouth', invoice_no:'+"39"'}])).toContain('"=""日本""\nSouth","+""39"""');
  expect(rowsToCsv([{...row, customer:'=1+1'}])).not.toContain('[text]');
  expect(chaseCsv([{customer:'=1+1', invoice_no:'+"39"', rank:1, amount:5000}])).toContain('"[text] =1+1","[text] +""39"""');
});
test('blank optional cells and assumed date behavior stay unchanged', () => {
  expect(rowsToCsv(stripUnconfirmedDates([{customer:'"A"', amount:10, due_date:'2026-10-15',date_assumed:true}]))).toBe('Customer,Invoice No,Amount,Due Date,Email,Phone\n"""A""","",10,"","",""');
});
test('real App analysis request uses lossless quoted transport', async () => {
  const ok = data => ({ok:true,json:async()=>data});
  global.fetch = jest.fn(async url => ok(String(url).includes('/health') ? {upload:true} : String(url).includes('/extract') ? {rows:[row]} : {report:{priority:[],buckets:[],customers:[]},messages:[]}));
  const el = document.createElement('div');document.body.appendChild(el);const root=createRoot(el);
  try {
    await act(async()=>root.render(<App/>));
    const input=el.querySelector('input[type=file]');
    Object.defineProperty(input,'files',{value:[new File(['synthetic'],'quotes.csv')]});
    await act(async()=>input.dispatchEvent(new Event('change',{bubbles:true})));
    await act(async()=>[...el.querySelectorAll('button')].find(b=>b.textContent==='Show me who to chase').click());
    const call=fetch.mock.calls.find(([url])=>String(url).includes('/analyse'));
    expect(JSON.parse(call[1].body).data).toBe(expected);
  } finally {await act(async()=>root.unmount());el.remove();}
});
