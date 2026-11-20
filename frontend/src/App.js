import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { applyPromiseDateToEvents, clearPromiseDateFromEvents, buildNextActionEvents, localIso, isOutlierDate } from "./promiseDate";
import { safeEmailAddress, buildMailto } from "./mailto";
import SAMPLE_ROWS from "./sample";

const API = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
const SYMBOLS = { INR: "₹", USD: "$", EUR: "€", GBP: "£", AED: "AED " };
const TIER_CLASS = { reminder: "t-ok", firm: "t-warn", escalation: "t-hot", final: "t-crit" };
const BLANK = { customer: "", invoice_no: "", amount: "", due_date: "", email: "", phone: "", confidence: "manual", date_assumed: false, date_assumed_reason: "" };

// Import notes about guessed dates are derived live from the rows, not kept
// as static strings: once a row is confirmed the note must not keep saying
// its bill is unscheduled while a chase draft sits below.
const GUESS_NOTE_MARKERS = ["could be read day-first or month-first", "unlabelled column and is unconfirmed"];

export function guessNotes(rows) {
  const out = [];
  const ambiguous = rows.filter((r) => r.date_assumed && r.date_assumed_reason === "ambiguous").length;
  if (ambiguous) out.push(
    ambiguous + " date(s) like 05/06/2026 could be read day-first or month-first. Shown as a guess, " +
    "unconfirmed; those bills are not scheduled for chasing. Confirm or fix the dates where you review them.");
  const ambComputed = rows.filter((r) => r.date_assumed && r.date_assumed_reason === "ambiguous-computed").length;
  if (ambComputed) out.push(
    ambComputed + " due date(s) were computed from an invoice date like 05/06/2026 that could be read day-first or " +
    "month-first, so the estimate could be a month off. Shown as a guess, unconfirmed; those bills are not " +
    "scheduled for chasing. Confirm or fix the dates where you review them.");
  const positional = rows.filter((r) => r.date_assumed && r.date_assumed_reason === "positional").length;
  if (positional) out.push(
    positional + " row(s) came without a header row, so the due date was read from an unlabelled column and " +
    "is unconfirmed. Those rows are not scheduled for chasing. Confirm or fix the dates where you review " +
    "them, or add a header row naming the due date column.");
  return out;
}

export function customerNotes(rows) {
  const missing = rows.filter((r) => !String(r.customer || "").trim()).length;
  if (!missing) return [];
  return [missing + " bill(s) have no customer name. Type who owes you in the review table; we never guess it."];
}

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

function money(n, cur = "INR") {
  const v = Math.round(Number(n) || 0);
  if (cur === "INR") {
    const s = String(Math.abs(v));
    let out = s;
    if (s.length > 3) {
      let head = s.slice(0, -3);
      const tail = s.slice(-3);
      const parts = [];
      while (head.length > 2) { parts.unshift(head.slice(-2)); head = head.slice(0, -2); }
      if (head) parts.unshift(head);
      out = parts.join(",") + "," + tail;
    }
    return (v < 0 ? "-" : "") + SYMBOLS.INR + out;
  }
  return (SYMBOLS[cur] || cur + " ") + v.toLocaleString("en-US");
}

export function rowsToCsv(rows) {
  const esc = (s) => '"' + String(s == null ? "" : s).replace(/"/g, "'") + '"';
  return "Customer,Invoice No,Amount,Due Date,Email,Phone\n" + rows
    .map((r) => [esc(r.customer), esc(r.invoice_no), Number(r.amount) || 0, esc(r.due_date), esc(r.email), esc(r.phone)].join(","))
    .join("\n");
}

// An assumed date only becomes real when the user edits or confirms it in the
// review table; untouched ones are sent blank so those bills stay unscheduled.
export function stripUnconfirmedDates(rows) {
  return rows.map((r) => (r.date_assumed ? { ...r, due_date: "" } : r));
}

/* ------------------------------------------------------------------ */

function Copy({ text, label = "Copy" }) {
  const [done, setDone] = useState(false);
  const onClick = async () => {
    try { await navigator.clipboard.writeText(text); }
    catch (e) {
      const ta = document.createElement("textarea");
      ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); } catch (e2) { /* no-op */ }
      document.body.removeChild(ta);
    }
    setDone(true); setTimeout(() => setDone(false), 1600);
  };
  return <button type="button" className="btn ghost sm" onClick={onClick}>{done ? "Copied" : label}</button>;
}

function Steps({ step }) {
  const items = ["Add your bills", "Check what we read", "See who to chase"];
  return (
    <ol className="steps" aria-label="Progress">
      {items.map((label, i) => {
        const n = i + 1;
        const state = step > n ? "done" : step === n ? "now" : "todo";
        return (
          <li key={label} className={"step " + state}>
            <span className="step-dot">{state === "done" ? "✓" : n}</span>
            <span className="step-label">{label}</span>
          </li>
        );
      })}
    </ol>
  );
}

