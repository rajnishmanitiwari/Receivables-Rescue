import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import App from './App';
global.IS_REACT_ACT_ENVIRONMENT=true;
HTMLElement.prototype.scrollIntoView=jest.fn();
const ok=x=>({ok:true,json:async()=>x});
const button=(el,t)=>[...el.querySelectorAll('button')].find(b=>b.textContent===t);
const click=async(el,t)=>act(async()=>button(el,t).click());
const set=async(el,v)=>act(async()=>{Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}));});
const ROW={customer:'Acme',invoice_no:'44',amount:5000.49,due_date:'2026-10-15'};
async function mount(response){global.fetch=jest.fn(async url=>String(url).includes('/health')?ok({upload:true}):response());const el=document.createElement('div');document.body.appendChild(el);const root=createRoot(el);await act(async()=>root.render(<App/>));await click(el,'Type or paste them instead');await set(el.querySelector('#paste'),'original bill text');return {el,root};}
async function done(c){await act(async()=>c.root.unmount());c.el.remove();}
test.each([
 ['zero rows',()=>ok({rows:[],notes:['Amount needs fixing']})],
 ['HTTP error',()=>({ok:false,json:async()=>({detail:'Import failed'})})],
 ['network failure',()=>Promise.reject(Error('Network unavailable'))],
 ['unreadable body',()=>({ok:true,json:async()=>{throw Error('bad json')}})]
])('%s keeps original paste and editor for correction',async(label,response)=>{const c=await mount(response);try{await click(c.el,'Add these');expect(c.el.querySelector('#paste').value).toBe('original bill text');expect(c.el.querySelectorAll('.review-table tbody tr')).toHaveLength(0);expect(button(c.el,'Add these').disabled).toBe(false);}finally{await done(c);}});
test('success imports once and clears only submitted unchanged text',async()=>{const c=await mount(()=>ok({rows:[ROW]}));try{await click(c.el,'Add these');expect(c.el.querySelector('#paste').value).toBe('');expect(c.el.querySelectorAll('.review-table tbody tr')).toHaveLength(1);}finally{await done(c);}});
test('text edited during successful request survives',async()=>{let resolve;const pending=new Promise(r=>resolve=r);const c=await mount(()=>pending);try{await click(c.el,'Add these');await set(c.el.querySelector('#paste'),'corrected or next bill');await act(async()=>resolve(ok({rows:[ROW]})));expect(c.el.querySelector('#paste').value).toBe('corrected or next bill');expect(c.el.querySelectorAll('.review-table tbody tr')).toHaveLength(1);}finally{await done(c);}});
test('abandoned import cannot clear or close retained paste',async()=>{let resolve;const pending=new Promise(r=>resolve=r);const c=await mount(()=>pending);try{await click(c.el,'Add these');await click(c.el,'Try it with example bills');await act(async()=>resolve(ok({rows:[ROW]})));expect(c.el.querySelector('#paste').value).toBe('original bill text');}finally{await done(c);}});
