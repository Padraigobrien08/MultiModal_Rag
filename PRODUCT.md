# Product

## Register

product

## Users

Internal team members (developers, product owners) monitoring a multimodal RAG tutorial-search system called Stepwise. They check the dashboard periodically to understand query volume, latency bottlenecks, retrieval quality, and user feedback. Context: desktop browser, low ambient light, data-literate users who need density over hand-holding.

## Product Purpose

Stepwise converts tutorial videos and screenshots into structured, queryable knowledge. The admin dashboard exposes operational telemetry — query logs, latency breakdowns, retrieval metrics, and feedback signals — so the team can identify what's slow, what retrieval is failing, and which content consistently disappoints users.

## Brand Personality

Precise, terminal-native, understated. The UI gets out of the way of the data.

## Anti-references

- Generic SaaS admin templates (Tremor default, shadcn default chart dashboards)
- Cream/sand/beige warm-tinted surfaces
- Gradient text, glassmorphism cards, hero-metric big-number templates
- Bulky navigation chrome that competes with data
- Pastel color coding — data should be readable in near-monochrome with one sharp accent

## Design Principles

1. **Data density first.** Every pixel that isn't data is overhead. Tables beat cards when there are many rows; charts beat tables when shape matters.
2. **One accent, used surgingly.** Phosphor green (#00ff88) marks the one thing that matters on each surface. Not highlights, not decoration — a semantic signal.
3. **Mono for numbers.** All latency values, distances, scores, and counts use JetBrains Mono. Alignment is information.
4. **Expand on demand.** Summary rows are the default; full detail is one click away. Don't show everything at once.
5. **Earn color.** Color in charts and tables encodes meaning (good/bad, fast/slow, high/low). No decorative color assignments.

## Accessibility & Inclusion

WCAG AA minimum. All chart information available in table form. Contrast checked for text on dark surfaces. Reduced motion supported.
