import { applyPromiseDateToEvents, clearPromiseDateFromEvents, buildNextActionEvents,
         localIso, isOutlierDate } from "./promiseDate";

const reply = (id, extra = {}) => ({ id, type: "reply", text: "t" + id, ...extra });

describe("confirmed promise dates stay on their own event", () => {
  test("confirm dates the targeted reply", () => {
    const evs = [reply(1), reply(2)];
    const next = applyPromiseDateToEvents(evs, "2026-11-20", 2);
    expect(next[1].promise_date).toBe("2026-11-20");
    expect(next[0].promise_date).toBeUndefined();
  });

  test("a newer reply is not touched when changing the date on an older reply", () => {
    const evs = [reply(1, { promise_date: "2026-11-20" }), reply(2)];
    const next = applyPromiseDateToEvents(evs, "2026-11-27", 1);
    expect(next[0].promise_date).toBe("2026-11-27");
    expect(next[1].promise_date).toBeUndefined();
  });

  test("confirming a date on a newer reply clears the older one (single-date invariant)", () => {
    const evs = [reply(1, { promise_date: "2026-11-20" }), reply(2)];
    const next = applyPromiseDateToEvents(evs, "2026-11-27", 2);
    expect(Object.keys(next[0])).not.toContain("promise_date");
    expect(next[1].promise_date).toBe("2026-11-27");
  });

  test("remove clears only the targeted reply", () => {
    const evs = [reply(1, { promise_date: "2026-11-20" }), reply(2)];
    const next = clearPromiseDateFromEvents(evs, 1);
    expect(Object.keys(next[0])).not.toContain("promise_date");
    expect(next[1]).toEqual(evs[1]);
  });

  test("non-reply events are never dated", () => {
    const evs = [{ id: 1, type: "sent", tier: "polite" }, reply(2)];
    const next = applyPromiseDateToEvents(evs, "2026-11-20", 1);
    expect(next[0].promise_date).toBeUndefined();
  });
});

describe("next-action payload serialization", () => {
  test("a logged sent event keeps its tier (tier ladder regression)", () => {
    const evs = [{ id: 1, type: "sent", tier: "firm", day: "2026-11-17" }];
    const out = buildNextActionEvents(evs, "2026-11-18");
    expect(out[0].tier).toBe("firm");
    expect(out[0].type).toBe("sent");
  });

  test("session id is stripped, day defaults to local today, all fields survive", () => {
    const evs = [{ id: 7, type: "reply", text: "will pay friday", promise_date: "2026-11-20" },
                 { id: 8, type: "payment", amount: 50, day: "2026-11-10" }];
    const out = buildNextActionEvents(evs, "2026-11-18");
    expect(out[0]).toEqual({ type: "reply", text: "will pay friday", promise_date: "2026-11-20", day: "2026-11-18" });
    expect(out[1]).toEqual({ type: "payment", amount: 50, day: "2026-11-10" });
    expect(Object.keys(out[0])).not.toContain("id");
  });

  test("localIso uses the local calendar day, not UTC", () => {
    // 2026-11-18 01:30 local at UTC+5:30 is still 2026-11-17 in UTC.
    const d = new Date(2026, 10, 18, 1, 30);
    expect(localIso(d)).toBe("2026-11-18");
  });
});

describe("outlier confirmation guard", () => {
  test("dates within the window need no extra confirmation", () => {
    expect(isOutlierDate("2026-11-30", "2026-11-18")).toBe(0);
  });
  test("far-future dates report how far out they are", () => {
    expect(isOutlierDate("2027-02-15", "2026-11-18")).toBe(89);
  });
});
