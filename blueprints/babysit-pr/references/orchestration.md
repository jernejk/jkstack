# Orchestration

What to do for each handoff. Carry the launch flags forward every time.

## `ci_failed`

1. Read `ci_failed` and fetch the log: `gh run view <run-id> --log-failed`.
2. Caused by this PR (lint, formatter, a test it touched): fix, commit, push, verify, relaunch.
3. Unrelated or infrastructure: re-run once with `gh run rerun <run-id> --failed`. If it fails again,
   stop and report. A fix for it belongs on its own branch, unless the user agrees to widen this PR.

## `unresolved_comments`

For each entry in `unresolved_detail`:

1. Open `path` at `line` and verify the claim against the real file and its surroundings.
2. Classify with the [reviewer policy](reviewer-policy.md): apply, decline with a reason, ask the user,
   or leave a human thread alone.
3. Apply the accepted fixes as one batch, run the affected tests, commit, push.
4. [Verify the push landed](#verify-the-push-landed), then reply on each thread, then resolve it with
   `thread_id`.
5. Relaunch with an ignore entry for every thread you deliberately left open.

**Plan before fixing.** For anything larger than a one-liner, write the plan first: the comment, the file
and line, the intended change, and the command that proves it. Triage stays with the lead agent, because
deciding whether a bot is right is review work. A mechanical fix with a check can go to a cheaper worker,
or back to the agent that wrote the PR if it is still reachable, when the user allows delegation. Review
any delegated diff before committing.

**Smell-test big commits.** Before committing a large or multi-file change, run a quick read-only style
pass over the diff for the repository's conventions: noisy or narrating comments, leftover debug output,
issue numbers in code comments. Skip it for one-liners. It is a soft gate; the user can say "just commit".

Follow the repository's commit conventions, including its rule on trailers. If a push is rejected because
someone merged the base from the web UI, `git pull --rebase` and push again.

## Verify the push landed

A fix you think is in but is not is silent, and with merge authority the PR can merge on the next green
tick. A common cause is an edit made before `git mv` that gets committed as a content-free rename. After
every push, before replying "Applied" and before relaunching:

1. `git status --porcelain` lists none of the files you meant to commit.
2. `git show <sha> -- <path>` shows the change you intended, not a zero-line rename.
3. `gh pr view <PR> --json headRefOid --jq .headRefOid` returns `<sha>`. This checks GitHub's view of
   the PR itself, so a push to the wrong remote or branch cannot pass.

The user may waive this check. The honesty rule is never waived: when a fix did not land, say exactly
what is missing instead of reporting it as done.

## `not_mergeable` and conflicts

Fixing a conflict is part of babysitting. Do it without asking, unless the user said to leave it.

**Ownership first.** Compare `gh api user --jq .login` with the PR author, and note any approval.

- **Another author's branch:** never push, not even a base merge. Report the command they would run.
- **Your branch, not approved:** merge the base in and push. A rebase or restack that needs
  `--force-with-lease` waits for the user's yes.
- **Your branch, approved:** never force-push. Merge the base in only if the rules keep approvals across
  a push ([stale approvals](#stale-approvals)); otherwise report.

**Diagnose before resolving.**

- **Behind base, no conflict:** update the branch.
- **Stale stack:** the branch was stacked on a PR that has since been squash-merged, so its old commits
  fight their squashed copy in the base. Do not hand-resolve those. Replay only this PR's own commits:
  `git rebase --onto origin/<base> <old-parent-head>`. A diff of dozens of "conflicting" files often
  collapses to the handful the PR really changes.
- **Genuine conflict:** read both sides, keep the intent of both, and let the PR's purpose break ties.
  Never take a whole side of a hunk you have not read.

**Prove it before pushing.** Rehearse in a throwaway worktree, check that `git diff --stat
origin/<base>..HEAD` is the PR's intended delta, build or test when code changed, then push and verify.
Report which fix you used, the new SHA, and the before and after file counts if the diff shrank.

If a hunk forces a choice between two defensible behaviours that neither the code nor the PR settles,
resolve everything else, then bring that one hunk to the user with your read and both options.

Draft state, a required check that never ran, or a merge state still blocked after approval: report which,
and do not merge around it.

## Stale approvals

"A commit landed after the approval" is derived, not a GitHub rule. Whether it blocks is the base branch's
decision, so read it:

```sh
gh api --paginate repos/<owner>/<name>/rules/branches/<base> \
  --jq '[.[] | select(.type == "pull_request") | .parameters]'
gh api repos/<owner>/<name>/branches/<base>/protection --jq .required_pull_request_reviews
```

Rulesets and classic branch protection can both apply; combine them, and the stricter setting wins. A
protection read that fails for lack of permission is unknown, and unknown counts as blocking.

- `dismiss_stale_reviews_on_push: false` (rulesets) or `dismiss_stale_reviews: false` (classic): the
  repository keeps approvals across pushes on purpose.
- `require_last_push_approval: true`: someone other than the person who made the most recent reviewable
  push must approve after it. A review on the head commit is necessary but not sufficient; check who
  pushed last.
- Both satisfied, merge state `CLEAN`, decision `APPROVED`: GitHub's gate is met. Refusing here would
  block a merge the user authorised over a rule the repository does not have.

Then size the decision to the change since sign-off. A small, low-risk delta with everything green:
merge and report it. A large or risky delta (auth, money, schemas, concurrency, public API) sends the
question to the user, even when GitHub would allow the merge. Only a genuinely unmet rule is a hard stop.

## `change_request_stale`

Everything is green and a reviewer's change request has been addressed by a later commit. Check the
substance of their comment is really handled and run the smell test on the new commits, so the reviewer
is not sent back to noise. With merge authority, re-request them (`gh pr edit <PR> --add-reviewer LOGIN`)
and relaunch. Without it, offer that command and wait for the user.

## Merge

On `all_green` with `auto_merge: true` and explicit wording: run the watcher once more with `--once` and
the same flags. Merge only if that fresh pass also returns `all_green` with `auto_merge: true`; any other
reason goes back through the handling above. Merge with the fresh pass's `head_sha` and the repository's
usual method. If the merge fails, do not retry blindly: report it, notify, stop.

## `merged`: close-out

Run once, after an actual merge by you or anyone else. A PR that ends green without merging is not merged.

1. Check the PR body is complete and the linked issue closed.
2. Optionally add a status note where the project keeps one.
3. Tear down only what this branch created, and ask first unless the user said "clean up once merged".
   Never remove a dirty worktree. Never remove the main checkout: switch it to the default branch and
   fast-forward, unless it has uncommitted work. Remove only containers this branch started; list data
   volumes, never delete them. A squash merge makes the branch look unmerged to git, so deleting it needs
   `-D`, and only after confirming the PR merged and the local branch tip equals the PR's merged
   `headRefOid`. Anything committed after that is unmerged work: keep the branch and report it.

## Notifications

Notify only in these cases, under about 200 characters, leading with the action:

1. The user is needed: a human comment that needs a decision, an out-of-scope CI stop, a risky stale
   approval.
2. Approved and ready to merge, without merge authority.
3. Approved and merged.
4. Approved but unable to merge, with the reason.

Never for a nit you applied, a re-run you started or CI still running. If the watcher already notified for
its own exit, do not repeat it.

## Optional draft gate

For teams that review a finished batch before publishing, model **draft → pre-publish → published**:

- **Draft.** Normal commits and pushes while you work. The watcher reports draft work and stays out of the way.
- **Pre-publish.** The PR stays a GitHub draft while a named review bot, or a local review CLI, reviews the
  current head. Fix all findings as one batch, run local checks, push, relaunch. Never re-run a review on
  an unchanged head. The watcher exits `pre_publish_ready` when nothing is unresolved and that review covers
  the head. That means review-clean, not merge-ready.
- **Published.** Mark ready only after `pre_publish_ready` and the user's go-ahead, then read back the draft
  flag and head. Reworking a published PR means returning it to draft first, and the user decides that.

Without the gate, drafts are watched like any other PR and draft state is never changed.

## Summaries

Per handoff, three lines:

```
Handled: <by source, e.g. "bot-a 1 applied, bot-b 2 declined"> <sha if pushed>
CI: <running | passing | failed (names)>
Watcher: <relaunched [+ ignored N] | stopped (reason)>
```

At the end: totals by source and outcome, commits pushed, human comments left for the user, final CI state,
and PR state.
