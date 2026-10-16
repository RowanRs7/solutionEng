# Curriculum Foundation and Discovery Unit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the self-study course foundation and publish the complete traditional-solutions unit on discovery and requirements.

**Architecture:** Markdown files are the product. A small dependency-free Python validator enforces metadata, required sections, unique slugs, and internal links; focused unit tests pin the validator contract. Course entry pages lead learners into eight independently readable lessons and one stage assessment.

**Tech Stack:** Chinese Markdown, Python 3 standard library, `unittest`, SVG, PNG

**Spec:** `docs/superpowers/specs/2026-10-16-ai-solutions-curriculum-design.md`

## Global Constraints

- Write learner-facing prose in Chinese; use stable English slugs for files and metadata.
- Target learners know basic Python but lack backend and enterprise-integration experience.
- Organize material by solution lifecycle, with layered progression inside each stage.
- Use `core`, `card`, or `advanced` as the lesson `type`; use `beginner`, `intermediate`, or `advanced` as `difficulty`.
- Every published lesson includes concrete ISO `last_reviewed`, duration, prerequisites, outcomes, and navigation links.
- Every core lesson follows the 16-section structure in the spec unless the section is explicitly marked “本课不适用” with a reason.
- Use **bold** for core conclusions, *italics* for first-use terms, `<u>` for error-prone points, and **<u>bold underline</u>** for security or production risks.
- Core code is fully runnable, comments every non-blank code line, and is followed by an explanation of the whole execution flow.
- JSON and other non-commentable formats remain valid; explain their fields below the code block.
- Prefer `fireworks-tech-graph` for technical diagrams and deliver both SVG and PNG.
- Do not add the comprehensive enterprise AI integration project in this phase.
- Keep runtime validation dependency-free; do not add a package manager solely for documentation checks.

## Review Focus

- A published lesson with missing or malformed Front Matter must fail validation with its path and a stable error code; Task 1 tests this.
- Duplicate lesson slugs must fail repository validation before links become ambiguous; Task 1 tests this.
- Broken relative Markdown links, including missing local anchors, must fail validation; Task 1 tests this.
- Files under `docs/_templates/` may contain template variables and must not be treated as published lessons; Task 1 tests this.
- A time-sensitive lesson must contain a concrete `last_reviewed: YYYY-MM-DD` value rather than a placeholder; Task 1 tests this.

## Delivery Sequence

This is plan 1 of 7:

1. Course foundation and traditional discovery requirements — this plan.
2. Traditional Web, network, API, and integration.
3. Traditional identity, security, data, and architecture.
4. Traditional development, testing, delivery, and operations.
5. AI foundations, discovery, model selection, and Prompt design.
6. AI RAG, tools, Workflow, and Agent.
7. AI application architecture, evaluation, security, governance, deployment, and operations.

## File Map

### Validation and templates

- `scripts/validate_docs.py`: parse course metadata and validate one document or the whole documentation tree.
- `tests/test_validate_docs.py`: unit tests for validator behavior and Review Focus cases.
- `docs/_templates/lesson-template.md`: canonical 16-section lesson template.
- `docs/_templates/assessment-template.md`: canonical stage-assessment template.

### Course entry and references

- `README.md`: repository purpose, audience, scope, and start link.
- `docs/00-start-here/00-course-introduction.md`: course promise and module boundaries.
- `docs/00-start-here/01-learning-guide.md`: self-study loop and progress rules.
- `docs/00-start-here/02-environment-setup.md`: Python, editor, terminal, and optional Docker setup.
- `docs/00-start-here/03-solution-lifecycle.md`: seven lifecycle stages and deliverables.
- `docs/00-start-here/04-knowledge-map.md`: current and planned units with status labels.
- `docs/reference/glossary.md`: canonical terms introduced by this delivery.
- `docs/reference/technology-index.md`: topic-to-lesson lookup.
- `docs/reference/troubleshooting-index.md`: symptom-to-lesson lookup.
- `docs/reference/architecture-deliverables.md`: deliverable definitions and examples.
- `docs/reference/further-learning.md`: curated categories for continued study.

