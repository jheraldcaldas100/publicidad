\---

name: codex-review

description: Send the current implementation plan to OpenAI Codex CLI for iterative read-only review. Revise the plan from Codex feedback until it is approved or 5 rounds are reached.

user-invocable: true

disable-model-invocation: true

argument-hint: "\[optional-codex-model]"

\---



\# Codex Plan Review



Review the current implementation plan with OpenAI Codex CLI and iteratively improve it based on Codex feedback.



This skill is invoked manually with:



`/codex-review`



Maximum review rounds: 5.



\## Core rules



1\. Review the implementation plan currently present in the conversation.

2\. If there is no implementation plan, ask the user which plan should be reviewed.

3\. Codex must always run using the `read-only` sandbox.

4\. Codex is a reviewer only. It must not modify project files.

5\. Preserve the exact Codex session ID between review rounds.

6\. Never use `--last` when resuming a review.

7\. Do not hardcode a Codex model by default.

8\. If no model argument is supplied, allow Codex CLI to use its configured/default compatible model.

9\. If the user provides an argument to `/codex-review`, treat it as an explicit Codex model override.

10\. Stop immediately when Codex returns `VERDICT: APPROVED`.

11\. Never exceed 5 review rounds.



\## Step 1 — Prepare the plan



Create a temporary directory if necessary:



```bash

mkdir -p .claude/tmp

```



Generate a unique review identifier:



```bash

REVIEW\_ID="$(date +%s)-$RANDOM"

```



Define:



```bash

PLAN\_FILE=".claude/tmp/claude-plan-${REVIEW\_ID}.md"

REVIEW\_FILE=".claude/tmp/codex-review-${REVIEW\_ID}.md"

```



Write the complete current implementation plan to `$PLAN\_FILE`.



The plan must include all relevant:



\- requirements,

\- constraints,

\- architecture decisions,

\- data model changes,

\- migrations,

\- authentication and authorization considerations,

\- security requirements,

\- concurrency considerations,

\- error handling,

\- testing,

\- deployment,

\- rollback steps.



Do not intentionally omit relevant details from Codex.



\## Step 2 — Initial Codex review



If the user did not provide a model argument, run:



```bash

codex exec \\

&#x20; --skip-git-repo-check \\

&#x20; -s read-only \\

&#x20; -o "$REVIEW\_FILE" \\

&#x20; "Review the implementation plan in $PLAN\_FILE.



Inspect the existing codebase when useful for context, but do not modify any project files.



Evaluate the plan for:



1\. Correctness

2\. Missing implementation steps

3\. Architecture problems

4\. Failure modes and regressions

5\. Edge cases

6\. Race conditions and concurrency risks

7\. Data-loss risks

8\. Authentication and authorization risks

9\. Input validation and injection risks

10\. Secret or credential exposure

11\. Migration and rollback safety

12\. Testing completeness

13\. Unnecessary complexity

14\. Simpler alternatives where appropriate



Be specific and actionable.



When identifying an issue, explain what is wrong, why it matters, and what should change.



If the plan is ready for implementation, finish your response with exactly:



VERDICT: APPROVED



If changes are required, finish your response with exactly:



VERDICT: REVISE"

```



If the user explicitly supplied a model argument, use the same command but add:



```bash

\-m "$ARGUMENTS"

```



For example:



```bash

codex exec \\

&#x20; --skip-git-repo-check \\

&#x20; -m "$ARGUMENTS" \\

&#x20; -s read-only \\

&#x20; -o "$REVIEW\_FILE" \\

&#x20; "<review prompt>"

```



Do not add `-m` when `$ARGUMENTS` is empty.



\## Step 3 — Capture the Codex session



Capture the complete command output from the initial `codex exec`.



Locate:



```text

session id: <uuid>

```



Save the exact UUID as:



```text

CODEX\_SESSION\_ID

```



The session ID must be explicit.



Never replace it with:



```text

\--last

```



This is important because several Codex reviews may exist at the same time.



\## Step 4 — Read and present the review



Read `$REVIEW\_FILE`.



Present the result to the user in this format:



```text

\## Codex Review — Round N



\[Codex feedback]



VERDICT: APPROVED

```



or:



```text

\## Codex Review — Round N



\[Codex feedback]



VERDICT: REVISE

```



If Codex returns:



```text

VERDICT: APPROVED

```



stop the review loop and continue to the successful completion step.



If Codex returns:



```text

VERDICT: REVISE

```



continue to the revision step.



If the verdict line is missing but Codex identified unresolved substantive issues, treat the result as:



```text

VERDICT: REVISE

```



