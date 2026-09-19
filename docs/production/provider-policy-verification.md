# LLM Provider Data-Policy Verification Record (R-05)

Status date: 2026-09-19 · Provider: Zhipu AI / GLM via
`https://open.bigmodel.cn/api/paas/v4` (OpenAI-compatible endpoint).

## VERDICT: NOT VERIFIED (gate ships BLOCKED for real client data)

Per the Round-1 evidence rules — official provider documentation only;
forums/blogs/search summaries are not a final production judgment — the
policy could not be fully verified, so the runtime gate
(`runtime/agent/data_policy.py`) **blocks real client data by default**
and opens only on the operator's explicit post-verification opt-in
(`INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED=1`).

## What was checked (evidence trail)

1. **Official policy location** — the platform privacy policy is served
   from the `docs.bigmodel.cn` / `open.bigmodel.cn` domains. Both pages
   are JavaScript-rendered single-page applications: automated fetches on
   2026-09-19 returned only the SPA shell (verified — 3,483 bytes of
   loader markup, no policy text). The verbatim primary text therefore
   could NOT be independently retrieved by tooling during remediation.
2. **Third-party investigation** (search-retrieved summary of a zhihu
   column comparing DeepSeek / Zhipu / Ali Bailian data policies)
   reported:
   - the Zhipu general API terms retain an **"anonymized data may be used
     for training"** clause;
   - the Coding Plan (Token Plan team edition) explicitly promises no
     training on conversation data.
   This is third-party evidence — recorded as context, explicitly NOT
   accepted as the production judgment.
3. **Data retention period, storage region, deletion, DPA** — no primary
   official statements retrieved. UNKNOWN.

Sources consulted:
- [Zhipu BigModel platform](https://open.bigmodel.cn) (SPA shell only)
- [Zhipu docs portal](https://docs.bigmodel.cn) (privacy policy is
  JS-rendered; verbatim text not machine-retrievable in this environment)
- Third-party comparison (context only, not a production judgment)

## Operator verification procedure (before enabling real client data)

1. Open the current official privacy policy and service agreement on
   `docs.bigmodel.cn` in a browser (the SPA renders there).
2. Confirm, in the CURRENT text: (a) whether API-submitted content is
   used for model training (including anonymized/de-identified use);
   (b) the data retention period; (c) the data storage region;
   (d) deletion/enterprise-API terms; (e) any DPA available for your
   account tier.
3. Record the findings, the exact quoted clauses, the document version
   and the review date in this file (append a dated section below).
4. Only then set `INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED=1` for the
   production process — and only for a provider whose terms you have
   accepted for real client data.
5. If the terms are unacceptable (e.g. anonymized training use on client
   PII), keep the gate BLOCKED and switch to an acceptable provider or
   an enterprise tier with contractual no-training terms.

## Runtime behavior (as shipped)

```text
INSURANCE_AGENT_CLIENT_DATA unset | synthetic → gate open (benchmark/demo)
INSURANCE_AGENT_CLIENT_DATA=real, verified unset → BLOCK (fail closed)
INSURANCE_AGENT_CLIENT_DATA=real, INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED=1 → open
```

Tests: `tests/runtime/test_p0_r05.py` (T-R05-01..05).

<!-- append dated operator verification sections below this line -->
