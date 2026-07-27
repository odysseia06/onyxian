# $id

What this module provides and the conventions it carries. Document your note
types (their `type` values, status lifecycles, extra frontmatter fields) in a
table here — agents and humans both read this.

The module authoring guide — manifest anatomy, variables, Bases, skills and
agents, and the review checklist — is at
https://github.com/odysseia06/onyxian/blob/main/docs/module-authoring.md
In short: assets mirror install paths verbatim (placeholder segments included),
prose is never hard-wrapped, `{{variable}}` belongs to the engine and
`<% tp.* %>` to Templater, and modules contain no executable code.
