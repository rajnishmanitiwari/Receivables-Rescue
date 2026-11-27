import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import App from "./App";
global.IS_REACT_ACT_ENVIRONMENT=true;
HTMLElement.prototype.scrollIntoView=jest.fn();
const ROW={customer:"Initial Debtor",invoice_no:"INV-32",amount:5000,due_date:"2026-10-15"};
const ok=x=>({ok:true,json:async()=>x});
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return{promise,resolve,reject};};
const button=(el,text)=>[...el.querySelectorAll('button')].find(x=>x.textContent===text);
const click=async(el,text)=>act(async()=>button(el,text).click());
async function upload(el){const input=el.querySelector('input[type=file]');Object.defineProperty(input,'files',{value:[new File(['x'],'bills.csv')],configurable:true});await act(async()=>input.dispatchEvent(new Event('change',{bubbles:true})));}
async function mount(imports,initial=true){
 let i=0;global.fetch=jest.fn(async url=>String(url).includes('/health')?ok({upload:true,pdf:true}):imports[i++]());
 const el=document.createElement('div');document.body.appendChild(el);const root=createRoot(el);await act(async()=>root.render(<App/>));if(initial)await upload(el);return{el,root};
}
const names=el=>[...el.querySelectorAll('.review-table tbody tr')].map(x=>x.querySelector('input').value);
const reading=el=>el.textContent.includes('Reading your bills…');
async function done(ctx){await act(async()=>ctx.root.unmount());ctx.el.remove();}

test('reset discards old import success, notes and delayed scroll',async()=>{
 jest.useFakeTimers();const a=deferred();const ctx=await mount([()=>ok({rows:[ROW]}),()=>a.promise]);await act(async()=>jest.runOnlyPendingTimers());HTMLElement.prototype.scrollIntoView.mockClear();
 await upload(ctx.el);await click(ctx.el,'Start over');expect(reading(ctx.el)).toBe(false);
 await act(async()=>a.resolve(ok({rows:[{...ROW,customer:'Stale Debtor'}],notes:['stale note']})));
 await act(async()=>jest.runOnlyPendingTimers());expect(names(ctx.el)).toEqual([]);expect(ctx.el.textContent).not.toContain('stale note');expect(HTMLElement.prototype.scrollIntoView).not.toHaveBeenCalled();jest.useRealTimers();await done(ctx);
});

test('old failure/finally cannot overwrite a new session error or reading status',async()=>{
 const a=deferred(),b=deferred();const ctx=await mount([()=>ok({rows:[ROW]}),()=>a.promise,()=>b.promise]);await upload(ctx.el);await click(ctx.el,'Start over');await upload(ctx.el);expect(reading(ctx.el)).toBe(true);
 await act(async()=>a.reject(new Error('abandoned failure')));expect(reading(ctx.el)).toBe(true);expect(ctx.el.textContent).not.toContain('abandoned failure');
 await act(async()=>b.resolve(ok({rows:[{...ROW,customer:'New Debtor'}]})));expect(names(ctx.el)).toEqual(['New Debtor']);expect(reading(ctx.el)).toBe(false);await done(ctx);
});

test('loading examples abandons the pending initial upload',async()=>{
 const a=deferred();const ctx=await mount([()=>a.promise],false);await upload(ctx.el);await click(ctx.el,'Try it with example bills');const expected=names(ctx.el);expect(expected.length).toBeGreaterThan(1);
 await act(async()=>a.resolve(ok({rows:[{...ROW,customer:'Stale Debtor'}]})));expect(names(ctx.el)).toEqual(expected);expect(reading(ctx.el)).toBe(false);await done(ctx);
});

test('concurrent deliberate uploads remain additive and reading lasts until both settle',async()=>{
 const a=deferred(),b=deferred();const ctx=await mount([()=>a.promise,()=>b.promise],false);await upload(ctx.el);await upload(ctx.el);
 await act(async()=>b.resolve(ok({rows:[{...ROW,customer:'Second'}]})));expect(names(ctx.el)).toEqual(['Second']);expect(reading(ctx.el)).toBe(true);
 await act(async()=>a.resolve(ok({rows:[{...ROW,customer:'First'}]})));expect(names(ctx.el)).toEqual(['Second','First']);expect(reading(ctx.el)).toBe(false);await done(ctx);
});

test('one current failed concurrent upload reports honestly but cannot end the other upload spinner',async()=>{
 const a=deferred(),b=deferred();const ctx=await mount([()=>a.promise,()=>b.promise],false);await upload(ctx.el);await upload(ctx.el);
 await act(async()=>a.reject(new Error('current upload failed')));expect(reading(ctx.el)).toBe(true);expect(ctx.el.textContent).toContain('current upload failed');
 await act(async()=>b.resolve(ok({rows:[ROW]})));expect(names(ctx.el)).toEqual(['Initial Debtor']);expect(reading(ctx.el)).toBe(false);await done(ctx);
});

test('response body completing after reset is also abandoned',async()=>{
 const body=deferred();const ctx=await mount([()=>ok({rows:[ROW]}),()=>({ok:true,json:()=>body.promise})]);await upload(ctx.el);await click(ctx.el,'Start over');
 await act(async()=>body.resolve({rows:[ROW]}));expect(names(ctx.el)).toEqual([]);await done(ctx);
});

test('a later successful additive upload cannot erase an earlier rejected-file warning',async()=>{
 const warning='More than one bill-number column was found. Keep only the intended bill number column and try again.';
 const ctx=await mount([()=>ok({rows:[],notes:[warning]}),()=>ok({rows:[ROW],notes:[]})]);
 expect(ctx.el.textContent).toContain(warning);await upload(ctx.el);
 expect(names(ctx.el)).toEqual(['Initial Debtor']);expect(ctx.el.textContent).toContain(warning);expect(ctx.el.textContent).toContain('Import history includes earlier attempts');await done(ctx);
});

test('concurrent completion order preserves each current import warning',async()=>{
 const a=deferred(),b=deferred();const ctx=await mount([()=>a.promise,()=>b.promise],false);await upload(ctx.el);await upload(ctx.el);
 await act(async()=>b.resolve(ok({rows:[],notes:['Rejected second input.']})));
 await act(async()=>a.resolve(ok({rows:[ROW],notes:['Skipped 1 row(s) with no usable amount.']})));
 expect(ctx.el.textContent).toContain('Rejected second input.');expect(ctx.el.textContent).toContain('Skipped 1 row(s)');await done(ctx);
});

test('identical per-import skip counts are retained rather than falsely collapsed',async()=>{
 const note='Skipped 1 row(s) with no usable amount.';const ctx=await mount([()=>ok({rows:[ROW],notes:[note]}),()=>ok({rows:[{...ROW,invoice_no:'INV2'}],notes:[note]})]);await upload(ctx.el);
 expect([...ctx.el.querySelectorAll('.notes div')].filter(e=>e.textContent===note)).toHaveLength(2);await done(ctx);
});

test('fallback empty-import notes survive a later success but reset clears the session notes',async()=>{
 const ctx=await mount([()=>ok({rows:[],notes:[]}),()=>ok({rows:[ROW],notes:[]})]);await upload(ctx.el);
 expect(ctx.el.textContent).toContain('Nothing readable was found in those files.');await click(ctx.el,'Start over');
 expect(ctx.el.textContent).not.toContain('Nothing readable was found in those files.');await done(ctx);
});
