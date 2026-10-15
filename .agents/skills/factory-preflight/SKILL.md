---
name: factory-preflight
description: Run the offline, read-only structural checks for a Polygon problem folder before any upload. Use for imported or existing problems; does not verify solution correctness.
---

# Factory structural preflight

Read `FACTORY_START_HERE.md` and `docs/factory/VERIFICATION.md`.

Run:

~~~bash
python3 -m polyup preflight problems/<slug> --json
~~~

If there are errors: fix only missing/invalid components, re-run, then report exact issue codes. Warnings must be reviewed; they do not establish correctness. Never treat structural PASS as proof of algorithmic validity or Polygon package success.

After structural PASS, run the **separate** local `./verify.sh problems/<slug>` if the C++/Java toolchain is available. Actual Polygon upload requires user authorization. Do not ask for API keys in the conversation.