function Drop({ onFiles, busy }) {
  const [over, setOver] = useState(false);
  const ref = useRef(null);
  return (
    <div
      className={"drop" + (over ? " over" : "") + (busy ? " busy" : "")}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); onFiles(Array.from(e.dataTransfer.files || [])); }}
      onClick={() => ref.current && ref.current.click()}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); ref.current.click(); } }}
      role="button"
      tabIndex={0}
      aria-label="Add invoice files"
    >
      <input
        ref={ref} type="file" multiple hidden
        accept=".pdf,.png,.jpg,.jpeg,.webp,.csv,.tsv,.txt"
        onChange={(e) => { onFiles(Array.from(e.target.files || [])); e.target.value = ""; }}
      />
      <div className="drop-icon" aria-hidden="true">
        <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6" /><path d="M12 18v-6" /><path d="m9 15 3-3 3 3" />
        </svg>
      </div>
      <div className="drop-title">{busy ? "Reading your bills…" : "Drop your unpaid bills here"}</div>
      <div className="drop-sub">
        A PDF of an invoice, or a spreadsheet. You can add several at once.
      </div>
    </div>
  );
}

export function ReviewTable({ rows, setRows, currency }) {
  const update = (i, key, val) => setRows(rows.map((r, n) => (n === i ? {
    ...r, [key]: val, ...(key === "due_date" ? { date_assumed: false } : {}),
    // Correcting a provisional name must not silently reuse the old party's contacts.
    ...(r.recipient_review_required && ["customer", "email", "phone"].includes(key) ? { recipient_unconfirmed: true } : {}),
    ...(key === "customer" && r.recipient_review_required ? { email: "", phone: "" } : {}),
  } : r)));
  const remove = (i) => setRows(rows.filter((_, n) => n !== i));
  const total = rows.reduce((s, r) => s + (Number(r.amount) || 0), 0);
  return (
    <div className="review">
      <div className="review-scroll">
        <table className="review-table">
          <thead>
            <tr>
              <th>Who owes you</th><th>Bill no.</th><th className="r">Amount</th>
              <th>Was due on</th><th>Email</th><th>Phone</th><th aria-label="Remove" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className={r.confidence === "low" ? "shaky" : ""}>
                <td><input className={String(r.customer || "").trim() ? undefined : "need"} value={r.customer} onChange={(e) => update(i, "customer", e.target.value)} placeholder="Customer name" />
                  {r.recipient_unconfirmed ? <div className="recipient-check">
                    <p>Check this is who owes you, not the seller or shipping party. PDF layout can mix them up.</p>
                    <p><strong>{r.customer || "No name"}</strong><br />Email: {r.email || "None"}<br />Phone: {r.phone || "None"}</p>
                    <button type="button" className="btn ghost sm" disabled={!String(r.customer || "").trim()} onClick={() => update(i, "recipient_unconfirmed", false)}>Confirm name and contacts</button>
                  </div> : null}
                </td>
                <td><input className="w-sm" value={r.invoice_no} onChange={(e) => update(i, "invoice_no", e.target.value)} placeholder="-" /></td>
                <td><input className="w-sm num" inputMode="decimal" value={r.amount} onChange={(e) => update(i, "amount", e.target.value)} placeholder="0" /></td>
                <td>
                  <input className="w-md" type="date" value={r.due_date || ""} onChange={(e) => update(i, "due_date", e.target.value)} />
                  {r.date_assumed ? <button type="button" className="assumed" onClick={() => update(i, "date_assumed", false)}>We estimated this date. Tap to confirm, or fix it.</button> : null}
                </td>
                <td><input value={r.email} onChange={(e) => update(i, "email", e.target.value)} placeholder="-" /></td>
                <td><input className="w-md" value={r.phone} onChange={(e) => update(i, "phone", e.target.value)} placeholder="-" /></td>
                <td><button type="button" className="x" onClick={() => remove(i)} aria-label={"Remove row " + (i + 1)}>&times;</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="review-foot">
        <button type="button" className="btn ghost sm" onClick={() => setRows([...rows, { ...BLANK }])}>+ Add a row</button>
        <div className="review-total">{plural(rows.length, "bill", "bills")} &middot; <strong>{money(total, currency)}</strong> total</div>
      </div>
    </div>
  );
}

export function Aging({ buckets, currency }) {
  const max = Math.max(...buckets.map((b) => b.amount), 1);
  return (
    <div className="aging">
      {buckets.map((b) => (
        <div className="aging-row" key={b.bucket}>
          <div className="aging-name">{b.bucket}</div>
          <div className="aging-track">
            <div
              className={"aging-bar " + (b.probability == null ? "b-neutral" : b.bucket.indexOf("Not") === 0 ? "b-ok" : b.probability >= 74 ? "b-warn" : "b-crit")}
              style={{ width: Math.max(2, (b.amount / max) * 100) + "%" }}
            />
          </div>
          <div className="aging-amt">{money(b.amount, currency)}</div>
        </div>
      ))}
    </div>
  );
}

const KIND_PRESENT = {
  draft:      { label: "Send a follow-up", cls: "t-ok" },
  hold:       { label: "Wait",             cls: "t-warn" },
  pause:      { label: "Pause chasing",    cls: "t-crit" },
  stop:       { label: "Stop chasing",     cls: "t-crit" },
  human:      { label: "Needs your call",  cls: "t-hot" },
  none:       { label: "Nothing to do",    cls: "t-ok" },
};

