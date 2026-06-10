<%*
const title = await tp.system.prompt("Paper title");
const authorsRaw = await tp.system.prompt("Authors (comma-separated)");
const authors = authorsRaw.split(",").map(a => a.trim());
const year = await tp.system.prompt("Year");
const venue = await tp.system.prompt("Venue (leave blank if unknown)", "");
const type = await tp.system.suggester(
  ["attack", "construction", "engineering", "foundations", "framework", "protocol", "survey"],
  ["attack", "construction", "engineering", "foundations", "framework", "protocol", "survey"],
  false, "Paper type"
);
const priority = await tp.system.suggester(
  ["low", "medium", "high"],
  ["low", "medium", "high"],
  false, "Priority"
);
const citationKey = await tp.system.prompt("Citation key (e.g. Komlo2024)");
const shortTitle = await tp.system.prompt("Short title (e.g. FROST)");
const url = await tp.system.prompt("URL (leave blank if none)", "");

const dateAdded = tp.date.now("YYYY-MM-DD");
const pdfLink = `[[${citationKey} - ${shortTitle}.pdf]]`;
const newFilename = `${citationKey} - ${shortTitle}`;
await tp.file.rename(newFilename);

// Build authors YAML
const authorsYaml = authors.map(a => `  - "${a}"`).join("\n");

// Type-specific middle sections
const middleSections = {
  attack: `## Target of the Attack
-
- Scheme / system:
- Security property targeted:

## Attack Goal
-
- Forgery / key recovery / bias / leakage / privacy break / availability break / model break

## Threat Model
-
- Adversary capabilities:
- Access assumptions:
- Required setup / preconditions:

## Attack Description
-
- Main idea:
- Step-by-step mechanism:
- Why it works:

## Impact
-
- What exactly breaks:
- Practical or theoretical:
- Conditions required:`,

  construction: `## Construction Goal
-
- What object is being constructed:
- What properties are required:

## Main Construction Idea
-
- High-level intuition:
- Design strategy:

## Building Blocks
-
- Primitive 1:
- Primitive 2:
- Assumption dependencies:

## Construction Walkthrough
-
- Key generation:
- Core algorithm(s):
- Output / verification / recovery:

## Security Model and Proof Idea
-
- Security notion:
- Proof approach:
- Reduction intuition:

## Efficiency / Tradeoffs
-
- Computation:
- Communication:
- Round complexity:
- Setup cost:`,

  engineering: `## Engineering Problem
-

## System / Implementation Goal
-

## System Design
-
- Architecture:
- Components:
- Interfaces:

## Practical Constraints
-
- Deployment setting:
- Performance bottlenecks:
- Reliability / usability / interoperability concerns:

## Implementation Details
-
- Language / platform:
- Libraries / tools:
- Important engineering choices:

## Evaluation
-
- Benchmarks:
- Datasets / workloads:
- Metrics:

## Results
-
- Main performance outcomes:
- Tradeoffs:
- Practical conclusions:`,

  foundations: `## Foundational Question
-

## Core Definitions
-
- Definition 1:
- Definition 2:
- Definition 3:

## Model / Formal Setting
-
- Objects studied:
- Adversary / environment:
- Assumptions:

## Main Theorems / Statements
-
- Theorem 1:
- Theorem 2:

## Proof Ideas
-
- Intuition:
- Key lemmas:
- Main techniques:

## Conceptual Contribution
-
- What new lens or formalism does this paper introduce?`,

  framework: `## Problem the Framework Addresses
-

## Framework Goal
-

## Scope
-
- What it covers:
- What it does not cover:

## Core Abstraction
-
- Main abstraction idea:
- Entities / roles:
- Interfaces / components:

## Workflow / Structure
-
- How the framework is meant to be used:
- Pipeline / phases / layers:

## Design Rationale
-
- Why this framework structure was chosen:
- What pain point it resolves:`,

  protocol: `## Protocol Goal
-
- What task the protocol solves:
- Intended setting:

## Parties and Roles
-
- Participants:
- Trusted setup / dealer / coordinator if any:

## Threat / Security Model
-
- Corruption model:
- Network model:
- Assumptions:
- Desired guarantees:

## Protocol Overview
-
- High-level flow:
- Main phases:

## Protocol Steps
-
### Setup
-
### Key Generation / Initialization
-
### Online / Interactive Phase
-
### Output / Verification
-

## Security Intuition
-
- Why the protocol should be secure:
- Main proof strategy:

## Efficiency
-
- Round complexity:
- Communication:
- Computation:
- Setup assumptions:`,

  survey: `## Scope of the Survey
-
- Topic covered:
- Time span:
- Exclusions:

## Main Taxonomy
-
- Category 1:
- Category 2:
- Category 3:

## Key Themes
-
- Theme 1:
- Theme 2:
- Theme 3:

## Important Papers Mentioned
-
- Paper A:
- Paper B:
- Paper C:

## Comparison Dimensions
-
- Security model:
- Efficiency:
- Assumptions:
- Practicality:
- Application domain:

## Survey Strengths
-
- What it organizes well:
- What is especially useful:

## Survey Weaknesses
-
- Missing areas:
- Biases:
- Outdated parts:`
};

const middle = middleSections[type];
-%>
---
title: "<% title %>"
aliases: []
authors:
<% authorsYaml %>
year: <% year %>
venue: "<% venue %>"
type: "<% type %>"
topics: []
tags:
  - paper

status: "to-read"
priority: "<% priority %>"
rating:

citation_key: "<% citationKey %>"
pdf: "<% pdfLink %>"
doi: ""
url: "<% url %>"

date_added: "<% dateAdded %>"
date_summarized: ""

compares_to: []
improves_on: []
related_work: []

summary_template: "<% type %>"
personal_take: ""
---

## One-Sentence Summary
-

## Why This Paper Matters
-

## Problem Statement
-

## Main Contribution
-

<% middle %>

## Comparison to Related Work
-

## Strengths
-
-

## Weaknesses
-
-

## My Take
-

## Open Questions
-
-

## Research Relevance
-