### Traditional discovery unit

- `docs/01-traditional-solutions/00-overview.md`: module outcomes and lifecycle map.
- `docs/01-traditional-solutions/01-discovery-and-requirements/00-overview.md`: unit route and completion criteria.
- `01-solution-architect-role.md`: role, responsibilities, boundaries, and deliverables.
- `02-stakeholders-and-business-goals.md`: stakeholders, goals, outcomes, and conflicts.
- `03-current-state-and-business-process.md`: current-state investigation and process mapping.
- `04-users-roles-scenarios-and-use-cases.md`: actors, scenarios, and use cases.
- `05-functional-and-non-functional-requirements.md`: requirement categories and quality attributes.
- `06-boundaries-constraints-dependencies-assumptions.md`: solution boundary and constraint control.
- `07-priorities-scope-and-acceptance.md`: prioritization, scope, and measurable acceptance.
- `08-risks-and-requirement-deliverables.md`: risk register and requirement package.
- `09-stage-assessment.md`: closed-book check, scenario exercise, rubric, and answers.
- `docs/assets/diagrams/solution-lifecycle.svg`: editable lifecycle visual.
- `docs/assets/diagrams/solution-lifecycle.png`: compatible lifecycle preview.

---

### Task 1: Documentation Contract and Validator

**Files:**

- Create: `scripts/validate_docs.py`
- Create: `tests/test_validate_docs.py`
- Create: `docs/_templates/lesson-template.md`
- Create: `docs/_templates/assessment-template.md`

**Interfaces:**