export function FollowUp({ m, sender, company, currency, onDecision }) {
  const [events, setEvents] = useState([]);
  const [decision, setDecision] = useState(null);
  const [replyOpen, setReplyOpen] = useState(false);
  const [payOpen, setPayOpen] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [editDate, setEditDate] = useState("");
  const [editingDate, setEditingDate] = useState(false);
  const [dismissedSug, setDismissedSug] = useState("");
  const [payAmount, setPayAmount] = useState(String(m.amount || ""));
  const [reconOpen, setReconOpen] = useState(false);
  const [reconNote, setReconNote] = useState("");
  const [reconAttest, setReconAttest] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const decide = useCallback(async (nextEvents) => {
    if (m.days_overdue == null) {
      // No confirmed due date: never invent one (due=today) for the planner.
      setErr("Confirm this bill's due date before planning the next step.");
      return;
    }
    setBusy(true); setErr("");
    const today = new Date();
    const iso = localIso;
    const due = new Date(today);
    due.setDate(due.getDate() - (Number(m.days_overdue) || 0));  // calendar days: DST-safe
    try {
      const res = await fetch(API + "/api/next-action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          number: (m.invoice_no || m.customer || "invoice").slice(0, 60),
          amount: Number(m.amount) || 1,
          due: iso(due),
          today: iso(today),
          customer: (m.customer || "").slice(0, 120),
          email: (m.to_email || "").slice(0, 200),
          phone: (m.to_phone || "").slice(0, 40),
          sender: (sender || "").slice(0, 80),
          company: (company || "").slice(0, 80),
          currency: currency || "INR",
          events: buildNextActionEvents(nextEvents, iso(today)),
        }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(json.detail || "The follow-up helper is unavailable right now.");
      setDecision(json);
      if (onDecision) onDecision(json);
    } catch (e2) {
      setErr(e2.message || "The follow-up helper is unavailable right now.");
    } finally { setBusy(false); }
  }, [m, sender, company, currency, onDecision]);

  const nextEventId = useRef(1);
  // The day a reply was actually received, editable: pasting a reply today
  // does not mean the customer wrote it today. Defaults to local today.
  const [replyDay, setReplyDay] = useState(() => localIso(new Date()));
  const log = (e) => {
    const day = e.type === "reply" ? replyDay : localIso(new Date());
    if (day > localIso(new Date())) { setErr("The reply date cannot be in the future."); return; }
    const next = [...events, { ...e, id: nextEventId.current++, day }];
    setEvents(next);
    decide(next);
  };

  // A suggested promise date is only ever advisory: nothing changes in the plan
  // until the user confirms or edits it. Confirm/change sets an explicit
  // promise_date on the specific reply it belongs to; Remove strips it again.
  // A newer reply never inherits or loses the date by position: the confirmed
  // date stays on the event it was confirmed on, and at most one reply carries
  // a date at any time.
  const [editTarget, setEditTarget] = useState(null);
  // Far-future dates get one explicit extra confirmation; never a silent cap.
  const [pendingOutlier, setPendingOutlier] = useState(null);
  const applyPromiseDate = (dstr, targetId, skipOutlierCheck) => {
    const outlierDays = skipOutlierCheck ? 0 : isOutlierDate(dstr, localIso(new Date()));
    if (outlierDays) { setPendingOutlier({ dstr, targetId, days: outlierDays }); return; }
    const next = applyPromiseDateToEvents(events, dstr, targetId);
    setEvents(next); decide(next); setEditingDate(false); setEditTarget(null); setPendingOutlier(null);
  };
  const clearPromiseDate = (targetId) => {
    const next = clearPromiseDateFromEvents(events, targetId);
    setEvents(next); decide(next);
  };

  const sug = decision && decision.suggested_promise_date ? decision.suggested_promise_date : null;
  const sugKey = sug ? sug.date + "|" + sug.phrase + "|" + sug.reply_day : "";
  const todayIso = localIso(new Date());
  // The server echoes which reply it read (reply_index into the events we sent).
  // Confirm onto that exact event only when it still matches the suggestion's
  // reply_day and phrase; any mismatch means no confirmation, never a guess.
  const sugReply = (() => {
    if (!sug || !Number.isInteger(sug.reply_index)) return null;
    const ev = events[sug.reply_index];
    if (!ev || ev.type !== "reply") return null;
    if ((ev.day || todayIso) !== sug.reply_day) return null;
    if (!ev.text || !ev.text.toLowerCase().includes(String(sug.phrase || "").toLowerCase())) return null;
    return ev;
  })();
  const promisedReply = [...events].reverse().find((e) => e.type === "reply" && e.promise_date);

  const present = decision ? KIND_PRESENT[decision.kind] || KIND_PRESENT.none : null;
  return (
    <div className="followup">
      <div className="fu-head">
        <strong>What happened since?</strong>
        <span className="hint">A fixed set of rules suggests the next step. This session only: nothing is saved, and nothing is sent for you.</span>
      </div>
      <div className="fu-actions">
        <button type="button" className="btn ghost sm" disabled={busy}
          onClick={() => log({ type: "sent", tier: m.tier })}>I sent this message</button>
        <button type="button" className="btn ghost sm" disabled={busy}
          onClick={() => { setReplyOpen(!replyOpen); setPayOpen(false); }}>They replied</button>
        <button type="button" className="btn ghost sm" disabled={busy}
          onClick={() => { setPayOpen(!payOpen); setReplyOpen(false); }}>Payment came in</button>
      </div>
      {replyOpen ? (
        <div className="fu-box">
          <label htmlFor={"fu-reply-" + m.invoice_no}>Paste their reply</label>
          <textarea id={"fu-reply-" + m.invoice_no} rows={3} value={replyText}
            onChange={(e) => setReplyText(e.target.value)}
            placeholder="e.g. Will pay by Friday, or We never received the goods" />
          <label htmlFor={"fu-rday-" + m.invoice_no}>Reply received on</label>
          <input id={"fu-rday-" + m.invoice_no} type="date" value={replyDay}
            max={localIso(new Date())}
            onChange={(e) => setReplyDay(e.target.value)} />
          <button type="button" className="btn primary sm" disabled={busy || !replyText.trim()}
            onClick={() => { log({ type: "reply", text: replyText }); setReplyText(""); setReplyOpen(false); }}>
            Work out the next step
          </button>
        </div>
      ) : null}
      {payOpen ? (
        <div className="fu-box">
          <label htmlFor={"fu-pay-" + m.invoice_no}>Amount received</label>
          <input id={"fu-pay-" + m.invoice_no} inputMode="decimal" value={payAmount}
            onChange={(e) => setPayAmount(e.target.value)} />
          <button type="button" className="btn primary sm" disabled={busy || !(Number(payAmount) > 0)}
            onClick={() => { log({ type: "payment", amount: Number(payAmount) }); setPayOpen(false); }}>
            Record payment
          </button>
        </div>
      ) : null}
      {err ? <div className="error" role="alert">{err}</div> : null}
      {decision && present ? (
        <div className={"fu-decision"}>
          <span className={"tier " + present.cls}>{present.label}{decision.tier && decision.kind === "draft" ? ": " + decision.tier : ""}</span>
          <span className="fu-reason">
            {decision.reason}{decision.until ? ", until " + decision.until : ""}
          </span>
        </div>
      ) : null}
      {decision && (decision.kind === "pause" ||
        (decision.kind === "human" && /dispute|not understood/.test(decision.reason || ""))) ? (
        <div className="fu-box">
          <span className="fu-suggest-text">
            If you have looked into this yourself and closed it out, mark it reviewed (dated today).
          </span>
          <span className="fu-suggest-actions">
            <button type="button" className="btn ghost sm" disabled={busy}
              onClick={() => log({ type: "resolved" })}>I reviewed this</button>
          </span>
        </div>
      ) : null}
      {decision && decision.kind === "stop" && /opt-out/.test(decision.reason || "") ? (
        <div className="fu-box">
          {!reconOpen ? (
            <span className="fu-suggest-actions">
              <button type="button" className="btn ghost sm" disabled={busy}
                onClick={() => setReconOpen(true)}>They asked to hear from you again</button>
            </span>
          ) : (
            <div>
              <label className="fu-check">
                <input type="checkbox" checked={reconAttest}
                  onChange={(e) => setReconAttest(e.target.checked)} />
                The contact asked to be contacted again (in writing or a reply).
              </label>
              <label htmlFor={"fu-recon-" + m.invoice_no}>Note (optional, kept in this session only)</label>
              <input id={"fu-recon-" + m.invoice_no} type="text" value={reconNote}
                onChange={(e) => setReconNote(e.target.value)}
                placeholder="e.g. Called on the 15th, happy to get reminders" />
              <span className="fu-suggest-actions">
                <button type="button" className="btn primary sm" disabled={busy || !reconAttest}
                  onClick={() => { log({ type: "reconsent", text: reconNote.trim() || undefined }); setReconOpen(false); setReconNote(""); setReconAttest(false); }}>
                  Record re-consent
                </button>
                <button type="button" className="btn ghost sm" disabled={busy}
                  onClick={() => { setReconOpen(false); setReconAttest(false); }}>Cancel</button>
              </span>
              <span className="hint">
                Only record this if it actually happened. DueRise records what you tell it - when and whether to write again stays your call.
              </span>
            </div>
          )}
        </div>
      ) : null}
      {sug && sugReply && dismissedSug !== sugKey ? (
        <div className="fu-suggest">
          <span className="fu-suggest-text">
            We read “{sug.phrase}” as <strong>{sug.date}</strong>, assuming the reply was
            received {sug.reply_day} (the date you logged). Nothing changes until you
            confirm. You can also pick another date.
          </span>
          <span className="fu-suggest-actions">
            <button type="button" className="btn primary sm" disabled={busy || !sugReply}
              onClick={() => applyPromiseDate(sug.date, sugReply && sugReply.id)}>Use {sug.date}</button>
            <button type="button" className="btn ghost sm" disabled={busy || !sugReply}
              onClick={() => { setEditingDate(true); setEditDate(sug.date); setEditTarget(sugReply && sugReply.id); }}>Pick another date</button>
            <button type="button" className="btn ghost sm" disabled={busy}
              onClick={() => { setDismissedSug(sugKey); setEditingDate(false); }}>Dismiss</button>
          </span>
        </div>
      ) : null}
      {!sug && decision && decision.kind === "hold" && promisedReply ? (
        <div className="fu-suggest">
          <span className="fu-suggest-text">
            Promised date <strong>{promisedReply.promise_date}</strong> is in use for this plan.
          </span>
          <span className="fu-suggest-actions">
            <button type="button" className="btn ghost sm" disabled={busy}
              onClick={() => { setEditingDate(true); setEditDate(promisedReply.promise_date); setEditTarget(promisedReply.id); }}>Change</button>
            <button type="button" className="btn ghost sm" disabled={busy}
              onClick={() => clearPromiseDate(promisedReply.id)}>Remove</button>
          </span>
        </div>
      ) : null}
      {editingDate ? (
        <div className="fu-box">
          <label htmlFor={"fu-pdate-" + m.invoice_no}>Promised payment date</label>
          <input id={"fu-pdate-" + m.invoice_no} type="date" value={editDate}
            onChange={(e) => setEditDate(e.target.value)} />
          <span className="fu-suggest-actions">
            <button type="button" className="btn primary sm" disabled={busy || !editDate}
              onClick={() => applyPromiseDate(editDate, editTarget)}>Set date</button>
            <button type="button" className="btn ghost sm" disabled={busy}
              onClick={() => { setEditingDate(false); setEditTarget(null); }}>Cancel</button>
          </span>
        </div>
      ) : null}
      {pendingOutlier ? (
        <div className="fu-box">
          <span className="fu-suggest-text">
            That puts follow-ups on hold for <strong>{pendingOutlier.days} days</strong>, until{" "}
            <strong>{pendingOutlier.dstr}</strong>. Use this date?
          </span>
          <span className="fu-suggest-actions">
            <button type="button" className="btn primary sm" disabled={busy}
              onClick={() => applyPromiseDate(pendingOutlier.dstr, pendingOutlier.targetId, true)}>Use {pendingOutlier.dstr}</button>
            <button type="button" className="btn ghost sm" disabled={busy}
              onClick={() => setPendingOutlier(null)}>Cancel</button>
          </span>
        </div>
      ) : null}
      {events.length ? (
        <div className="fu-log">{plural(events.length, "update", "updates")} logged this session.</div>
      ) : null}
    </div>
  );
}

