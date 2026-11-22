import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import App from './App';
global.IS_REACT_ACT_ENVIRONMENT=true;
HTMLElement.prototype.scrollIntoView=jest.fn();
test('customer balance rows retain every value and mobile label without shortening identity',async()=>{
 const customer='Acme'+'Unbroken'.repeat(12);
 const row={customer,invoice_no:'I43',amount:5000.49,due_date:'2026-10-15'};
 const ok=x=>({ok:true,json:async()=>x});
 global.fetch=jest.fn(async url=>ok(String(url).includes('/health')?{upload:true}:String(url).includes('/extract')?{rows:[row]}:{report:{total_outstanding:5000.49,invoice_count:1,priority:[],buckets:[],customers:[{customer,amount:5000.49,count:1,oldest_days:39,share:100}]},messages:[]}));
 const el=document.createElement('div');document.body.appendChild(el);const root=createRoot(el);
 try{
  await act(async()=>root.render(<App/>));
  const input=el.querySelector('input[type=file]');Object.defineProperty(input,'files',{value:[new File(['x'],'synthetic.csv')]});
  await act(async()=>input.dispatchEvent(new Event('change',{bubbles:true})));
  await act(async()=>[...el.querySelectorAll('button')].find(b=>b.textContent==='Show me who to chase').click());
  const table=el.querySelector('.customer-balances');
  expect([...table.querySelectorAll('tbody td')].map(td=>[td.dataset.label,td.textContent])).toEqual([['Customer',customer],['Owed','₹5,000.49'],['Bills','1'],['Oldest','39d'],['Share','100%']]);
  expect(table.querySelectorAll('thead th')).toHaveLength(5);
 }finally{await act(async()=>root.unmount());el.remove();}
});
