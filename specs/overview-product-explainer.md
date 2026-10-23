# Spec: overview-product-explainer
Status: draft

## MUST - Functional core
### Description
Replace the vague Overview introduction with concrete public-user product facts: purpose, supplied/connected inputs, actual operations and named deliverables. Preserve all existing controls and user approval boundaries. Do not substitute disclaimers for the explanation.

### Requirements (EARS)
- The system shall return an Overview hero that names app marketing, preparation and measurement through `product_purpose`.
- The system shall return four numbered explanation blocks that name app details, supplied evidence and connected account reports, actual twelve-stage preparation/validation/calculation operations, and saved work packets, briefs, experiment plans and PDF reports through `product_facts`.
- The system shall retain the Guided workflow entry and verify the concrete explanation at desktop width 1440 px and mobile width 390 px through `explainer_proof`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: product_purpose
  Given the Overview page
  When `product_purpose` is displayed in the hero
  Then the user reads the purpose as app marketing preparation and measurement
Scenario: product_facts
  Given the implemented repository capabilities
  When `product_facts` is displayed in the explanation
  Then the four blocks name actual inputs, operations and outputs without hedging or invented business outcomes
Scenario: explainer_proof
  Given desktop and mobile browsers
  When `explainer_proof` loads Overview and activates its primary action
  Then the concrete explanation is visible and Guided workflow opens
```

## SHOULD - Technical
- Ground claims in catalog.py, packets.py, ledger.py, subscription_review.py and existing report controls. Account reads require user-selected connections; user-supplied records remain distinct.
- Use direct declarative language. Avoid vague helpers, uncertain modal verbs and a disclaimer-led introduction. Do not promise users, revenue or profit.
- Keep the existing layout and interactions. Validate Node/browser/PDF regression, rendered design, architecture integrity and hash-bound workflow evidence.

## Authorized parameters
