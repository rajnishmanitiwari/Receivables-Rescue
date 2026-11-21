import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import App, {FollowUp} from './App';
import {confirmedDueDate,localIso} from './promiseDate';
global.IS_REACT_ACT_ENVIRONMENT=true;
HTMLElement.prototype.scrollIntoView=jest.fn();
const btn=(el,t)=>[...el.querySelectorAll('button')].find(x=>x.textContent===t);
const ok=x=>({ok:true,json:async()=>x});
async function mount(m){const el=document.createElement('div');document.body.appendChild(el);const root=createRoot(el);await act(async()=>root.render(<FollowUp m={m}/>));return {el,root};}
async function done(c){await act(async()=>c.root.unmount());c.el.remove();}
const M={invoice_no:'INV-35',customer:'Acme',amount:5000,days_overdue:36,due_date:'2026-10-15',tier:'firm'};
afterEach(()=>jest.useRealTimers());

test('exact confirmed due survives timezone mismatch and a tab left open overnight',async()=>{jest.useFakeTimers();jest.setSystemTime(new Date(2026,10,21,1,30));global.fetch=jest.fn(async()=>ok({kind:'hold',reason:'minimum gap'}));const c=await mount(M);await act(async()=>btn(c.el,'I sent this message').click());let body=JSON.parse(fetch.mock.calls[0][1].body);expect(body.due).toBe('2026-10-15');expect(body.today).toBe('2026-11-21');jest.setSystemTime(new Date(2026,10,22,1,30));await act(async()=>btn(c.el,'I sent this message').click());body=JSON.parse(fetch.mock.calls[1][1].body);expect(body.due).toBe('2026-10-15');expect(body.today).toBe('2026-11-22');expect(body.events.map(e=>e.day)).toEqual(['2026-11-21','2026-11-22']);await done(c);});

test.each([undefined,'','2026-02-30','10/15/2026','2026-10-15T00:00:00Z'])('missing or invalid date %s never becomes today minus days late',async due_date=>{global.fetch=jest.fn();const c=await mount({...M,due_date});await act(async()=>btn(c.el,'I sent this message').click());expect(fetch).not.toHaveBeenCalled();expect(c.el.textContent).toContain('Generate a fresh chase with a confirmed due date');await done(c);});

test('analyse sends the browser local calendar day explicitly',async()=>{jest.useFakeTimers();jest.setSystemTime(new Date(2026,10,21,0,30));global.fetch=jest.fn(async url=>ok(String(url).includes('/health')?{upload:true}:String(url).includes('/extract')?{rows:[{customer:'Acme',amount:5000,due_date:'2026-10-15'}]}:{report:{priority:[],buckets:[],customers:[]},messages:[]}));const el=document.createElement('div');document.body.appendChild(el);const root=createRoot(el);await act(async()=>root.render(<App/>));const input=el.querySelector('input[type=file]');Object.defineProperty(input,'files',{value:[new File(['x'],'bill.csv')]});await act(async()=>input.dispatchEvent(new Event('change',{bubbles:true})));await act(async()=>btn(el,'Show me who to chase').click());const call=fetch.mock.calls.find(([url])=>String(url).includes('/analyse'));expect(JSON.parse(call[1].body).today).toBe(localIso(new Date()));await done({root,el});});

test('calendar validation preserves leap dates and rejects rollover dates',()=>{expect(confirmedDueDate('2028-02-29')).toBe('2028-02-29');expect(confirmedDueDate('2027-02-29')).toBeNull();expect(confirmedDueDate('2026-13-01')).toBeNull();});
