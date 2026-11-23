import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import App from './App';
global.IS_REACT_ACT_ENVIRONMENT=true;
HTMLElement.prototype.scrollIntoView=jest.fn();
const ok=x=>({ok:true,json:async()=>x});
const ROW={customer:'Acme',invoice_no:'45',amount:5000.49,due_date:'2026-10-15'};
const btn=(el,t)=>[...el.querySelectorAll('button')].find(b=>b.textContent===t);
const click=async(el,t)=>act(async()=>btn(el,t).click());
async function upload(el,n,drop=false){const files=Array.from({length:n},(_,i)=>new File(['x'],`bill${i}.csv`));const target=el.querySelector(drop?'.drop':'input[type=file]');const event=new Event(drop?'drop':'change',{bubbles:true,cancelable:true});if(drop)Object.defineProperty(event,'dataTransfer',{value:{files}});else Object.defineProperty(target,'files',{value:files,configurable:true});await act(async()=>target.dispatchEvent(event));}
async function mount(){global.fetch=jest.fn(async url=>String(url).includes('/health')?ok({upload:true}):String(url).includes('/extract')?ok({rows:[ROW]}):ok({report:{total_outstanding:5000.49,invoice_count:1,customer_count:1,priority:[],buckets:[],customers:[],risks:[]},messages:[],warnings:[]}));const el=document.createElement('div');document.body.appendChild(el);const root=createRoot(el);await act(async()=>root.render(<App/>));return{el,root};}
async function done(c){await act(async()=>c.root.unmount());c.el.remove();}
const extracts=()=>global.fetch.mock.calls.filter(([u])=>String(u).includes('/extract'));
test.each([false,true])('oversized batch via drop=%s sends nothing and preserves existing results',async drop=>{const c=await mount();try{await upload(c.el,1);await click(c.el,'Show me who to chase');expect(c.el.querySelector('.stats')).not.toBeNull();const before=c.el.querySelector('.stats').textContent;await upload(c.el,13,drop);expect(extracts()).toHaveLength(1);expect(c.el.querySelector('[role=alert]').textContent).toContain('13 files');expect(c.el.querySelector('[role=alert]').textContent).toContain('None of this selection was imported');expect(c.el.querySelector('.stats').textContent).toBe(before);expect(c.el.querySelectorAll('.review-table tbody tr')).toHaveLength(1);await upload(c.el,12,drop);expect(extracts()).toHaveLength(2);expect(extracts()[1][1].body.getAll('files')).toHaveLength(12);expect(c.el.querySelector('[role=alert]')).toBeNull();expect(c.el.querySelectorAll('.review-table tbody tr')).toHaveLength(2);}finally{await done(c);}});
test('oversized selection cannot cancel a valid import already running',async()=>{const c=await mount();try{let resolve;global.fetch.mockImplementation(()=>new Promise(r=>resolve=r));await upload(c.el,1);await upload(c.el,13);expect(c.el.textContent).toContain('Reading your bills…');expect(global.fetch).toHaveBeenCalledTimes(2);await act(async()=>resolve(ok({rows:[ROW]})));expect(c.el.querySelectorAll('.review-table tbody tr')).toHaveLength(1);expect(c.el.textContent).not.toContain('Reading your bills…');}finally{await done(c);}});
