# guided-onboarding Specification

## Purpose
Let Claude Code run bimai's onboarding interview with its own question tool (options with explanations,
recommended defaults, multi-select, and a free-text "Other"), while bimai decides which values are valid.

## Requirements

### Requirement: Interview specification
`bimai init --interview [PATH] [--role ROLE]` SHALL print JSON describing the interview without writing
anything: a list of steps, each with at most four questions. Every question SHALL have an `id` (the
matching `bimai init` flag), the question text, a `header` of at most 12 characters, a `kind` (`choice`
or `text`), `multi_select`, two to four `options` (each with `label`, `description` and `value`) with the
recommended option first, the `recommended` value(s), and for choices the complete list of `allowed`
values with their labels, so a free-text answer can be mapped. Without `--role`, the output SHALL contain
step 1 (project name, person, role, language) and say that step 2 needs the role. With `--role`, it SHALL
contain step 2 (goals, tools, VS Code familiarity). It SHALL exit with code 2 when the folder is already a
bimai project or the role is unknown (with suggestions).

#### Scenario: Step 1
- **WHEN** the user runs `bimai init --interview` in a folder named `a2-tunnel`
- **THEN** the output has a role question with the four roles as options and the project name question recommends `a2-tunnel`

#### Scenario: Within the tool's limits
- **WHEN** the interview is generated for any role, with or without scan results
- **THEN** every step has at most four questions, every question two to four options, and every header at most 12 characters

### Requirement: Options that fit the person
For goals, the options SHALL be the four goals most relevant to the chosen role, with the role's default
goals recommended. For tools, the options SHALL start with the tools found by the folder scan (each saying
which file suggested it), filled up with the role's typical tools, at most four, with the found tools
recommended. Text questions SHALL offer the suggestions bimai has (folder name, git user name) and, when
there are fewer than two, an option that tells the person to type their own answer.

#### Scenario: Found tools first
- **WHEN** the folder contains a `.rvt` file and the role is BIM coordinator
- **THEN** Revit is the first tools option, its description names the file, and it is recommended

#### Scenario: Goals for a design coordinator
- **WHEN** the role is design coordinator
- **THEN** the goals options are requirements, risks, planning and reporting, all recommended

### Requirement: Forgiving role matching
When a role can't be matched, the error SHALL name the closest roles (by similarity of words), so the
person or Claude can pick one, in addition to listing all roles.

#### Scenario: Close role
- **WHEN** the role is "BIM coordinater"
- **THEN** the error suggests "BIM coordinator"

### Requirement: Guided start prompt
The start prompt published on the install page and the landing page SHALL instruct Claude to get the
interview from `bimai init --interview`, ask each step with Claude Code's question tool using the given
headers, options, multi-select and recommended order, map "Other" answers to the allowed values (and ask
when unsure), request step 2 with the chosen role, show the proposed team from a dry run, and only write
after a final yes.

#### Scenario: Prompt content
- **WHEN** the start prompt is published
- **THEN** it names `bimai init --interview`, the question tool, mapping of "Other" answers, and the final confirmation
