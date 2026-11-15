# Extensions

Build these once the basic loop works. None is bundled; each needs its own tests before you trust it.

| Extension | What it adds |
| --- | --- |
| **The watcher itself** | A script to the [watcher contract](watcher-contract.md). Standard library plus the GitHub CLI is enough. Keep the decision logic pure, separate from the polling, so recorded responses can test every exit. |
| **Richer bot "still working" detection** | The contract only needs a conservative signal. This adds per-bot signals that a review or coding agent has not finished: a task API where the bot has one, otherwise its timeline events with a recency guard for starts that never finished. This is what makes `all_green` trustworthy. |
| **Approval-delta scoring** | The contract treats an unscored delta as risky. This scores the change since the last approval (lines, files, risky paths such as auth, schemas, migrations, payments, public API) and reports `risky` with reasons, so a low-risk delta merges and a risky one asks. |
| **Pre-publish review receipts** | For the draft gate: run a local review CLI on the head, store a receipt keyed by head SHA, and reuse it instead of re-running on an unchanged head. Respect the tool's rate limits and report when it is unavailable rather than passing. |
| **Re-request helper** | List reviewers whose latest review predates the head and offer the exact re-request command. With merge authority, send it once the PR is genuinely ready. |
| **Notifier** | One call for a desktop banner and an optional phone push, with priority levels mapped to the four notification cases. Keep credentials in the OS keychain, not in the skill. |
| **Celebration** | A small on-screen moment after a merge you performed. Rare by design: merges only, never on "ready". |
| **Close-out handoff** | Hand a merged PR to a separate finish-work step: status note, issue state, and teardown of the branch's own worktree and containers, under that step's own authority. |
| **Durable watching** | A scheduled job that launches the watcher once with `--once` and acts on the result, for PRs that outlive the session. Hold merges and pushes when no one is there to answer a question. |
| **Repository profile** | A small per-repository file: the bot logins and how much to trust each, required check names, merge method, commit trailer rule, and whether the draft gate applies. The loop reads it instead of guessing. |
