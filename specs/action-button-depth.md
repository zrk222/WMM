# Action button depth

Scope: the existing shared root-app controls, without changing actions or authority.

- Primary actions retain green, secondary actions use blue, and explicit caution/destructive variants retain amber/red meaning. Status colors remain independent.
- Pointer-down wins over hover and shows an inset pressed state; disabled controls remain flat and clearly unavailable.
- Keyboard focus has a visible contrasting ring on light content and the dark sidebar. Icons inherit the action state.
- Reduced motion removes movement while retaining pressed shading. Existing mobile layouts and 44px controls remain usable.
- Acceptance uses the actual loopback app with an isolated synthetic store at 390px and 1440px, captures screenshots, blocks external traffic and checks keyboard modal behavior, disabled controls and pointer-down computed styles.

No new dark theme, provider effects, dependencies, or conversion claims are introduced.