export function MessageCard({ m, currency, sender, company }) {
  const [open, setOpen] = useState(false);
  const [channel, setChannel] = useState("whatsapp");
  const [fuDecision, setFuDecision] = useState(null);
  // The card shows the CURRENT plan's draft: after a new decision with a
  // message, that message (and its tier) replaces the original analysis one.
  const dm = fuDecision && fuDecision.message && (fuDecision.kind === "draft" || fuDecision.kind === "hold") ? fuDecision.message : null;
  const blocked = fuDecision && (fuDecision.kind === "stop" || fuDecision.kind === "pause" || fuDecision.kind === "human" || fuDecision.kind === "none");
  const curSubject = dm ? dm.subject : m.subject;
  const curWhatsapp = dm ? dm.whatsapp : m.whatsapp;
  const curEmail = dm ? dm.email : m.email;
  const body = channel === "email" ? curEmail : curWhatsapp;
  const wa = m.to_phone ? "https://wa.me/" + m.to_phone.replace(/[^0-9]/g, "") + "?text=" + encodeURIComponent(curWhatsapp) : null;
  // Accept exactly one well-formed address; anything with control chars, query
  // separators or extra recipients is dropped instead of interpolated.
  const safeEmail = safeEmailAddress(m.to_email);
  const mailto = buildMailto({ ...m, subject: curSubject, email: curEmail });
  const badge = blocked ? KIND_PRESENT[fuDecision.kind] : null;
  return (
    <div className={"msg" + (open ? " open" : "")}>
      <button type="button" className="msg-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className={"tier " + (badge ? badge.cls : TIER_CLASS[dm ? dm.tier : m.tier])}>{badge ? badge.label : (dm ? dm.tier_label : m.tier_label)}</span>
        <span className="msg-cust">{m.customer}</span>
        <span className="msg-meta">
          {m.invoice_no ? m.invoice_no + " · " : ""}{money(m.amount, currency)}
          {" · "}{m.days_overdue > 0 ? m.days_overdue + " days late" : "not late yet"}
        </span>
        <span className="chev" aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      {open ? (
        <div className="msg-body">
          {blocked ? (
            <p className="hint">No message to send while this one is {fuDecision.kind === "stop" ? "stopped" : fuDecision.kind === "pause" ? "paused" : fuDecision.kind === "none" ? "settled" : "waiting on your call"} - the plan below says why.</p>
          ) : (
            <>
              <p className="msg-why">{dm ? dm.why : m.why}</p>
              <div className="tabs" role="tablist">
                <button type="button" role="tab" aria-selected={channel === "whatsapp"} className={channel === "whatsapp" ? "tab on" : "tab"} onClick={() => setChannel("whatsapp")}>WhatsApp</button>
                <button type="button" role="tab" aria-selected={channel === "email"} className={channel === "email" ? "tab on" : "tab"} onClick={() => setChannel("email")}>Email</button>
              </div>
              {channel === "email" ? <div className="subject"><strong>Subject:</strong> {curSubject}</div> : null}
              <pre className="msg-text">{body}</pre>
              <div className="msg-actions">
                <Copy text={channel === "email" ? curSubject + "\n\n" + curEmail : curWhatsapp} label="Copy message" />
                {channel === "email" && mailto ? <a className="btn ghost sm" href={mailto}>Open in email</a> : null}
                {channel === "whatsapp" && wa ? <a className="btn primary sm" href={wa} target="_blank" rel="noreferrer">Send on WhatsApp</a> : null}
                {!safeEmail && !m.to_phone ? <span className="hint">No email or phone saved for this one.</span> : null}
              </div>
            </>
          )}
          <FollowUp m={m} sender={sender} company={company} currency={currency} onDecision={setFuDecision} />
        </div>
      ) : null}
    </div>
  );
}

