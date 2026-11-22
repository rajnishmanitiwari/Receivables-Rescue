import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import {FollowUp} from './App';
global.IS_REACT_ACT_ENVIRONMENT=true;
const btn=(el,t)=>[...el.querySelectorAll('button')].find(b=>b.textContent.trim()===t);
const set=async(el,value)=>act(async()=>{Object.getOwnPropertyDescriptor(el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(el,value);el.dispatchEvent(new Event('input',{bubbles:true}));});
async function setup(){
 global.fetch=jest.fn(async()=>({ok:true,json:async()=>({kind:'human',reason:'promise without a date'})}));
 const el=document.createElement('div');document.body.appendChild(el);const root=createRoot(el);
 await act(async()=>root.render(<FollowUp m={{customer:'Acme',invoice_no:'41',amount:5000.49,due_date:'2026-10-15',days_overdue:38,tier:'firm'}}/>));
 await act(async()=>btn(el,'They replied').click());
 await set(el.querySelector('textarea'),'will pay by friday');
 return {el,root};
}
afterEach(()=>jest.useRealTimers());
test.each(['','2999-01-01','2026-02-30'])('invalid received-on %s neither logs nor discards reply, correcting it sends one original reply',async day=>{
 jest.useFakeTimers();jest.setSystemTime(new Date(2026,10,22,12));
 const {el,root}=await setup();
 try {
  await set(el.querySelector('input[type=date]'),day);
  await act(async()=>btn(el,'Work out the next step').click());
  expect(fetch).not.toHaveBeenCalled();
  expect(el.querySelector('textarea').value).toBe('will pay by friday');
  expect(el.querySelector('[role=alert]').textContent).toContain(day==='2999-01-01'?'cannot be in the future':'We do not assume today');
  expect(el.textContent).not.toContain('1 update logged');
  await set(el.querySelector('input[type=date]'),'2026-11-20');
  await act(async()=>btn(el,'Work out the next step').click());
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(JSON.parse(fetch.mock.calls[0][1].body).events).toEqual([{type:'reply',day:'2026-11-20',text:'will pay by friday'}]);
  expect(el.querySelector('textarea')).toBeNull();
  await act(async()=>btn(el,'They replied').click());
  expect(el.querySelector('textarea').value).toBe('');
 } finally {await act(async()=>root.unmount());el.remove();}
});
test('untouched local today default still logs, and a valid leap received-on date is preserved',async()=>{
 jest.useFakeTimers();jest.setSystemTime(new Date(2028,2,1,12));
 const {el,root}=await setup();
 try {
  expect(el.querySelector('input[type=date]').value).toBe('2028-03-01');
  await set(el.querySelector('input[type=date]'),'2028-02-29');
  await act(async()=>btn(el,'Work out the next step').click());
  expect(JSON.parse(fetch.mock.calls[0][1].body).events[0].day).toBe('2028-02-29');
 } finally {await act(async()=>root.unmount());el.remove();}
});