Do not falsely claim approval.



\## Step 5 — Revise the implementation plan



Address every substantive issue raised by Codex.



Do not blindly accept all Codex suggestions.



A Codex suggestion may be rejected or adapted when it:



\- contradicts an explicit user requirement,

\- misunderstands the existing codebase,

\- introduces unnecessary scope,

\- creates additional risk,

\- proposes unnecessary complexity,

\- conflicts with verified project constraints.



When rejecting a Codex recommendation, explicitly explain the reason.



Update the implementation plan in the conversation.



Then overwrite `$PLAN\_FILE` with the complete revised implementation plan.



Do not write only the changed sections. The file must contain the complete updated plan.



Show a concise revision summary:



```text

\### Revisions — Round N



\- Addressed: ...

\- Addressed: ...

\- Not adopted: ... because ...

```



\## Step 6 — Resume the same Codex session



For review rounds 2 through 5, resume using the exact saved session ID.



Run:



```bash

codex exec \\

&#x20; --skip-git-repo-check \\

&#x20; -s read-only \\

&#x20; resume "$CODEX\_SESSION\_ID" \\

&#x20; "I revised the implementation plan based on your previous review.



The complete updated plan is available at:



$PLAN\_FILE



Review the revised plan against all concerns you raised previously.



Inspect the codebase again if useful, but do not modify any files.



Verify whether every substantive issue from your previous review was actually resolved.



Also identify any new issue introduced by the revisions.



If the implementation plan is now solid and ready to implement, finish with exactly:



VERDICT: APPROVED



If changes are still required, finish with exactly:



VERDICT: REVISE"

```



Do not use:



```text

\--last

```



Do not use `-o` with `codex exec resume`.



Capture the resumed Codex response directly from stdout.



Verify that Codex reports the same:



```text

session id

```



as `$CODEX\_SESSION\_ID`.



Then evaluate the new verdict.



\## Step 7 — Continue the review loop



If Codex returns:



```text

VERDICT: REVISE

```



repeat:



1\. Analyze Codex feedback.

2\. Revise the plan.

3\. Update `$PLAN\_FILE`.

4\. Resume the same Codex session.

5\. Read the new verdict.



Continue until:



```text

VERDICT: APPROVED

```



or until 5 total review rounds have been completed.



Never exceed 5 rounds.



\## Step 8 — Resume failure



If resuming `$CODEX\_SESSION\_ID` fails:



1\. Do not use `--last`.

2\. Start a new Codex session.

3\. Keep `-s read-only`.

4\. Include the complete current implementation plan.

5\. Include a concise summary of previous Codex concerns.

6\. Include the revisions already made.

7\. Capture the new explicit session ID.

8\. Continue using that new session ID.



Tell the user that the previous Codex session could not be resumed and that a replacement review session was created.



\## Step 9 — Maximum rounds



If round 5 still returns:



```text

VERDICT: REVISE

```



stop.



Present:



```text

\## Codex Review — Final



Status: Maximum 5 rounds reached — not fully approved.



Remaining concerns:



\[remaining Codex concerns]

```



Do not claim that the plan passed review.



\## Step 10 — Successful completion



When Codex returns:



```text

VERDICT: APPROVED

```



present:



```text

\## Codex Review — Final



Status: APPROVED after N round(s)



\[final Codex feedback]



The implementation plan has passed iterative Codex review.

```



The reviewed and revised plan should remain available in the conversation so implementation can proceed from the approved version.



\## Step 11 — Cleanup



At the end of the review process, remove only the temporary files created by this review:



```bash

rm -f "$PLAN\_FILE" "$REVIEW\_FILE"

```



Do not delete unrelated files from:



```text

.claude/tmp

```



\## Safety requirements



Codex is acting only as a reviewer.



Every Codex review command, including resumed sessions, must use:



```text

\-s read-only

```



Never use any of the following for this skill:



```text

workspace-write

danger-full-access

\--dangerously-bypass-approvals-and-sandbox

```



Never instruct Codex to implement changes.



Never allow Codex to modify the codebase during `/codex-review`.



\## Expected workflow



The intended workflow is:



```text

Claude creates implementation plan

&#x20;       ↓

User runs /codex-review

&#x20;       ↓

Codex reviews plan in read-only mode

&#x20;       ↓

VERDICT: REVISE

&#x20;       ↓

Claude revises plan

&#x20;       ↓

Same Codex session is resumed

&#x20;       ↓

Codex verifies corrections

&#x20;       ↓

VERDICT: APPROVED

&#x20;       ↓

Claude presents approved final plan

```

