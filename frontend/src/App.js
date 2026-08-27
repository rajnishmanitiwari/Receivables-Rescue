import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import SAMPLE_CSV from "./sample";

const API = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
const SYMBOLS = { INR: "₹", USD: "$", EUR: "€", GBP: "£", AED: "AED " };

function money(n, cur = "INR") {
  const v = Math.round(Number(n) || 0);
  if (cur === "INR") {
    const s = String(Math.abs(v));
    let out = s;
    if (s.length > 3) {
      let head = s.slice(0, -3);
      const tail = s.slice(-3);
      const parts = [];
      while (head.length > 2) {
        parts.unshift(head.slice(-2));
        head = head.slice(0, -2);
      }
      if (head) parts.unshift(head);
      out = parts.join(",") + "," + tail;
    }
    return (v < 0 ? "-" : "") + SYMBOLS.INR + out;
  }
  return (SYMBOLS[cur] || cur + " ") + v.toLocaleString("en-US");
}

const TIER_CLASS = { reminder: "t-ok", firm: "t-warn", escalation: "t-hot", final: "t-crit" };

function Stat({ label, value, sub, tone }) {
  return (
    <div className={"stat " + (tone || "")}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub ? <div className="stat-sub">{sub}</div> : null}
    </div>
  );
}

function Copy({ text, label = "Copy" }) {
  const [done, setDone] = useState(false);
  const onClick = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch (e) {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); } catch (e2) { /* ignore */ }
      document.body.removeChild(ta);
    }
    setDone(true);
    setTimeout(() => setDone(false), 1600);
  };
  return (
    <button type="button" className="btn ghost sm" onClick={onClick}>
      {done ? "Copied" : label}
    </button>
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
              className={"aging-bar " + (b.bucket.startsWith("Not") ? "b-ok" : b.probability >= 74 ? "b-warn" : "b-crit")}
              style={{ width: Math.max(3, (b.amount / max) * 100) + "%" }}
            />
          </div>
          <div className="aging-amt">{money(b.amount, currency)}</div>
          <div className="aging-pct">{b.probability}% typically collected</div>
        </div>
      ))}
    </div>
  );
}

