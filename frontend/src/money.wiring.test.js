import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import {money, ReviewTable, MessageCard} from './App';
global.IS_REACT_ACT_ENVIRONMENT=true;
const cases=[
 [5000.49,'INR','₹5,000.49'],[6000.75,'INR','₹6,000.75'],[0.25,'INR','₹0.25'],
 [1234567.5,'INR','₹12,34,567.50'],[-0.25,'INR','-₹0.25'],[5000,'INR','₹5,000'],
 [5000.49,'USD','$5,000.49'],[1234567.5,'USD','$1,234,567.50'],
 [1.01,'EUR','€1.01'],[1.1,'GBP','£1.10'],[1.25,'AED','AED 1.25'],[5000,'USD','$5,000']
];
test.each(cases)('money preserves minor units for %s %s',(n,cur,want)=>expect(money(n,cur)).toBe(want));
test('review total and bill label show the same fractional amount as the underlying bills',async()=>{
 const el=document.createElement('div');document.body.appendChild(el);const root=createRoot(el);
 const rows=[{customer:'Acme',invoice_no:'INV-40',amount:5000.49,due_date:'2026-10-15',email:'',phone:''},{customer:'Beta',amount:1000.26,due_date:'2026-10-15',email:'',phone:''}];
 try {
  await act(async()=>root.render(<><ReviewTable rows={rows} setRows={()=>{}} currency="INR"/><MessageCard m={{...rows[0],tier:'firm',days_overdue:38}} currency="INR"/></>));
  expect(el.querySelector('.review-total').textContent).toContain('₹6,000.75');
  expect(el.querySelector('.msg-head').textContent).toContain('₹5,000.49');
 } finally {await act(async()=>root.unmount());el.remove();}
});
