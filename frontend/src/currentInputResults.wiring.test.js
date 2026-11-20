import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import App from "./App";
global.IS_REACT_ACT_ENVIRONMENT = true;
HTMLElement.prototype.scrollIntoView = jest.fn();
const ROW = {customer:"Acme",invoice_no:"INV-31",amount:5000,due_date:"2026-10-15",email:"ap@acme.test",phone:"+91 99887 66554"};
const reply = tag => ({report:{total_outstanding:tag,invoice_count:1,customer_count:1,priority:[],buckets:[],customers:[],risks:[]},messages:[],warnings:[]});
const ok = value => ({ok:true,json:async()=>value});
const deferred = () => {let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject};};
async function mount(analysis) {
  global.fetch=jest.fn(async url=>String(url).includes('/health')?ok({upload:true,pdf:true}):String(url).includes('/extract')?ok({rows:[ROW]}):analysis());
  const el=document.createElement('div');document.body.appendChild(el);const root=createRoot(el);
  await act(async()=>root.render(<App/>));
  const file=el.querySelector('input[type=file]');Object.defineProperty(file,'files',{value:[new File(['x'],'bills.csv')]});
  await act(async()=>file.dispatchEvent(new Event('change',{bubbles:true})));
  return {el,root};
}
const btn=(el,text)=>[...el.querySelectorAll('button')].find(x=>x.textContent===text);
const click=async(el,text)=>{await act(async()=>btn(el,text).click());};
async function edit(input,value){await act(async()=>{const proto=input.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(input,value);input.dispatchEvent(new Event(input.tagName==='SELECT'?'change':'input',{bubbles:true}));});}
async function done(ctx){await act(async()=>ctx.root.unmount());ctx.el.remove();}

test.each([[0,'Other Debtor'],[1,'INV-NEW'],[2,'123'],[3,'2026-11-01'],[4,'new@debtor.test'],[5,'+91 98765 43210']])('editing row field %s removes ALL old analysis/output actions until rerun',async(index,value)=>{
 const ctx=await mount(async()=>ok(reply(5000)));await click(ctx.el,'Show me who to chase');expect(ctx.el.querySelector('.stats')).not.toBeNull();
 await edit(ctx.el.querySelectorAll('.review-table tbody input')[index],value);
 expect(ctx.el.querySelector('.stats')).toBeNull();expect(btn(ctx.el,'Download list')).toBeUndefined();expect(btn(ctx.el,'Copy share text')).toBeUndefined();
 await click(ctx.el,'Show me who to chase');expect(ctx.el.querySelector('.stats')).not.toBeNull();await done(ctx);
});

test.each([['#cur','USD'],['#sender','New Sender'],['#company','New Business']])('changing %s invalidates the analysis and prevents relabeling an old result',async(selector,value)=>{
 const ctx=await mount(async()=>ok(reply(5000)));await click(ctx.el,'Show me who to chase');await click(ctx.el,'+ Your details and currency');
 await edit(ctx.el.querySelector(selector),value);expect(ctx.el.querySelector('.stats')).toBeNull();await done(ctx);
});

test('adding/removing rows invalidates existing output; removing last row and reset do not resurrect it',async()=>{
 const ctx=await mount(async()=>ok(reply(5000)));await click(ctx.el,'Show me who to chase');await click(ctx.el,'+ Add a row');expect(ctx.el.querySelector('.stats')).toBeNull();
 await act(async()=>ctx.el.querySelector('[aria-label="Remove row 2"]').click());await click(ctx.el,'Show me who to chase');expect(ctx.el.querySelector('.stats')).not.toBeNull();
 await act(async()=>ctx.el.querySelector('[aria-label="Remove row 1"]').click());expect(ctx.el.querySelector('.stats')).toBeNull();await done(ctx);
});

test('edited input cancels busy ownership; older success cannot overwrite newer result',async()=>{
 const a=deferred(),b=deferred();let calls=0;const ctx=await mount(()=>++calls===1?a.promise:b.promise);
 await click(ctx.el,'Show me who to chase');expect(btn(ctx.el,'Working it out…').disabled).toBe(true);
 await edit(ctx.el.querySelector('.review-table input.num'),'7000');expect(btn(ctx.el,'Show me who to chase').disabled).toBe(false);
 await click(ctx.el,'Show me who to chase');await act(async()=>b.resolve(ok(reply(7000))));expect(ctx.el.querySelector('.stats').textContent).toContain('7,000');
 await act(async()=>a.resolve(ok(reply(5000))));expect(ctx.el.querySelector('.stats').textContent).toContain('7,000');expect(ctx.el.querySelector('.stats').textContent).not.toContain('5,000');await done(ctx);
});

test('older failure cannot clear newer busy state or display stale error; reset discards pending success',async()=>{
 const a=deferred(),b=deferred();let calls=0;const ctx=await mount(()=>++calls===1?a.promise:b.promise);
 await click(ctx.el,'Show me who to chase');await edit(ctx.el.querySelector('.review-table input.num'),'7000');await click(ctx.el,'Show me who to chase');
 await act(async()=>a.reject(new Error('old request failure')));expect(ctx.el.querySelector('[role=alert]')).toBeNull();expect(btn(ctx.el,'Working it out…').disabled).toBe(true);
 await click(ctx.el,'Start over');await act(async()=>b.resolve(ok(reply(7000))));expect(ctx.el.querySelector('.stats')).toBeNull();expect(btn(ctx.el,'Working it out…')).toBeUndefined();await done(ctx);
});

test('current network failure still reports and unlocks rerun',async()=>{
 const ctx=await mount(async()=>{throw new Error('current failure');});await click(ctx.el,'Show me who to chase');expect(ctx.el.querySelector('[role=alert]').textContent).toContain('current failure');expect(btn(ctx.el,'Show me who to chase').disabled).toBe(false);await done(ctx);
});

test('reverting an edit does not resurrect a previously generated result',async()=>{
 const ctx=await mount(async()=>ok(reply(5000)));await click(ctx.el,'Show me who to chase');
 await edit(ctx.el.querySelector('.review-table input.num'),'123');await edit(ctx.el.querySelector('.review-table input.num'),'5000');
 expect(ctx.el.querySelector('.stats')).toBeNull();await done(ctx);
});

test('starting another import discards a pending analysis before imported rows arrive',async()=>{
 const a=deferred(),upload=deferred();const ctx=await mount(()=>a.promise);await click(ctx.el,'Show me who to chase');
 global.fetch.mockImplementation(async url=>String(url).includes('/extract')?upload.promise:ok({}));
 await act(async()=>ctx.el.querySelector('input[type=file]').dispatchEvent(new Event('change',{bubbles:true})));
 await act(async()=>a.resolve(ok(reply(5000))));expect(ctx.el.querySelector('.stats')).toBeNull();
 await act(async()=>upload.resolve(ok({rows:[ROW]})));expect(ctx.el.querySelector('.stats')).toBeNull();await done(ctx);
});
