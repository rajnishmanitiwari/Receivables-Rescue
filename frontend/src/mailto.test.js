import { safeEmailAddress, buildMailto } from "./mailto";

test("accepts exactly one well-formed address", () => {
  expect(safeEmailAddress("ap@everline.example")).toBe("ap@everline.example");
  expect(safeEmailAddress("  ap@everline.example  ")).toBe("ap@everline.example");
});

test("drops query separators, CRLF, extra recipients and junk", () => {
  for (const bad of [
    "a@b.co?subject=x", "a@b.co&body=x", "a@b.co\nBcc: x@y.z", "a@b.co\r\nbcc:x@y.z",
    "two@a.b, three@c.d", "a@b.co;b@c.d", "not-an-email", "a@b", "", null, undefined,
  ]) {
    expect(safeEmailAddress(bad)).toBeNull();
  }
});

test("buildMailto encodes subject and body, never the address source", () => {
  const link = buildMailto({ to_email: "ap@everline.example", subject: "Invoice INV-2041", email: "Hi,\nPlease pay ₹4,25,000." });
  expect(link.startsWith("mailto:ap@everline.example?subject=")).toBe(true);
  expect(link).toContain(encodeURIComponent("Hi,\nPlease pay ₹4,25,000."));
  expect(buildMailto({ to_email: "a@b.co?bcc=x@y.z", subject: "s", email: "b" })).toBeNull();
});
