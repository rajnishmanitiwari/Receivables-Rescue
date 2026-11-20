import React from "react";
import {createRoot} from "react-dom/client";
import {act} from "react-dom/test-utils";
import {MessageCard} from "./App";
global.IS_REACT_ACT_ENVIRONMENT=true;
const M={tier:"firm",tier_label:"Firm follow-up",customer:"Acme",invoice_no:"INV-33",amount:1000,days_overdue:38,subject:"Original subject",email:"OLD EMAIL",whatsapp:"OLD CHASE",to_email:"ap@acme.test",to_phone:"+919999999999"};
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject};};
const ok=value=>({ok:true,json:async()=>value});
const btn=(el,text)=>[...el.querySelectorAll('button')].find(x=>x.textContent.trim()===text);
const click=async(el,text)=>act(async()=>btn(el,text).click());
function setup(response){global.fetch=jest.fn(()=>response());const el=document.createElement('div');document.body.appendChild(el);const root=createRoot(el);act(()=>root.render(<MessageCard m={M} currency="INR"/>));act(()=>el.querySelector('.msg-head').click());return {el,root};}
const gone=el=>{expect(el.querySelector('.msg-text')).toBeNull();expect(el.querySelector('.msg-actions')).toBeNull();expect(btn(el,'Copy message')).toBeUndefined();};
const cleanup=async({root,el})=>{await act(async()=>root.unmount());el.remove();};
async function payment(el){await click(el,'Payment came in');await click(el,'Record payment');}
async function reply(el){await click(el,'They replied');const ta=el.querySelector('textarea');await act(async()=>{Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(ta,'Do not contact me again');ta.dispatchEvent(new Event('input',{bubbles:true}));});await click(el,'Work out the next step');}

test.each(['payment','reply'])('new %s hides the old draft and every send/copy action before response',async kind=>{const d=deferred();const c=setup(()=>d.promise);await(kind==='payment'?payment(c.el):reply(c.el));gone(c.el);expect(c.el.textContent).toContain('Checking next step');await act(async()=>d.resolve(ok({kind:'stop',reason:'contact opt-out recorded'})));gone(c.el);await cleanup(c);});

test('network failure stays closed; retry reuses the same event exactly once then shows only the current draft',async()=>{const d=deferred();let n=0;const c=setup(()=>++n===1?d.promise:Promise.resolve(ok({kind:'draft',tier:'firm',message:{tier:'firm',tier_label:'Firm follow-up',whatsapp:'NEW CHASE',email:'NEW EMAIL',subject:'NEW SUBJECT'}})));await payment(c.el);await act(async()=>d.reject(new Error('offline')));gone(c.el);expect(c.el.textContent).toContain('Next step unavailable');await click(c.el,'Retry next step');expect(c.el.querySelector('.msg-text').textContent).toBe('NEW CHASE');expect(JSON.parse(fetch.mock.calls[0][1].body).events).toEqual(JSON.parse(fetch.mock.calls[1][1].body).events);expect(c.el.querySelector('.fu-log').textContent).toBe('1 update logged this session.');await cleanup(c);});

test.each(['http','malformed'])('%s error never restores the original chase',async type=>{const c=setup(()=>Promise.resolve(type==='http'?{ok:false,json:async()=>({detail:'unavailable'})}:ok({})));await payment(c.el);gone(c.el);expect(btn(c.el,'Retry next step')).toBeDefined();await cleanup(c);});

test('collapse/reopen while pending or failed retains the gate and retry context',async()=>{const d=deferred();const c=setup(()=>d.promise);await payment(c.el);await act(async()=>c.el.querySelector('.msg-head').click());await act(async()=>c.el.querySelector('.msg-head').click());gone(c.el);expect(c.el.querySelector('.fu-log').textContent).toBe('1 update logged this session.');await act(async()=>d.reject(new Error('offline')));await act(async()=>c.el.querySelector('.msg-head').click());await act(async()=>c.el.querySelector('.msg-head').click());gone(c.el);expect(btn(c.el,'Retry next step')).toBeDefined();await cleanup(c);});

test('a previous ready plan is hidden immediately by a new payment and remains hidden on failure',async()=>{let n=0;const d=deferred();const c=setup(()=>++n===1?Promise.resolve(ok({kind:'hold',reason:'minimum gap'})):d.promise);await click(c.el,'I sent this message');expect(c.el.querySelector('.msg-text')).not.toBeNull();await payment(c.el);gone(c.el);await act(async()=>d.reject(new Error('offline')));gone(c.el);await cleanup(c);});

test('collapse/reopen preserves an accepted opt-out and its event history',async()=>{const c=setup(()=>Promise.resolve(ok({kind:'stop',reason:'contact opt-out recorded'})));await reply(c.el);await act(async()=>c.el.querySelector('.msg-head').click());await act(async()=>c.el.querySelector('.msg-head').click());gone(c.el);expect(c.el.querySelector('.fu-log').textContent).toBe('1 update logged this session.');await cleanup(c);});
