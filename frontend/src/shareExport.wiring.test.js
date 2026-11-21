import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import App from './App';
global.IS_REACT_ACT_ENVIRONMENT=true;
HTMLElement.prototype.scrollIntoView=jest.fn();
const ok=x=>({ok:true,json:async()=>x});
const report={total_outstanding:5000,invoice_count:2,customer_count:1,cost_of_waiting_30d:1234,ranking_basis:"Ordered by how much each bill costs you if you wait another 30 days.",priority:[{rank:1,customer:'=1+1',invoice_no:'+2',amount:3000,due_date:'2026-10-15',days_overdue:37,bucket:'31-60',probability:70,slip_30d:900,statutory_interest:99,tier:'firm'},{rank:2,customer:'Acme',invoice_no:'UNKNOWN',amount:2000,due_date:null,days_overdue:null,bucket:'unknown',probability:null,slip_30d:334,tier:'reminder'}],buckets:[],customers:[],risks:[]};
const btn=(el,t)=>[...el.querySelectorAll('button')].find(x=>x.textContent===t);
const readBlob=blob=>new Promise(resolve=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.readAsText(blob)});
test('copy and download carry input facts, not predicted loss, collection percentages or statutory amounts',async()=>{
 global.fetch=jest.fn(async u=>ok(String(u).includes('/health')?{upload:true}:String(u).includes('/extract')?{rows:[{customer:'Acme',amount:5000,due_date:'2026-10-15'}]}:{report,messages:[]}));
 const writeText=jest.fn().mockResolvedValue();Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText}});
 let blob;global.URL.createObjectURL=jest.fn(b=>{blob=b;return 'blob:test'});global.URL.revokeObjectURL=jest.fn();jest.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
 const el=document.createElement('div');document.body.appendChild(el);const root=createRoot(el);await act(async()=>root.render(<App/>));const f=el.querySelector('input[type=file]');Object.defineProperty(f,'files',{value:[new File(['x'],'bills.csv')]});await act(async()=>f.dispatchEvent(new Event('change',{bubbles:true})));await act(async()=>btn(el,'Show me who to chase').click());
 await act(async()=>btn(el,'Copy share text').click());const text=writeText.mock.calls[0][0];expect(text).toContain('5,000');expect(text).toContain('2 bills');expect(text).toContain('entered');expect(text).not.toMatch(/disappear|1,234|quietly|chance|statutory|prediction/i);
 await act(async()=>btn(el,'Download list').click());const csv=await readBlob(blob);expect(csv.split('\n')[0]).toBe('Heuristic rank,Customer,Invoice,Amount,Due date,Days late,Bucket,Draft tier');expect(csv).toContain('3000,"2026-10-15",37');expect(csv).toContain('"[text] =1+1","[text] +2"');expect(csv).toContain('2000,"",,');expect(csv).not.toMatch(/collection|waiting|statutory|900|334|1234/i);expect(el.textContent).toContain('not collection forecasts or legal amounts');expect(el.textContent).not.toContain('each bill costs you');
 await act(async()=>root.unmount());el.remove();jest.restoreAllMocks();
});