export default function App() {
  const [rows, setRows] = useState([]);
  const [notes, setNotes] = useState([]);
  const [reading, setReading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [showPaste, setShowPaste] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [showAssume, setShowAssume] = useState(false);
  const [paste, setPaste] = useState("");
  const [caps, setCaps] = useState({ vision: false, pdf: true, upload: true });

  const [currency, setCurrency] = useState("INR");
  const [sender, setSender] = useState("");
  const [company, setCompany] = useState("");

  const resultRef = useRef(null);
  const reviewRef = useRef(null);
  const step = result ? 3 : rows.length ? 2 : 1;

  useEffect(() => {
    fetch(API + "/api/health").then((r) => r.json())
      .then((h) => {
        setCaps(h);
        if (h.upload === false) setShowPaste(true);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (result && resultRef.current) resultRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [result]);

  const addFiles = useCallback(async (files) => {
    if (!files.length) return;
    setReading(true); setError(""); setResult(null);
    const fd = new FormData();
    files.slice(0, 12).forEach((f) => fd.append("files", f));
    try {
      const res = await fetch(API + "/api/extract", { method: "POST", body: fd });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(json.detail || "Those files could not be read.");
      const got = (json.rows || []).map((r) => {
        // Source fallback also gates document rows during a rolling API update.
        const documentRecipient = r.recipient_review_required || /\.(pdf|png|jpe?g|webp|heic)$/i.test(r.source || "");
        return { ...BLANK, ...r, amount: r.amount == null ? "" : r.amount, due_date: r.due_date || "",
          ...(documentRecipient ? { recipient_review_required: true, recipient_unconfirmed: true } : {}) };
      });
      setRows((prev) => [...prev, ...got]);
      // Guessed-date notes are derived from the live rows (see guessNotes);
      // keeping the static strings would leave a stale "not scheduled"
      // warning after the user confirms the date.
      setNotes((json.notes || []).filter((n) => !GUESS_NOTE_MARKERS.some((m) => n.includes(m))));
      if (!got.length && !(json.notes || []).length) setNotes(["Nothing readable was found in those files."]);
      if (got.length && reviewRef.current) setTimeout(() => reviewRef.current.scrollIntoView({ behavior: "smooth", block: "start" }), 120);
    } catch (err) {
      setError(err.message || "Those files could not be read.");
    } finally {
      setReading(false);
    }
  }, []);

  const usePaste = async () => {
    if (!paste.trim()) return;
    setReading(true); setError("");
    const blob = new Blob([paste], { type: "text/csv" });
    await addFiles([new File([blob], "pasted.csv", { type: "text/csv" })]);
    setPaste(""); setShowPaste(false);
  };

  const run = useCallback(async () => {
    const clean = rows.filter((r) => Number(r.amount) > 0);
    if (!clean.length) { setError("Add at least one bill with an amount."); return; }
    const missingCustomer = clean.filter((r) => !String(r.customer || "").trim()).length;
    if (missingCustomer) {
      setError(missingCustomer + " bill(s) have no customer name. Type who owes you in the review table; we never guess it.");
      return;
    }
    if (clean.some((r) => r.recipient_unconfirmed)) {
      setError("Check and confirm the name and contacts on each PDF or photo bill before generating a chase.");
      return;
    }
    setBusy(true); setError(""); setResult(null);
    try {
      const unconfirmed = clean.filter((r) => r.date_assumed).length;
      const res = await fetch(API + "/api/analyse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          data: rowsToCsv(stripUnconfirmedDates(clean)), currency, sender_name: sender, company_name: company,
          bank_rate: null,
        }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(json.detail || "Something went wrong reading those rows.");
      if (unconfirmed) json.warnings = [...(json.warnings || []),
        unconfirmed + " assumed due date(s) were not confirmed, so those bills stay unscheduled. Confirm or enter their dates to chase them."];
      setResult(json);
    } catch (err) {
      setError(err.message || "Something went wrong. Try again.");
    } finally { setBusy(false); }
  }, [rows, currency, sender, company]);

  const rep = result && result.report;
  const overdueRows = rep ? rep.priority.filter((p) => p.days_overdue > 0) : [];
  const overdueTotal = overdueRows.reduce((sum, p) => sum + p.amount, 0);
  const overdueCount = overdueRows.length;
  const late90Total = overdueRows.filter((p) => p.days_overdue > 90).reduce((sum, p) => sum + p.amount, 0);
  const unknownDates = rep ? rep.priority.filter((p) => p.days_overdue == null).length : 0;
  const oldestDays = rep ? Math.max(0, ...rep.priority.map((p) => p.days_overdue)) : 0;

  const csvOut = useMemo(() => {
    if (!rep) return "";
    const head = "Rank,Customer,Invoice,Amount,Due date,Days late,Bucket,Chance of collection %,Cost of waiting 30d,Statutory interest,Action\n";
    return head + rep.priority.map((p) => [
      p.rank, '"' + String(p.customer).replace(/"/g, "'") + '"', '"' + String(p.invoice_no || "").replace(/"/g, "'") + '"',
      p.amount, p.due_date || "", p.days_overdue ?? "", '"' + p.bucket + '"', p.probability ?? "", p.slip_30d ?? "",
      p.statutory_interest || 0, p.tier,
    ].join(",")).join("\n");
  }, [rep]);

  const download = () => {
    const blob = new Blob([csvOut], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "chase-list.csv";
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const shareText = rep
    ? "I ran my unpaid bills through DueRise: " + money(rep.total_outstanding, currency)
      + " outstanding, and " + money(rep.cost_of_waiting_30d, currency)
      + " of it quietly disappears if I do nothing for 30 days. Free, no signup."
    : "";

  // The missing-customer gate error retires as soon as every row has a name.
  useEffect(() => {
    if (error && error.includes("no customer name") && !customerNotes(rows).length) setError("");
    if (error && error.startsWith("Check and confirm the name and contacts") && !rows.some((r) => Number(r.amount) > 0 && r.recipient_unconfirmed)) setError("");
    if (rows.some((r) => r.recipient_unconfirmed)) setResult(null);
  }, [rows]);  // eslint-disable-line react-hooks/exhaustive-deps
  const reset = () => { setRows([]); setResult(null); setNotes([]); setError(""); };

  return (
    <div className="page">
      <header className="topbar">
        <div className="wrap bar">
          <div className="logo"><span className="dot" aria-hidden="true" />DueRise</div>
          {rows.length || result ? (
            <button type="button" className="btn ghost sm" onClick={reset}>Start over</button>
          ) : null}
        </div>
      </header>

      <main className="wrap">
        <div className="intro">
          <h1>Find the money you are already owed.</h1>
          <p>Add your unpaid bills. See who to chase first, how late each one is, and get a
             reminder ready to send. Nothing is kept between visits, and there is no sign-up.</p>
        </div>

        <Steps step={step} />

        <section className="card">
          {caps.upload === false ? (
            <div className="upload-off">
              <strong>File uploads are unavailable on this server right now.</strong>
              <span>Type or paste your bills below instead. Everything else works normally.</span>
            </div>
          ) : (
            <Drop onFiles={addFiles} busy={reading} />
          )}
          <div className="alt">
            <button type="button" className="btn link" onClick={() => setShowPaste(!showPaste)}>
              {showPaste ? "Hide typing box" : "Type or paste them instead"}
            </button>
            {rows.length ? null : (
              <>
                <span className="sep" aria-hidden="true">&middot;</span>
                <button type="button" className="btn link" onClick={() => { setRows(SAMPLE_ROWS.map((r) => ({ ...BLANK, ...r }))); setNotes([]); setResult(null); }}>
                  Try it with example bills
                </button>
              </>
            )}
          </div>
          {showPaste ? (
            <div className="paste">
              <label htmlFor="paste">One bill per line: who owes you, bill number, amount, date it was due.</label>
              <textarea
                id="paste" rows={5} value={paste} spellCheck={false}
                onChange={(e) => setPaste(e.target.value)}
                placeholder={"Acme Traders, INV-2041, 425000, 2026-04-21\nBluepeak Logistics, INV-2044, 186500, 2026-06-14"}
              />
              <button type="button" className="btn ghost" onClick={usePaste} disabled={reading || !paste.trim()}>Add these</button>
            </div>
          ) : null}
          {[...notes, ...guessNotes(rows), ...customerNotes(rows)].length ? <div className="notes">{[...notes, ...guessNotes(rows), ...customerNotes(rows)].map((n, i) => <div key={i}>{n}</div>)}</div> : null}
          {!caps.vision && caps.upload !== false ? (
            <p className="cap-note">
              PDF bills are read automatically. Photos of paper bills need the AI reader turned on.
              Until then, type those in or paste them.
            </p>
          ) : null}
        </section>

        {rows.length ? (
          <section className="card" ref={reviewRef}>
            <div className="card-head">
              <h2>Check what we read</h2>
              <p>Fix anything that looks wrong before we work it out. Nothing here is sent anywhere.</p>
            </div>
            <ReviewTable rows={rows} setRows={setRows} currency={currency} />

            <button type="button" className="disclosure" onClick={() => setShowDetails(!showDetails)} aria-expanded={showDetails}>
              {showDetails ? "−" : "+"} Your details and currency
            </button>
            {showDetails ? (
              <div className="details">
                <div className="field">
                  <label htmlFor="sender">Your name</label>
                  <input id="sender" value={sender} onChange={(e) => setSender(e.target.value)} placeholder="Damini" />
                </div>
                <div className="field">
                  <label htmlFor="company">Your business</label>
                  <input id="company" value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Nyneso" />
                </div>
                <div className="field">
                  <label htmlFor="cur">Currency</label>
                  <select id="cur" value={currency} onChange={(e) => setCurrency(e.target.value)}>
                    <option value="INR">Indian Rupee</option>
                    <option value="USD">US Dollar</option>
                    <option value="EUR">Euro</option>
                    <option value="GBP">Pound</option>
                    <option value="AED">UAE Dirham</option>
                  </select>
                </div>
                
              </div>
            ) : null}

            {error ? <div className="error" role="alert">{error}</div> : null}
            <button type="button" className="btn primary big" onClick={run} disabled={busy}>
              {busy ? "Working it out…" : "Show me who to chase"}
            </button>
          </section>
        ) : error ? (
          <div className="error standalone" role="alert">{error}</div>
        ) : null}

        {rep ? (
          <div ref={resultRef}>
            {result.warnings && result.warnings.length ? (
              <div className="notes">{result.warnings.map((w, i) => <div key={i}>{w}</div>)}</div>
            ) : null}

            <section className="stats">
              <div className="stat">
                <div className="stat-label">You are owed</div>
                <div className="stat-value">{money(rep.total_outstanding, currency)}</div>
                <div className="stat-sub">{plural(rep.invoice_count, "bill", "bills")} &middot; {plural(rep.customer_count, "customer", "customers")}</div>
              </div>
              <div className="stat good">
                <div className="stat-label">Past due</div>
                <div className="stat-value">{money(overdueTotal, currency)}</div>
                <div className="stat-sub">{plural(overdueCount, "bill", "bills")} past their due date{unknownDates ? " · " + plural(unknownDates, "bill", "bills") + " with unknown dates" : ""}</div>
              </div>
              <div className="stat bad">
                <div className="stat-label">Over 90 days late</div>
                <div className="stat-value">{money(late90Total, currency)}</div>
                <div className="stat-sub">{oldestDays > 0 ? "Oldest bill: " + oldestDays + " days late" : unknownDates ? "Lateness unknown for " + plural(unknownDates, "bill", "bills") : "Nothing overdue yet"}</div>
              </div>
            </section>

            {rep.statutory_interest_total > 0 ? (
              <section className="card msme-card">
                <h2>Possible late-payment interest (estimate)</h2>
                <p className="msme-figure">{money(rep.statutory_interest_total, currency)}</p>
                <p>
                  Under the MSMED Act, a buyer who pays a registered micro or small business late
                  may owe compound interest at <strong>{rep.statutory_rate}% a year</strong> - three times
                  the RBI Bank Rate. Whether that applies to you depends on your registration and
                  your buyers; this figure is an estimate, not an entitlement.
                </p>
                <p className="fineprint">{rep.assumptions.msmed.note}</p>
              </section>
            ) : null}

            {rep.risks && rep.risks.length ? (
              <section className="card">
                <h2>What is actually wrong</h2>
                <ul className="risks">{rep.risks.map((r, i) => <li key={i}>{r}</li>)}</ul>
              </section>
            ) : null}

            <section className="card">
              <h2>Where your money is sitting</h2>
              <Aging buckets={rep.buckets} currency={currency} />
              <button type="button" className="disclosure" onClick={() => setShowAssume(!showAssume)} aria-expanded={showAssume}>
                {showAssume ? "−" : "+"} The collection assumptions behind this view
              </button>
              {showAssume ? (
                <div className="assume">
                  <p>{rep.assumptions.note}</p>
                  <div className="curve">
                    {rep.assumptions.curve.map((c, i) => (
                      <span key={i}>{c.days_past_due} days &rarr; {c.collected}%</span>
                    ))}
                  </div>
                </div>
              ) : null}
            </section>

            <section className="card">
              <div className="card-head row-head">
                <div>
                  <h2>Chase these first</h2>
                  <p>{rep.ranking_basis || "Ranked by urgency: how much is owed and how late each bill is, under a standard aging assumption."} Open any row for a message you can send now.</p>
                </div>
                <div className="head-actions">
                  <button type="button" className="btn ghost sm" onClick={download}>Download list</button>
                  <Copy text={shareText} label="Copy share text" />
                </div>
              </div>
              <div className="msgs">
                {result.messages.map((m, i) => <MessageCard key={i} m={m} currency={currency} sender={sender} company={company} />)}
              </div>
            </section>

            <section className="card">
              <h2>By customer</h2>
              <div className="review-scroll">
                <table className="data">
                  <thead>
                    <tr><th>Customer</th><th className="r">Owed</th><th className="r">Bills</th><th className="r">Oldest</th><th className="r">Share</th></tr>
                  </thead>
                  <tbody>
                    {rep.customers.map((c) => (
                      <tr key={c.customer}>
                        <td>{c.customer}</td>
                        <td className="r">{money(c.amount, currency)}</td>
                        <td className="r">{c.count}</td>
                        <td className="r">{c.oldest_days > 0 ? c.oldest_days + "d" : "-"}</td>
                        <td className="r">{c.share}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        ) : null}
      </main>


      <footer className="wrap foot">
        <p>
          This app processes your bills to build this page and does not save them; nothing you
          enter is kept for a next visit. DueRise is not legal, accounting or debt-collection advice.
        </p>
      </footer>
    </div>
  );
}
