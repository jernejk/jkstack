# Watcher contract

The watcher is a plain script, in any language, that polls one PR through the GitHub CLI or API and exits
when something needs the agent. It never calls a model, never edits code, never replies and never merges.
Its whole job is to turn "keep an eye on this" into one exit with everything the agent needs to act.

## Launch

```sh
watch-pr 123 --repo owner/name [--auto-merge] [--require-approver LOGIN] [--require-check NAME] \
  [--bot LOGIN] [--ignore-comment ID] [--ignore-user LOGIN] [--marker TEXT] [--poll 60] [--timeout MIN] [--once]
```

- `--auto-merge`: the user said "merge if all good". The watcher still never merges; it only reports
  whether merging is safe.
- `--require-approver`: every named login must have approved the current head.
- `--require-check`: a named check must succeed on the current head; a skipped run blocks.
- `--bot`: logins treated as review bots. Everything else is human.
- `--ignore-comment`, `--ignore-user`: threads the agent left open on purpose.
- `--marker`: the footer that marks the agent's own replies (default 🤖).
- `--once`: one pass, no waiting. Used for the re-check before a merge. When nothing is actionable yet,
  it exits with the reason the PR is waiting on (`waiting_on_human`, or `timeout` while checks or bots
  are still running), never `all_green`.
- `--stage pre-publish --gate-bot LOGIN`: turns on the optional draft gate. Without it, draft state is
  reported but never changed.
- Timeouts: about 30 minutes by default; about 4 hours with `--auto-merge` or `--require-approver`,
  because approvals take a while.

Run it as a background command the harness wakes you from when it exits. Claude Code and Codex can both
do that. Without background commands, run it in the foreground with a short timeout and relaunch.

## Output

A human-readable line, then one final machine line: `BABYSIT_JSON {...}`. Give each reason its own exit
code so the success or failure flag on the background notification already tells the agent what happened.

| Exit | `reason` |
| ---: | --- |
| 0 | `all_green` |
| 10 | `ci_failed` |
| 11 | `unresolved_comments` |
| 13 | `timeout` |
| 14 | `not_mergeable` |
| 15 | `change_request_stale` |
| 16 | `stale_approval_risky` |
| 17 | `waiting_on_human` |
| 20 | `merged` |
| 21 | `closed` |
| 23 | `pre_publish_ready` (draft gate only) |
| 2 | `error`, with `detail` |

The JSON carries enough that the agent needs `gh` only to act (reply, resolve, push, merge) or to read a
failing log:

| Field | Meaning |
| --- | --- |
| `pr_state`, `merged`, `is_draft`, `head_branch`, `base_branch`, `head_sha`, `url` | Where the PR is. Merge with `head_sha`. |
| `ci`, `ci_failed[]` | `passing`, `failed`, `running` or `none`, and the failed checks with run ids. |
| `approval`, `approvers[]`, `approval_required` | Review decision, human logins whose latest review approves (on head when any are), and whether the base needs a review: `true`, `false`, or `null` when unreadable. |
| `merge_state`, `merge_blocked_reason`, `stalled` | GitHub's merge state, and in words why a ready PR is not merging. |
| `approval_stale`, `approval_delta` | A commit landed after the approval, and what changed since: `summary`, `risky`, `reasons[]`. |
| `unresolved_detail[]` | One entry per open comment: `id`, `thread_id`, `author`, `source` (`bot` or `human`), `body`, `path`, `line`, `url`. |
| `bot_working` | A review bot or coding agent is still busy on this PR. |
| `stale_reviewers[]`, `requested_reviewers[]` | Humans whose latest review predates the head, and who is already requested. |
| `auto_merge` | True only when every merge gate below passed. |
| `elapsed` | How long the watcher ran. |

When several reasons hold at once, report the first in this order: `merged`, `closed`, `error`,
`ci_failed`, `unresolved_comments`, `not_mergeable`, `stale_approval_risky`, `change_request_stale`,
`pre_publish_ready`, `all_green`. Failures and open comments come before readiness, so a green
summary never hides work.

Keep state between launches small and explicit: the count of approval-wait timeouts for this PR and
head, reset when the head changes or an approval arrives. Store it beside the watcher, keyed by
repository and PR number.

## Rules the watcher keeps

- **Exit on the first actionable state; otherwise wait.** Actionable means a failed check, an unresolved
  comment, a merge blocker, a merge or close, or green and quiet.
- **Green means quiet.** No `all_green` while a check is running or a review bot or agent is still working.
  Detect "still working" from whatever the bot exposes: a task API, timeline events, or a review on the
  current head. Guard against a started event that never finished.
- **Never hold silently on a gate nothing will clear.** Once approval is satisfied, any gate still blocking
  after about five quiet minutes (a required check that never starts, no CI at all, a merge state GitHub
  never computes) exits `not_mergeable` with `stalled`. The only silent waits are a missing human
  approval and a check that is still running.
- **Skip the agent's own replies.** Drop a thread whose latest comment is the agent's marked reply, so the
  watcher does not wake on itself. The marker alone does not prove authorship: someone else's
  agent-drafted review can carry the same footer. Match the author too.
- **Hydrate everything.** Each comment arrives with its thread id and location, so the agent triages,
  replies and resolves from the JSON without another lookup.
- **Merge gates for `auto_merge: true`:** CI `passing` (never `none`, and verified even when told to ignore
  CI elsewhere, because the merge button can bypass checks), merge state `CLEAN`, every required check
  green on the head, and a human approval on the head when the base needs one, or an older approval with
  a low-risk delta. A bot approval never satisfies this gate.
- **Unknown means required.** Read the base branch's rulesets and classic protection. A readable rule that
  needs zero reviews means no approval is needed. Anything unreadable is `null` and treated as required,
  so the loop never merges past a gate it could not see.
- **Bounded waiting for approval.** After a fixed number of timeouts with only a human approval missing,
  exit `waiting_on_human` and stop the relaunch cycle.
- **Missing signals are conservative.** A bot whose activity cannot be read counts as still working
  until a timeout, and an approval delta that cannot be computed counts as risky.
- **Validate inputs at launch.** Unknown `--require-approver` logins and unknown repos fail fast with
  `error`.

## Testing it

Drive the decision logic from recorded GitHub responses, not live PRs: one fixture per exit reason, plus
the edge cases that cost a merge when wrong (an approval on an old head, CI `none`, a stalled required
check, the agent's own reply as the latest comment, an unreadable ruleset). Add a loop test for every new
gate. Then watch one real PR of your own end to end before trusting `--auto-merge`.
