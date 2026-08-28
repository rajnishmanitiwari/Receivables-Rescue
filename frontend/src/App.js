import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import SAMPLE_ROWS from "./sample";

const API = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
const SYMBOLS = { INR: "₹", USD: "$", EUR: "€", GBP: "£", AED: "AED " };
const TIER_CLASS = { reminder: "t-ok", firm: "t-warn", escalation: "t-hot", final: "t-crit" };
const BLANK = { customer: "", invoice_no: "", amount: "", due_date: "", email: "", phone: "", confidence: "manual" };

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

function rowsToCsv(rows) {
  const esc = (s) => '"' + String(s == null ? "" : s).replace(/"/g, "'") + '"';
  return "Customer,Invoice No,Amount,Due Date,Email,Phone\n" + rows
    .map((r) => [esc(r.customer), esc(r.invoice_no), Number(r.amount) || 0, esc(r.due_date), esc(r.email), esc(r.phone)].join(","))
    .join("\n");
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
        A photo of an invoice, a PDF, or a spreadsheet. You can add several at once.
      </div>
    </div>
  );
}

function ReviewTable({ rows, setRows, currency }) {
  const update = (i, key, val) => setRows(rows.map((r, n) => (n === i ? { ...r, [key]: val } : r)));
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
                <td><input value={r.customer} onChange={(e) => update(i, "customer", e.target.value)} placeholder="Customer name" /></td>
                <td><input className="w-sm" value={r.invoice_no} onChange={(e) => update(i, "invoice_no", e.target.value)} placeholder="—" /></td>
                <td><input className="w-sm num" inputMode="decimal" value={r.amount} onChange={(e) => update(i, "amount", e.target.value)} placeholder="0" /></td>
                <td><input className="w-md" type="date" value={r.due_date || ""} onChange={(e) => update(i, "due_date", e.target.value)} /></td>
                <td><input value={r.email} onChange={(e) => update(i, "email", e.target.value)} placeholder="—" /></td>
                <td><input className="w-md" value={r.phone} onChange={(e) => update(i, "phone", e.target.value)} placeholder="—" /></td>
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

function Aging({ buckets, currency }) {
  const max = Math.max(...buckets.map((b) => b.amount), 1);
  return (
    <div className="aging">
      {buckets.map((b) => (
        <div className="aging-row" key={b.bucket}>
          <div className="aging-name">{b.bucket}</div>
          <div className="aging-track">
            <div
              className={"aging-bar " + (b.bucket.indexOf("Not") === 0 ? "b-ok" : b.probability >= 74 ? "b-warn" : "b-crit")}
              style={{ width: Math.max(2, (b.amount / max) * 100) + "%" }}
            />
          </div>
          <div className="aging-amt">{money(b.amount, currency)}</div>
          <div className="aging-pct">{b.probability}% usually gets paid</div>
        </div>
      ))}
    </div>
  );
}

function MessageCard({ m, currency }) {
  const [open, setOpen] = useState(false);
  const [channel, setChannel] = useState("whatsapp");
  const body = channel === "email" ? m.email : m.whatsapp;
  const wa = m.to_phone ? "https://wa.me/" + m.to_phone.replace(/[^0-9]/g, "") + "?text=" + encodeURIComponent(m.whatsapp) : null;
  const mailto = m.to_email ? "mailto:" + m.to_email + "?subject=" + encodeURIComponent(m.subject) + "&body=" + encodeURIComponent(m.email) : null;
  return (
    <div className={"msg" + (open ? " open" : "")}>
      <button type="button" className="msg-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className={"tier " + TIER_CLASS[m.tier]}>{m.tier_label}</span>
        <span className="msg-cust">{m.customer}</span>
        <span className="msg-meta">
          {m.invoice_no ? m.invoice_no + " · " : ""}{money(m.amount, currency)}
          {" · "}{m.days_overdue > 0 ? m.days_overdue + " days late" : "not late yet"}
        </span>
        <span className="chev" aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      {open ? (
        <div className="msg-body">
          <p className="msg-why">{m.why}</p>
          <div className="tabs" role="tablist">
            <button type="button" role="tab" aria-selected={channel === "whatsapp"} className={channel === "whatsapp" ? "tab on" : "tab"} onClick={() => setChannel("whatsapp")}>WhatsApp</button>
            <button type="button" role="tab" aria-selected={channel === "email"} className={channel === "email" ? "tab on" : "tab"} onClick={() => setChannel("email")}>Email</button>
          </div>
          {channel === "email" ? <div className="subject"><strong>Subject:</strong> {m.subject}</div> : null}
          <pre className="msg-text">{body}</pre>
          <div className="msg-actions">
            <Copy text={channel === "email" ? m.subject + "\n\n" + m.email : m.whatsapp} label="Copy message" />
            {channel === "email" && mailto ? <a className="btn ghost sm" href={mailto}>Open in email</a> : null}
            {channel === "whatsapp" && wa ? <a className="btn primary sm" href={wa} target="_blank" rel="noreferrer">Send on WhatsApp</a> : null}
            {!m.to_email && !m.to_phone ? <span className="hint">No email or phone saved for this one.</span> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ */

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
  const [msme, setMsme] = useState(true);
  const [bankRate, setBankRate] = useState(5.5);

  const resultRef = useRef(null);
  const reviewRef = useRef(null);
  const step = result ? 3 : rows.length ? 2 : 1;

  useEffect(() => {
    fetch(API + "/api/health").then((r) => r.json())
      .then((h) => {
        setCaps(h);
        if (h.default_bank_rate) setBankRate(h.default_bank_rate);
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
      const got = (json.rows || []).map((r) => ({ ...BLANK, ...r, amount: r.amount == null ? "" : r.amount, due_date: r.due_date || "" }));
      setRows((prev) => [...prev, ...got]);
      setNotes(json.notes || []);
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
    setBusy(true); setError(""); setResult(null);
    try {
      const res = await fetch(API + "/api/analyse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          data: rowsToCsv(clean), currency, sender_name: sender, company_name: company,
          bank_rate: msme && currency === "INR" ? Number(bankRate) || null : null,
        }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(json.detail || "Something went wrong reading those rows.");
      setResult(json);
    } catch (err) {
      setError(err.message || "Something went wrong. Try again.");
    } finally { setBusy(false); }
  }, [rows, currency, sender, company, msme, bankRate]);

  const rep = result && result.report;

  const csvOut = useMemo(() => {
    if (!rep) return "";
    const head = "Rank,Customer,Invoice,Amount,Due date,Days late,Bucket,Chance of collection %,Cost of waiting 30d,Statutory interest,Action\n";
    return head + rep.priority.map((p) => [
      p.rank, '"' + String(p.customer).replace(/"/g, "'") + '"', '"' + String(p.invoice_no || "").replace(/"/g, "'") + '"',
      p.amount, p.due_date || "", p.days_overdue, '"' + p.bucket + '"', p.probability, p.slip_30d,
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
    ? "I ran my unpaid bills through Receivables Rescue: " + money(rep.total_outstanding, currency)
      + " outstanding, and " + money(rep.cost_of_waiting_30d, currency)
      + " of it quietly disappears if I do nothing for 30 days. Free, no signup."
    : "";

  const reset = () => { setRows([]); setResult(null); setNotes([]); setError(""); };

  return (
    <div className="page">
      <header className="topbar">
        <div className="wrap bar">
          <div className="logo"><span className="dot" aria-hidden="true" />Receivables Rescue</div>
          {rows.length || result ? (
            <button type="button" className="btn ghost sm" onClick={reset}>Start over</button>
          ) : null}
        </div>
      </header>

      <main className="wrap">
        <div className="intro">
          <h1>Find the money you are already owed.</h1>
          <p>Add your unpaid bills. See who to chase first, what waiting costs you, and send the
             reminder in one tap. Nothing is saved, and there is no sign-up.</p>
        </div>

        <Steps step={step} />

        <section className="card">
          {caps.upload === false ? (
            <div className="upload-off">
              <strong>File uploads are unavailable on this server right now.</strong>
              <span>Type or paste your bills below instead — everything else works normally.</span>
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
          {notes.length ? <div className="notes">{notes.map((n, i) => <div key={i}>{n}</div>)}</div> : null}
          {!caps.vision && caps.upload !== false ? (
            <p className="cap-note">
              PDF bills are read automatically. Photos of paper bills need the AI reader turned on
              — until then, type those in or paste them.
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
              {showDetails ? "−" : "+"} Your details, currency and interest settings
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
                {currency === "INR" ? (
                  <>
                    <div className="field check">
                      <label htmlFor="msme">
                        <input id="msme" type="checkbox" checked={msme} onChange={(e) => setMsme(e.target.checked)} />
                        <span>I am registered on Udyam (MSME)</span>
                      </label>
                      <small>Adds the late-payment interest the MSMED Act entitles you to.</small>
                    </div>
                    {msme ? (
                      <div className="field">
                        <label htmlFor="rate">RBI Bank Rate (%)</label>
                        <input id="rate" inputMode="decimal" value={bankRate} onChange={(e) => setBankRate(e.target.value)} />
                        <small>Check today's rate on rbi.org.in before you quote a figure.</small>
                      </div>
                    ) : null}
                  </>
                ) : null}
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
                <div className="stat-label">Likely to actually arrive</div>
                <div className="stat-value">{money(rep.expected_recoverable, currency)}</div>
                <div className="stat-sub">{money(rep.at_risk, currency)} is already at risk</div>
              </div>
              <div className="stat bad">
                <div className="stat-label">Lost if you wait 30 more days</div>
                <div className="stat-value">{money(rep.cost_of_waiting_30d, currency)}</div>
                <div className="stat-sub">Every day of silence has a price</div>
              </div>
            </section>

            {rep.statutory_interest_total > 0 ? (
              <section className="card msme-card">
                <h2>You are also owed interest</h2>
                <p className="msme-figure">{money(rep.statutory_interest_total, currency)}</p>
                <p>
                  Under the MSMED Act, a buyer who pays a registered micro or small business late owes
                  compound interest at <strong>{rep.statutory_rate}% a year</strong> &mdash; three times
                  the RBI Bank Rate. Most small businesses never ask for it. It is now written into your
                  final-notice messages below.
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
                {showAssume ? "−" : "+"} Where these percentages come from
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
                  <p>{rep.ranking_basis || "Ranked by money lost if you wait another 30 days."} Open any row for a message you can send now.</p>
                </div>
                <div className="head-actions">
                  <button type="button" className="btn ghost sm" onClick={download}>Download list</button>
                  <Copy text={shareText} label="Copy share text" />
                </div>
              </div>
              <div className="msgs">
                {result.messages.map((m, i) => <MessageCard key={i} m={m} currency={currency} />)}
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
                        <td className="r">{c.oldest_days > 0 ? c.oldest_days + "d" : "—"}</td>
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
          Your bills are read to build this page and are never stored, logged or shared. Receivables
          Rescue is not legal, accounting or debt-collection advice; collection percentages are
          industry benchmarks, and the interest figure is an estimate to check with your accountant.
        </p>
      </footer>
    </div>
  );
}