function MessageCard({ m, currency }) {
  const [open, setOpen] = useState(false);
  const [channel, setChannel] = useState("email");
  const body = channel === "email" ? m.email : m.whatsapp;
  const wa = m.to_phone ? "https://wa.me/" + m.to_phone.replace(/[^0-9]/g, "") + "?text=" + encodeURIComponent(m.whatsapp) : null;
  const mailto = m.to_email
    ? "mailto:" + m.to_email + "?subject=" + encodeURIComponent(m.subject) + "&body=" + encodeURIComponent(m.email)
    : null;
  return (
    <div className="msg">
      <button type="button" className="msg-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className={"tier " + TIER_CLASS[m.tier]}>{m.tier_label}</span>
        <span className="msg-cust">{m.customer}</span>
        <span className="msg-meta">
          {m.invoice_no ? m.invoice_no + " · " : ""}
          {money(m.amount, currency)} · {m.days_overdue > 0 ? m.days_overdue + "d overdue" : "not due yet"}
        </span>
        <span className="chev">{open ? "−" : "+"}</span>
      </button>
      {open ? (
        <div className="msg-body">
          <p className="msg-why">{m.why}</p>
          <div className="tabs">
            <button type="button" className={channel === "email" ? "tab on" : "tab"} onClick={() => setChannel("email")}>Email</button>
            <button type="button" className={channel === "whatsapp" ? "tab on" : "tab"} onClick={() => setChannel("whatsapp")}>WhatsApp</button>
          </div>
          {channel === "email" ? <div className="subject"><strong>Subject:</strong> {m.subject}</div> : null}
          <pre className="msg-text">{body}</pre>
          <div className="msg-actions">
            <Copy text={channel === "email" ? m.subject + "\n\n" + m.email : m.whatsapp} label="Copy message" />
            {channel === "email" && mailto ? <a className="btn ghost sm" href={mailto}>Open in email</a> : null}
            {channel === "whatsapp" && wa ? <a className="btn ghost sm" href={wa} target="_blank" rel="noreferrer">Send on WhatsApp</a> : null}
            {!m.to_email && !m.to_phone ? <span className="hint">No contact on file for this one.</span> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function App() {
  const [data, setData] = useState("");
  const [currency, setCurrency] = useState("INR");
  const [sender, setSender] = useState("");
  const [company, setCompany] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [showAssume, setShowAssume] = useState(false);
  const fileRef = useRef(null);
  const resultRef = useRef(null);

  useEffect(() => {
    if (result && resultRef.current) resultRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [result]);

  const onFile = (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    if (f.size > 4 * 1024 * 1024) { setError("That file is over 4 MB. Export just the open invoices."); return; }
    const r = new FileReader();
    r.onload = () => { setData(String(r.result || "")); setError(""); };
    r.onerror = () => setError("Could not read that file.");
    r.readAsText(f);
  };

  const run = useCallback(async () => {
    if (!data.trim()) { setError("Paste your invoices or upload a CSV first."); return; }
    setBusy(true); setError(""); setResult(null);
    try {
      const res = await fetch(API + "/api/analyse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data, currency, sender_name: sender, company_name: company }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(json.detail || "Analysis failed. Check your columns and try again.");
      setResult(json);
    } catch (err) {
      setError(err.message || "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }, [data, currency, sender, company]);

  const rep = result && result.report;

  const csvOut = useMemo(() => {
    if (!rep) return "";
    const head = "Rank,Customer,Invoice,Amount,Due date,Days overdue,Bucket,Chance of collection %,Cost of waiting 30d,Action\n";
    return head + rep.priority.map((p) => [
      p.rank,
      '"' + String(p.customer).replace(/"/g, "'") + '"',
      '"' + String(p.invoice_no || "").replace(/"/g, "'") + '"',
      p.amount, p.due_date || "", p.days_overdue, '"' + p.bucket + '"',
      p.probability, p.slip_30d, p.tier,
    ].join(",")).join("\n");
  }, [rep]);

  const download = () => {
    const blob = new Blob([csvOut], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "chase-list.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const shareText = rep
    ? `I ran my unpaid invoices through Receivables Rescue: ${money(rep.total_outstanding, currency)} outstanding, and ${money(rep.cost_of_waiting_30d, currency)} of it quietly disappears if I do nothing for 30 days. Free, no signup.`
    : "";

  return (
    <div className="page">
      <header className="hero">
        <div className="wrap">
          <div className="brand">Receivables Rescue</div>
          <h1>Find the money you are <em>already owed</em>.</h1>
          <p className="sub">
            Paste your unpaid invoices. In 30 seconds you get who to chase first, how much
            you lose by waiting another month, and the follow-up messages ready to send.
            No signup. Nothing stored.
          </p>
        </div>
      </header>

      <main className="wrap">
        <section className="card input-card">
          <div className="row between">
            <h2>Your open invoices</h2>
            <button type="button" className="btn link" onClick={() => { setData(SAMPLE_CSV); setError(""); }}>
              Use sample data
            </button>
          </div>
          <p className="help">
            CSV, TSV or just pasted rows. Include a <strong>customer</strong>, <strong>amount</strong> and
            {" "}<strong>due date</strong> column — the names do not have to match exactly. Email and phone are optional
            but let us build sendable follow-ups.
          </p>
          <textarea
            value={data}
            onChange={(e) => { setData(e.target.value); setError(""); }}
            placeholder={"Customer,Invoice No,Amount,Due Date,Email,Phone\nAcme Traders,INV-2041,425000,2026-04-21,accounts@acme.com,+919812345678"}
            spellCheck={false}
            rows={9}
          />
          <div className="controls">
            <label className="btn ghost">
              Upload CSV
              <input ref={fileRef} type="file" accept=".csv,.tsv,.txt,text/csv,text/plain" onChange={onFile} hidden />
            </label>
            <select value={currency} onChange={(e) => setCurrency(e.target.value)} aria-label="Currency">
              <option value="INR">INR &#8377;</option>
              <option value="USD">USD $</option>
              <option value="EUR">EUR &#8364;</option>
              <option value="GBP">GBP &#163;</option>
              <option value="AED">AED</option>
            </select>
            <input value={sender} onChange={(e) => setSender(e.target.value)} placeholder="Your name (for the messages)" />
            <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Your company" />
          </div>
          {error ? <div className="error">{error}</div> : null}
          <button type="button" className="btn primary big" onClick={run} disabled={busy}>
            {busy ? "Working…" : "Show me the money"}
          </button>
          <p className="privacy">
            Your invoice data is processed in memory to build this report and is never written to a
            database, logged or shared. Only an anonymous count of how many reports were run is kept.
          </p>
        </section>

        {rep ? (
          <div ref={resultRef}>
            {result.warnings && result.warnings.length ? (
              <div className="warnings">
                {result.warnings.map((w, i) => <div key={i}>{w}</div>)}
              </div>
            ) : null}

            <section className="stats">
              <Stat label="Outstanding" value={money(rep.total_outstanding, currency)}
                    sub={`${rep.invoice_count} invoices · ${rep.customer_count} customers`} />
              <Stat label="Realistically collectable" value={money(rep.expected_recoverable, currency)}
                    sub={`${money(rep.at_risk, currency)} is already at risk`} tone="good" />
              <Stat label="You lose this by waiting 30 more days" value={money(rep.cost_of_waiting_30d, currency)}
                    sub="Every day of silence has a price" tone="bad" />
            </section>

            {rep.risks && rep.risks.length ? (
              <section className="card">
                <h2>What is actually wrong</h2>
                <ul className="risks">{rep.risks.map((r, i) => <li key={i}>{r}</li>)}</ul>
              </section>
            ) : null}

            <section className="card">
              <h2>Where your money is sitting</h2>
              <Aging buckets={rep.buckets} currency={currency} />
              <button type="button" className="btn link" onClick={() => setShowAssume(!showAssume)}>
                {showAssume ? "Hide" : "Show"} the assumptions behind these percentages
              </button>
              {showAssume ? (
                <div className="assume">
                  <p>{rep.assumptions.note}</p>
                  <div className="curve">
                    {rep.assumptions.curve.map((c, i) => (
                      <span key={i}>{c.days_past_due}d &rarr; {c.collected}%</span>
                    ))}
                  </div>
                </div>
              ) : null}
            </section>

            <section className="card">
              <div className="row between">
                <h2>Chase these first</h2>
                <div className="row gap">
                  <button type="button" className="btn ghost sm" onClick={download}>Download chase list</button>
                  <Copy text={shareText} label="Copy share text" />
                </div>
              </div>
              <p className="help">{rep.ranking_basis || "Ranked by money lost if you wait another 30 days."} Open any row for a message you can send right now.</p>
              <div className="msgs">
                {result.messages.map((m, i) => <MessageCard key={i} m={m} currency={currency} />)}
              </div>
            </section>

            <section className="card">
              <h2>By customer</h2>
              <div className="tablewrap">
                <table>
                  <thead>
                    <tr><th>Customer</th><th className="r">Owed</th><th className="r">Invoices</th><th className="r">Oldest</th><th className="r">Share of book</th></tr>
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
          Receivables Rescue gives you a prioritised view of your own numbers. It is not legal,
          accounting or debt-collection advice, and the collection percentages are industry aging
          benchmarks, not a prediction about your customers.
        </p>
      </footer>
    </div>
  );
}
