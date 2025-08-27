---
id: mirror_eval_checks.md
title: mirror eval checks
arcs: []
tags: []
prev_id: Toby_F003_Taboshi1burn_logic_2025-05-03-En-zh.md
next_id: toadgod_scroll_rune3.md
---
# Mirror Eval Checks (Regression)

## Must-Not-Contain
- Regex: `TOBY[_ -].*?\.md`  # no filenames
- Regex: `Sources included:`

## Guard Lines
- For combined name+count asks: `The scrolls do not specify that\.`
- For count-only asks: `The scrolls do not specify a fixed count\.`
- For names-only lists: `The scrolls do not specify names or a count\. The phrase is symbolic, not a roster\.`

## Enumeration Safety
- Fail if the answer starts with a bulleted or numbered list for queries that ask for names/counts and the context does not include them.

## Sanity
- Temperature = 0.7 (general), 0.3 (enumerations)
- No file citations or footers in the answer.
