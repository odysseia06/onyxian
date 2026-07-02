---
type: daily
created: <% tp.date.now("YYYY-MM-DD") %>
status: open
tags:
  - daily
date: <% tp.date.now("YYYY-MM-DD") %>
---

# <% tp.date.now("YYYY-MM-DD") %>

## Tasks

- [ ]

<%*
const today = tp.date.now("YYYY-MM-DD");
tR += "### Due Today\n";
tR += "```tasks\n";
tR += "due on " + today + "\n";
tR += "not done\n";
tR += "sort by priority reverse\n";
tR += "hide backlink\n";
tR += "path does not include Templates\n";
tR += "```\n\n";
tR += "### Scheduled Today\n";
tR += "```tasks\n";
tR += "scheduled on " + today + "\n";
tR += "not done\n";
tR += "sort by priority reverse\n";
tR += "hide backlink\n";
tR += "path does not include Templates\n";
tR += "```\n\n";
tR += "### Overdue\n";
tR += "```tasks\n";
tR += "due before " + today + "\n";
tR += "not done\n";
tR += "sort by priority reverse\n";
tR += "sort by due\n";
tR += "hide backlink\n";
tR += "path does not include Templates\n";
tR += "```\n\n";
tR += "### Carry-over\n";
tR += "```tasks\n";
tR += "not done\n";
tR += "path includes Daily-Notes\n";
tR += "sort by priority reverse\n";
tR += "hide backlink\n";
tR += "path does not include Templates\n";
tR += "```\n\n";
tR += "### Captured\n";
tR += "```tasks\n";
tR += "not done\n";
tR += "tags include #captured\n";
tR += "sort by priority reverse\n";
tR += "hide backlink\n";
tR += "path does not include Templates\n";
tR += "```\n\n";
tR += "### Completed Today\n";
tR += "```tasks\n";
tR += "done on " + today + "\n";
tR += "short mode\n";
tR += "path does not include Templates\n";
tR += "```";
-%>

## Notes

-

## Reading / Research

-

## Journal

-