- Consumes: Python 3 standard library and Markdown files below a supplied root.
- Produces: `Issue(path: Path, code: str, message: str, line: int | None)`, `parse_front_matter(text: str) -> tuple[dict[str, object], str]`, `github_anchor(heading: str) -> str`, `validate_document(path: Path, root: Path) -> list[Issue]`, `validate_repository(root: Path) -> list[Issue]`, and `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write failing validator tests**

Create tests named:

```python
def test_valid_core_lesson_has_no_issues(): ...
def test_missing_front_matter_reports_metadata_error(): ...
def test_duplicate_slugs_report_duplicate_slug(): ...
def test_broken_relative_file_link_reports_broken_link(): ...
def test_broken_local_anchor_reports_broken_anchor(): ...
def test_chinese_heading_anchor_is_resolved(): ...
def test_template_directory_is_ignored(): ...
def test_placeholder_review_date_reports_invalid_review_date(): ...
def test_missing_required_core_section_reports_missing_section(): ...
```

Assert exact stable codes: `metadata`, `duplicate-slug`, `broken-link`, `broken-anchor`, `invalid-review-date`, and `missing-section`.

- [ ] **Step 2: Run the validator tests and verify failure**

Run: `python -m unittest tests.test_validate_docs -v`

Expected: FAIL because `scripts.validate_docs` does not exist.

- [ ] **Step 3: Implement the validator interfaces**

Parse the scalar and list-valued YAML subset used by the templates without adding PyYAML. Ignore fenced code blocks when scanning headings and links. Skip `docs/_templates/`. For local anchors, lowercase Latin text, trim whitespace, replace runs of spaces with `-`, preserve Chinese letters and digits, remove other punctuation, and suffix duplicate headings with `-1`, `-2`, and so on. The CLI accepts one optional file-or-directory target, defaults to `docs`, and resolves repository links against `docs/`. Print one issue per line as `path:line [code] message`; return `0` with no issues and `1` otherwise.

- [ ] **Step 4: Create the canonical templates**

The lesson template contains all Front Matter keys and all 16 required headings. The assessment template contains outcomes, a knowledge checklist, scenario exercise, deliverable task, rubric, answers, review links, and next step.

- [ ] **Step 5: Run the unit tests**

Run: `python -m unittest tests.test_validate_docs -v`

Expected: 9 tests pass.

- [ ] **Step 6: Run the CLI smoke check**

Run: `python scripts/validate_docs.py docs`

Expected: exit code 0; template placeholders are ignored.

- [ ] **Step 7: Commit**

```bash
git add scripts/validate_docs.py tests/test_validate_docs.py docs/_templates
git commit -m "feat: add curriculum documentation contract"
```

### Task 2: Course Entry and Reference Structure

**Files:**

- Create: `README.md`
- Create: `docs/00-start-here/00-course-introduction.md`
- Create: `docs/00-start-here/01-learning-guide.md`
- Create: `docs/00-start-here/02-environment-setup.md`
- Create: `docs/00-start-here/03-solution-lifecycle.md`
- Create: `docs/00-start-here/04-knowledge-map.md`
- Create: `docs/reference/glossary.md`
- Create: `docs/reference/technology-index.md`
- Create: `docs/reference/troubleshooting-index.md`
- Create: `docs/reference/architecture-deliverables.md`
- Create: `docs/reference/further-learning.md`
- Test: `tests/test_validate_docs.py`

**Interfaces:**

- Consumes: Task 1 validator and templates.
- Produces: a single start path from `README.md`, canonical lifecycle vocabulary, and reference destinations that later lessons can link to.

- [ ] **Step 1: Add a failing repository-navigation test**

Add `test_course_entry_files_exist_and_readme_links_to_start()` and assert that all 11 files exist and `README.md` links to `docs/00-start-here/00-course-introduction.md`.

- [ ] **Step 2: Run the new test and verify failure**

Run: `python -m unittest tests.test_validate_docs.CourseRepositoryTests.test_course_entry_files_exist_and_readme_links_to_start -v`

Expected: FAIL with missing course entry files.

- [ ] **Step 3: Write the five start-here documents**

State the audience, two-module scope, 60–80 hour expectation, self-study loop, environment checks, seven lifecycle stages, status legend, and next-page navigation. Mark the third comprehensive project as out of scope.

- [ ] **Step 4: Write the five reference documents and README**

Seed only terms used in this delivery. Each index distinguishes published links from planned plain-text entries, so no placeholder link can break validation.

- [ ] **Step 5: Run the unit tests**

Run: `python -m unittest tests.test_validate_docs -v`

Expected: all tests pass.

- [ ] **Step 6: Validate the documentation tree**

Run: `python scripts/validate_docs.py docs`

Expected: exit code 0.

- [ ] **Step 7: Commit**

```bash
git add README.md docs/00-start-here docs/reference tests/test_validate_docs.py
git commit -m "docs: add course entry and reference structure"
```

### Task 3: Traditional Module and Discovery Unit Overviews

**Files:**

- Create: `docs/01-traditional-solutions/00-overview.md`
- Create: `docs/01-traditional-solutions/01-discovery-and-requirements/00-overview.md`

**Interfaces:**

- Consumes: lifecycle terms and navigation from Task 2.
- Produces: module outcomes, prerequisites, ordered lesson route, completion criteria, and links consumed by all discovery lessons.

- [ ] **Step 1: Write both overview documents**

The module overview explains why traditional engineering precedes AI. The unit overview lists lessons 01–09, estimated time, required deliverables, and the rule that a learner completes the assessment after all eight lessons.

- [ ] **Step 2: Verify metadata and links**

Run: `python scripts/validate_docs.py docs/01-traditional-solutions`

Expected: exit code 0.

- [ ] **Step 3: Verify navigation terms**

Run: `rg -n "需求发现|验收标准|09-stage-assessment" docs/01-traditional-solutions`

Expected: matches in both overview files.

- [ ] **Step 4: Commit**

```bash
git add docs/01-traditional-solutions
git commit -m "docs: introduce traditional solutions discovery unit"
```

### Task 4: Solution Architect Role Lesson

**Files:**

- Create: `docs/01-traditional-solutions/01-discovery-and-requirements/01-solution-architect-role.md`

**Interfaces:**

- Consumes: course lifecycle and unit overview.
- Produces: definitions for solution, architecture, stakeholder, constraint, deliverable, and decision; later lessons reuse these terms.

- [ ] **Step 1: Write the lesson from the canonical template**

Teach role boundaries, lifecycle responsibilities, collaboration with product/development/security/operations, common deliverables, and the difference between deciding and documenting. Include a small “online retail integration” scenario used throughout the unit.

- [ ] **Step 2: Add the self-check**

Include 3–5 concept questions, one role-boundary scenario, an optional responsibility-mapping exercise, and answers that explain incorrect options.

- [ ] **Step 3: Validate the lesson**

Run: `python scripts/validate_docs.py docs/01-traditional-solutions/01-discovery-and-requirements/01-solution-architect-role.md`

Expected: exit code 0.

- [ ] **Step 4: Commit**

```bash
git add docs/01-traditional-solutions/01-discovery-and-requirements/01-solution-architect-role.md
git commit -m "docs: teach the solution architect role"
```

### Task 5: Stakeholders and Business Goals Lesson

**Files:**

- Create: `docs/01-traditional-solutions/01-discovery-and-requirements/02-stakeholders-and-business-goals.md`
- Modify: `docs/reference/glossary.md`

**Interfaces:**

- Consumes: role and deliverable definitions from Task 4.
- Produces: stakeholder map, goal statement, outcome metric, conflict record, and decision-owner concepts.

- [ ] **Step 1: Write the lesson**

Use the retail scenario to identify sponsors, users, operators, security, compliance, data owners, and external providers. Contrast business goals, outputs, outcomes, solution ideas, and measurable indicators.

- [ ] **Step 2: Add a stakeholder exercise and rubric**

Require learners to create a stakeholder table with influence, interest, concerns, decisions, and communication method. Supply a rubric and sample answer.

- [ ] **Step 3: Update the glossary**

Add stakeholder, sponsor, business goal, output, outcome, indicator, concern, and decision owner. Link each term to its first full explanation.

- [ ] **Step 4: Validate the documentation tree**

Run: `python scripts/validate_docs.py docs`

Expected: exit code 0.

- [ ] **Step 5: Commit**

```bash
git add docs/01-traditional-solutions/01-discovery-and-requirements/02-stakeholders-and-business-goals.md docs/reference/glossary.md
git commit -m "docs: teach stakeholder and goal discovery"
```

### Task 6: Current State and Business Process Lesson

**Files:**

- Create: `docs/01-traditional-solutions/01-discovery-and-requirements/03-current-state-and-business-process.md`
- Modify: `docs/reference/architecture-deliverables.md`

**Interfaces:**

- Consumes: stakeholder goals from Task 5.
- Produces: current-state inventory, interview guide, process steps, pain-point evidence, and as-is process map.

- [ ] **Step 1: Write the lesson**

Teach interviews, observation, document review, system inventory, process mapping, evidence collection, and the difference between symptoms and causes. Continue the retail scenario with a manual order-refund process.

- [ ] **Step 2: Add a current-state investigation exercise**

Provide incomplete interview notes. Ask learners to separate facts, assumptions, unanswered questions, pain points, and candidate metrics; include a scored reference answer.

- [ ] **Step 3: Validate the documentation tree**

Run: `python scripts/validate_docs.py docs`

Expected: exit code 0.

- [ ] **Step 4: Commit**

```bash
git add docs/01-traditional-solutions/01-discovery-and-requirements/03-current-state-and-business-process.md docs/reference/architecture-deliverables.md
git commit -m "docs: teach current-state investigation"
```

### Task 7: Users, Roles, Scenarios, and Use Cases Lesson

**Files:**

- Create: `docs/01-traditional-solutions/01-discovery-and-requirements/04-users-roles-scenarios-and-use-cases.md`

**Interfaces:**

- Consumes: current-state actors and process from Task 6.
- Produces: actor, persona, system role, scenario, use case, precondition, main flow, alternate flow, and postcondition definitions.

- [ ] **Step 1: Write the lesson**

Contrast users with system roles and scenarios with requirements. Model the refund scenario as a concise use case, including alternate and failure flows.

- [ ] **Step 2: Add a use-case conversion exercise**

Give an ambiguous request and require a structured use case. Provide a rubric covering actor, trigger, preconditions, success flow, exceptions, and postconditions.

- [ ] **Step 3: Validate the documentation tree**

Run: `python scripts/validate_docs.py docs`

Expected: exit code 0.

- [ ] **Step 4: Commit**

```bash
git add docs/01-traditional-solutions/01-discovery-and-requirements/04-users-roles-scenarios-and-use-cases.md
git commit -m "docs: teach scenarios and use cases"
```

### Task 8: Functional and Non-Functional Requirements Lesson

**Files:**

- Create: `docs/01-traditional-solutions/01-discovery-and-requirements/05-functional-and-non-functional-requirements.md`
- Modify: `docs/reference/glossary.md`

**Interfaces:**

- Consumes: use cases from Task 7.
- Produces: functional requirement, quality attribute, quality-attribute scenario, and measurable requirement patterns.

- [ ] **Step 1: Write the lesson**

Cover performance, availability, scalability, security, privacy, usability, maintainability, operability, compatibility, compliance, and cost. Replace vague adjectives with conditions and measurable responses.

- [ ] **Step 2: Add a requirement-rewrite exercise**

Provide at least eight vague statements such as “系统要快” and “系统必须安全.” Require measurable revisions with context, stimulus, response, and threshold; include annotated answers.

- [ ] **Step 3: Validate the documentation tree**

Run: `python scripts/validate_docs.py docs`

Expected: exit code 0.

- [ ] **Step 4: Commit**

```bash
git add docs/01-traditional-solutions/01-discovery-and-requirements/05-functional-and-non-functional-requirements.md docs/reference/glossary.md
git commit -m "docs: teach measurable requirements"
```

### Task 9: Boundaries, Constraints, Dependencies, and Assumptions Lesson

**Files:**

- Create: `docs/01-traditional-solutions/01-discovery-and-requirements/06-boundaries-constraints-dependencies-assumptions.md`

**Interfaces:**

- Consumes: functional and quality requirements from Task 8.
- Produces: in-scope/out-of-scope statement, context inventory, constraint log, dependency log, and assumption log.

- [ ] **Step 1: Write the lesson**

Explain system boundary, external actor, upstream/downstream dependency, organizational constraint, technical constraint, assumption, and validation owner. Show how an untested assumption becomes a project risk.

- [ ] **Step 2: Add a boundary-classification exercise**

Ask learners to classify retail systems and responsibilities as inside, outside, or undecided; provide a reference table and reasons.

- [ ] **Step 3: Validate the documentation tree**

Run: `python scripts/validate_docs.py docs`

Expected: exit code 0.

- [ ] **Step 4: Commit**

```bash
git add docs/01-traditional-solutions/01-discovery-and-requirements/06-boundaries-constraints-dependencies-assumptions.md
git commit -m "docs: teach solution boundaries and constraints"
```

### Task 10: Priorities, Scope, and Acceptance Lesson

**Files:**

- Create: `docs/01-traditional-solutions/01-discovery-and-requirements/07-priorities-scope-and-acceptance.md`

**Interfaces:**

- Consumes: scoped requirements and constraints from Task 9.
- Produces: priority record, minimum viable scope, change decision, acceptance criterion, and traceability relationship.

- [ ] **Step 1: Write the lesson**

Teach MoSCoW as a conversation tool, value/risk/effort trade-offs, scope baseline, change control, Given/When/Then acceptance criteria, and traceability from business goal to testable result.

- [ ] **Step 2: Add prioritization and acceptance exercises**

Give conflicting retail requirements and a fixed delivery constraint. Require a prioritized scope and measurable acceptance criteria; include a decision rationale and rubric.

- [ ] **Step 3: Validate the documentation tree**

Run: `python scripts/validate_docs.py docs`

Expected: exit code 0.

- [ ] **Step 4: Commit**

```bash
git add docs/01-traditional-solutions/01-discovery-and-requirements/07-priorities-scope-and-acceptance.md
git commit -m "docs: teach scope and acceptance design"
```

### Task 11: Risks, Requirement Deliverables, and Stage Assessment

**Files:**

- Create: `docs/01-traditional-solutions/01-discovery-and-requirements/08-risks-and-requirement-deliverables.md`
- Create: `docs/01-traditional-solutions/01-discovery-and-requirements/09-stage-assessment.md`
- Modify: `docs/reference/architecture-deliverables.md`

**Interfaces:**

- Consumes: all artifacts from Tasks 4–10.
- Produces: risk register, requirement package checklist, scored stage assessment, answer key, and remediation links.

- [ ] **Step 1: Write the risks and deliverables lesson**

Teach probability, impact, exposure, trigger, owner, mitigation, contingency, and residual risk. Assemble goals, stakeholders, process, use cases, requirements, boundary, assumptions, priorities, acceptance criteria, and risks into one requirement package.

- [ ] **Step 2: Write the stage assessment**

Include at least 15 mixed concept questions, one fresh business scenario, one requirement-package task, a 100-point rubric, full answers, common wrong-answer analysis, and score-based review paths.

- [ ] **Step 3: Validate the complete documentation tree**

Run: `python scripts/validate_docs.py docs`

Expected: exit code 0.

- [ ] **Step 4: Verify that lessons contain answers**

Run: `rg -L "答案与解析|参考答案" docs/01-traditional-solutions/01-discovery-and-requirements/*.md`

Expected: only the two overview files may be listed.

- [ ] **Step 5: Commit**

```bash
git add docs/01-traditional-solutions/01-discovery-and-requirements docs/reference/architecture-deliverables.md
git commit -m "docs: complete discovery requirements unit"
```

### Task 12: Lifecycle Diagram, Indexes, and Release Verification

**Files:**

- Create: `docs/assets/diagrams/solution-lifecycle.svg`
- Create: `docs/assets/diagrams/solution-lifecycle.png`
- Modify: `docs/00-start-here/03-solution-lifecycle.md`
- Modify: `docs/00-start-here/04-knowledge-map.md`
- Modify: `docs/reference/glossary.md`
- Modify: `docs/reference/technology-index.md`
- Modify: `docs/reference/troubleshooting-index.md`

**Interfaces:**

- Consumes: all published lessons and glossary terms from Tasks 2–11.
- Produces: final navigation, SVG/PNG lifecycle visual, and a validation-clean first course release.

- [ ] **Step 1: Generate the lifecycle diagram with `fireworks-tech-graph`**

Show the seven lifecycle stages, the iterative feedback loop from operations to discovery, and the current unit highlight. Use Chinese labels and export matching SVG and PNG files.

- [ ] **Step 2: Add accessible diagram integration**

Embed the SVG in the lifecycle lesson, link the PNG fallback, add concise alt text, and explain the same relationships in prose.

- [ ] **Step 3: Finalize indexes**

Link every published lesson from the knowledge map and relevant indexes. Add every defined term once to the glossary; keep unpublished curriculum items as unlinked “计划中” entries.

- [ ] **Step 4: Run all unit tests**

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 5: Validate the complete documentation tree**

Run: `python scripts/validate_docs.py docs`

Expected: exit code 0 and no output.

- [ ] **Step 6: Check the Git diff**

Run: `git diff --check`

Expected: exit code 0.

- [ ] **Step 7: Verify diagram file types**

Run: `file docs/assets/diagrams/solution-lifecycle.svg docs/assets/diagrams/solution-lifecycle.png`

Expected: one SVG image and one PNG image.

- [ ] **Step 8: Perform a manual learner-path check**

Starting at `README.md`, follow every “下一课” link through the assessment and every remediation link back to its lesson. Confirm that a learner never reaches a dead end.

- [ ] **Step 9: Commit**

```bash
git add docs
git commit -m "docs: release discovery requirements course unit"
```
