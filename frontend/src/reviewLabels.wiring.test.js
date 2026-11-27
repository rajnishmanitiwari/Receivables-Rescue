import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { ReviewTable } from "./App";
global.IS_REACT_ACT_ENVIRONMENT = true;
const ROW={customer:'Acme',invoice_no:'INV1',amount:5000.49,due_date:'',email:'',phone:'',due_date_raw:'2026-10-15/2027-01-15'};
function Harness({initial}) {const [rows,setRows]=useState(initial);return <ReviewTable rows={rows} setRows={setRows} currency="INR"/>;}
function mount(initial=[ROW,{...ROW,invoice_no:'INV2',due_date_raw:''}]) {
 const el=document.createElement('div');document.body.appendChild(el);const root=createRoot(el);
 act(()=>root.render(<Harness initial={initial}/>));return {el,root};
}
function done({el,root}){act(()=>root.unmount());el.remove();}
test('each editable review cell has a unique field and row name',()=>{
 const m=mount();const inputs=[...m.el.querySelectorAll('tbody input')];
 expect(inputs).toHaveLength(12);
 expect(inputs.map(e=>e.getAttribute('aria-label'))).toEqual([1,2].flatMap(n=>['Who owes you','Bill number','Amount','Due date','Email','Phone'].map(f=>`${f}, row ${n}`)));
 expect(new Set(inputs.map(e=>e.getAttribute('aria-label'))).size).toBe(12);done(m);
});
test('unreadable-date guidance describes only the corresponding date input',()=>{
 const m=mount();const dates=m.el.querySelectorAll('input[type=date]');
 const id=dates[0].getAttribute('aria-describedby');expect(id).toBeTruthy();
 const context=document.getElementById(id);expect(context.textContent).toContain(ROW.due_date_raw);expect(context.textContent).toContain('unscheduled');
 expect(dates[1].hasAttribute('aria-describedby')).toBe(false);done(m);
});
test('row deletion and addition keep labels and descriptions aligned',()=>{
 const m=mount();act(()=>m.el.querySelector('[aria-label="Remove row 1"]').click());
 expect(m.el.querySelector('[aria-label="Bill number, row 1"]').value).toBe('INV2');
 expect(m.el.querySelector('[aria-label="Due date, row 1"]').hasAttribute('aria-describedby')).toBe(false);
 act(()=>[...m.el.querySelectorAll('button')].find(b=>b.textContent==='+ Add a row').click());
 expect(m.el.querySelector('[aria-label="Amount, row 2"]')).not.toBeNull();done(m);
});
test('two review tables never share original-date description identifiers',()=>{
 const a=mount([ROW]),b=mount([ROW]);
 expect(a.el.querySelector('input[type=date]').getAttribute('aria-describedby')).not.toBe(b.el.querySelector('input[type=date]').getAttribute('aria-describedby'));done(a);done(b);
});
