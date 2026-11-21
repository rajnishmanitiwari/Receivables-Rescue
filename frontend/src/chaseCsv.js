// Download-only formatting. Never use this to rewrite input identities.
// A visible literal marker avoids relying on spreadsheet-specific apostrophe
// or tab handling. It is part of the downloaded value, not the saved input.
export function csvText(value) {
  const raw = value == null ? "" : String(value);
  const withoutLeadingSpace = raw.trimStart();
  const risky = /^[=+\-@＝＋－＠]/u.test(withoutLeadingSpace) || (raw.length > 0 && raw.charCodeAt(0) < 32);
  const text = risky ? "[text] " + raw : raw;
  return '"' + text.replace(/"/g, '""') + '"';
}
const numeric = value => typeof value === "number" && Number.isFinite(value) ? String(value) : "";
export function chaseCsv(priority) {
  const head = "Heuristic rank,Customer,Invoice,Amount,Due date,Days late,Bucket,Draft tier\n";
  return head + priority.map(p => [
    numeric(p.rank), csvText(p.customer), csvText(p.invoice_no), numeric(p.amount),
    csvText(p.due_date), numeric(p.days_overdue), csvText(p.bucket), csvText(p.tier),
  ].join(",")).join("\n");
}
