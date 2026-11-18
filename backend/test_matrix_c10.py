"""22-case chronology matrix through the real FastAPI app.

Twenty-two chronology cases through the real FastAPI app. In case (o) -
dual-intent reply, then a re-consent only - the opt-out clears but the
open dispute remains, so the plan is PAUSE (the restrictive outcome),
not the script's earlier guess of HUMAN.
"""
import unittest

from fastapi.testclient import TestClient

import server


class TestMatrixC10(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)

    def post(self, evs, today="2026-11-18", due="2026-10-11"):
        r = self.client.post("/api/next-action", json={"number": "I1", "amount": 1000, "due": due, "today": today, "events": evs})
        return r.status_code, r.json()

    def test_matrix(self):
        def rep(d, t="stop emailing me"): return {"day": d, "type": "reply", "text": t}
        def rc(d): return {"day": d, "type": "reconsent"}
        def rs(d): return {"day": d, "type": "resolved"}
        def dis(d): return rep(d, "this invoice is wrong, I dispute it")
        cases=[
         ("a reconsent before optout, listed after STOP",[rc("2026-11-10"),rep("2026-11-12")],"stop"),
         ("b optout dated after reconsent, listed before STOP",[rep("2026-11-14"),rc("2026-11-12")],"stop"),
         ("c optout dated before, listed after reconsent STOP",[rc("2026-11-14"),rep("2026-11-12")],"stop"),
         ("d1 same date optout then reconsent resume",[rep("2026-11-14"),rc("2026-11-14")],"draft"),
         ("d2 same date reconsent then optout STOP",[rc("2026-11-14"),rep("2026-11-14")],"stop"),
         ("e optout,reconsent,optout STOP",[rep("2026-11-10"),rc("2026-11-12"),rep("2026-11-14")],"stop"),
         ("f1 plain dispute+resolved resumes",[dis("2026-11-10"),rs("2026-11-12")],"draft"),
         ("f2 resolved before dispute pause",[rs("2026-11-10"),dis("2026-11-12")],"pause"),
         ("f3 dual-intent+resolved STOP/human",[rep("2026-11-10","stop emailing me, the invoice is wrong"),rs("2026-11-12")],"stop"),
         ("f4 resolved never lifts optout",[rep("2026-11-10"),rs("2026-11-12")],"stop"),
         ("f5 reconsent doesn't close dispute",[dis("2026-11-10"),rc("2026-11-12")],"pause"),
         ("g reconsent no optout noop",[rc("2026-11-12")],"draft"),
         ("h future reconsent 422",[rep("2026-11-10"),rc("2026-11-25")],422),
         ("i future resolved 422",[dis("2026-11-10"),rs("2026-11-25")],422),
         ("j reply-text 'resubscribe me' not resume",[rep("2026-11-10"),rep("2026-11-12","please resubscribe me, send reminders again")],"stop"),
         ("k 'I didnt unsubscribe' alone human",[rep("2026-11-12","i didnt unsubscribe")],"human"),
         ("l 'resubscribe me' alone human",[rep("2026-11-12","resubscribe me")],"human"),
         ("m 'dont unsubscribe me' human",[rep("2026-11-12","dont unsubscribe me")],"human"),
         ("n 'unsubscribe' alone stop",[rep("2026-11-12","unsubscribe")],"stop"),
         ("o optout+dispute, reconsent only -> pause (open dispute remains)",[rep("2026-11-10","stop emailing me, the invoice is wrong"),rc("2026-11-12")],"pause"),
         ("p reconsent then sent tier firm preserved",[rep("2026-11-10"),rc("2026-11-11"),{"day":"2026-11-12","type":"sent","tier":"escalation"}],"hold"),
         ("q resolved unknown reply then ok",[rep("2026-11-10","hmm ok whatever"),rs("2026-11-12")],"draft"),
        ]
        failures = []
        for n, evs, want in cases:
            s, j = self.post(evs)
            k = (s, j.get("kind"), (j.get("reason") or "")[:90])
            ok = (s == 422) if want == 422 else (s == 200 and str(k[1]).lower().startswith(want))
            if not ok:
                failures.append((n, k))
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
