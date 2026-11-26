import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import App, { rowsToCsv } from "./App";
global.IS_REACT_ACT_ENVIRONMENT = true;
const RAW = '<img src=x onerror=alert(1)>2026-10-15/2027-01-15';
const ROW = {customer:'Acme',invoice_no:'I61',amount:5000.49,due_date:null,due_date_raw:RAW};
async function mount(rows=[ROW]) {
 global.fetch=jest.fn(async url=>({ok:true,json:async()=>String(url).includes('health')?{upload:true,pdf:true}:String(url).includes('extract')?{rows}: {report:{}}}));
 const el=document.createElement('div');document.body.appendChild(el);const root=createRoot(el);
 await act(async()=>root.render(<App/>));const input=el.querySelector('input[type=file]');
 Object.defineProperty(input,'files',{value:[new File(['x'],'dates.csv')]});
 await act(async()=>input.dispatchEvent(new Event('change',{bubbles:true})));
 return {el,root};
}
async function change(input,value){await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new Event('input',{bubbles:true}));});}
async function click(el,text){await act(async()=>[...el.querySelectorAll('button')].find(b=>b.textContent===text).click());}
test('original unreadable date is text only and survives correction/clearing; reset removes it',async()=>{
 const {el,root}=await mount();expect(el.querySelector('.original-date-value').textContent).toBe(RAW);
 expect(el.querySelector('.original-date img')).toBeNull();expect(el.querySelector('input[type=date]').value).toBe('');
 expect(el.querySelector('.original-date').textContent).toContain('unscheduled');
 await change(el.querySelector('input[type=date]'),'2026-10-15');
 expect(el.querySelector('.original-date-value').textContent).toBe(RAW);
 expect(el.querySelector('.original-date').textContent).toContain('Using the date you entered');
 await change(el.querySelector('input[type=date]'),'');expect(el.querySelector('.original-date').textContent).toContain('unscheduled');
 await click(el,'Start over');expect(el.querySelector('.original-date')).toBeNull();
 await act(async()=>root.unmount());el.remove();
});
test('old API rows and valid dates have no unreadable-date label',async()=>{
 const {el,root}=await mount([{...ROW,due_date:'2026-10-15',due_date_raw:undefined}]);
 expect(el.querySelector('.original-date')).toBeNull();await act(async()=>root.unmount());el.remove();
});
test('original raw text never becomes the analysis date or transport field',()=>{
 const unknown=rowsToCsv([ROW]);expect(unknown).not.toContain(RAW);expect(unknown).not.toContain('due_date_raw');
 const corrected=rowsToCsv([{...ROW,due_date:'2026-10-15'}]);expect(corrected).toContain('2026-10-15');expect(corrected).not.toContain(RAW);
});
test('removing an unreadable-date row keeps the other bill and its date',async()=>{
 const {el,root}=await mount([ROW,{...ROW,invoice_no:'I62',due_date:'2026-10-15',due_date_raw:''}]);
 await act(async()=>el.querySelector('[aria-label="Remove row 1"]').click());
 expect(el.querySelector('.original-date')).toBeNull();expect(el.querySelectorAll('.review-table tbody tr')).toHaveLength(1);
 expect(el.querySelector('input[type=date]').value).toBe('2026-10-15');
 await act(async()=>root.unmount());el.remove();
});
test('long original date is not truncated in the session review',async()=>{
 const raw='unreadable '.repeat(200);const {el,root}=await mount([{...ROW,due_date_raw:raw}]);
 expect(el.querySelector('.original-date-value').textContent).toBe(raw);
 await act(async()=>root.unmount());el.remove();
});
