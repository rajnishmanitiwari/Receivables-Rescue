// Pure helpers for confirmed promise dates on reply events.
// A confirmed promise_date belongs to one specific reply event, identified by
// its session id: a newer reply must never inherit or lose the date by
// position, and at most one reply carries a date at any time.

export function applyPromiseDateToEvents(events, dstr, targetId) {
  return events.map((e) => {
    if (e.type !== "reply") return e;
    if (e.id === targetId) return { ...e, promise_date: dstr };
    if (e.promise_date) { const { promise_date, ...rest } = e; return rest; }
    return e;
  });
}

export function clearPromiseDateFromEvents(events, targetId) {
  return events.map((e) => {
    if (e.id === targetId && e.promise_date) { const { promise_date, ...rest } = e; return rest; }
    return e;
  });
}

// Local calendar date as YYYY-MM-DD. toISOString() is UTC and can say
// "tomorrow" or "yesterday" for a local evening/morning; the planner compares
// calendar days, so events must carry the user's local day.
export function localIso(d) {
  const p = (n) => String(n).padStart(2, "0");
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
}

// Serialize events for /api/next-action: every planner-relevant field
// (type, day, text, amount, tier, promise_date) survives; only the UI-only
// session id is stripped. Day defaults to the local today at send time.
export function buildNextActionEvents(events, todayIso) {
  return events.map((e) => {
    const { id, ...rest } = e;
    return { ...rest, day: e.day || todayIso };
  });
}

// A confirmed date this far out is unusual for a promise-to-pay; the UI asks
// for an explicit second confirmation instead of silently accepting or
// silently capping it. This is a confirmation threshold, not a maximum.
export const OUTLIER_WINDOW_DAYS = 30;
export function isOutlierDate(dstr, todayIso, windowDays = OUTLIER_WINDOW_DAYS) {
  const days = Math.round((new Date(dstr + "T00:00:00") - new Date(todayIso + "T00:00:00")) / 86400000);
  return days > windowDays ? days : 0;
}
