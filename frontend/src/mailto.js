// Build a mailto: link only for exactly one well-formed address. Anything with
// control characters, query separators or extra recipients is dropped instead
// of interpolated into the link.
const EMAIL_RE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;

export function safeEmailAddress(to) {
  const t = to == null ? "" : String(to).trim();
  return EMAIL_RE.test(t) ? t : null;
}

export function buildMailto(m) {
  const addr = safeEmailAddress(m && m.to_email);
  if (!addr) return null;
  return "mailto:" + addr + "?subject=" + encodeURIComponent(m.subject) + "&body=" + encodeURIComponent(m.email);
}
