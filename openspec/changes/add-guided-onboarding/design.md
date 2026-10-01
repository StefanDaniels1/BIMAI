# Design

## Context

Claude Code's question tool (`AskUserQuestion`) asks one to four questions per call; each question has a
header of at most 12 characters, two to four options (label + description), optional multi-select, and
always an automatic "Other" with free text. bimai has 4 roles (fits), 8 goals and 14 tools (don't fit), so
bimai chooses the most relevant four per person.

## Decisions

- **The script owns the interview, Claude owns the conversation.** `interview.py` builds the steps as
  data (deterministic, tested); Claude renders them with its tool and maps free text. Everything still
  ends in `bimai init` flags that the script validates, so a bad mapping fails loudly instead of silently.
- **Two steps,** because goals and tools depend on the role: step 1 = name, person, role, language (4
  questions); step 2 = goals, tools, VS Code (3). Each fits one tool call.
- **Relevance from the catalogue:** each preset gets `goal_options` (4, its defaults first) and
  `typical_tools` (up to 4); found tools always come first. Labels and descriptions live in the
  catalogue (`tools.yaml` goal labels, preset descriptions), so the same text appears in the terminal
  interview and in Claude's options.
- **Text questions** carry suggestions as options; with fewer than two suggestions, a "Type it yourself"
  option points to "Other". `kind: "text"` tells Claude that free text is the normal answer, not an
  exception.
- **Role suggestions** with `difflib` on normalized names and match terms; no new dependency.

## Risks / Trade-offs

- Claude may map a free-text answer wrongly → the prompt asks it to confirm uncertain mappings, and the
  dry run shows the team before anything is written.
