# Reviewer policy

Read when the watcher returns `unresolved_comments`. It calibrates by bot, so rewrite the two examples to match the bots your repository really uses and revise them as you learn.

## Signal hierarchy

Review bots differ in signal. Calibrate per login and write it down.

- **Higher-signal bot** (reads diff context, flags real deviations from convention). Default to applying a verified suggestion. Decline only when it conflicts with explicit direction, repository conventions or an existing pattern it did not see. Read every file a multi-file suggestion touches.
- **Lower-signal bot** (wide, theoretical, sometimes wrong about files it did not read). Start sceptical. Prefer the repository's existing pattern unless it found a concrete correctness, contract or security flaw.

Verify the actual file and its surroundings before acting on either.

## Decline

- A concern with no path that fires in this PR ("could potentially", "consider whether").
- Defensive validation for states that cannot occur.
- Speculative abstraction or "future flexibility".
- Anything that makes the code more complicated without changing the outcome.

Apply small, mechanical, clearly correct fixes: a typo, a demonstrated off-by-one, a boundary check that matches its neighbours. Reply with the commit.

## Nits

Decline style, wording and naming nits by default. Apply one only when it is tiny and obviously correct, or when it clearly helps a human reviewer. A useful decline:

> Not applying: this is a nit, does not change behaviour, and the current form matches the surrounding code.

Reviewer attention is the scarce resource, not the bot's.

## Bigger refactors

Stop and ask before applying a suggestion that spans files beyond the commented one, adds an abstraction, renames a public surface, restructures logic enough to change the diff's shape, or widens the PR's scope. Leave the thread untouched while you wait. Pre-approval for this PR overrides the ask. Single-line fixes, local renames, typos and boundary checks are not bigger refactors.

## Two bots disagree

Take the higher-signal bot by default, but check the other's point once before resolving it; occasionally it caught a real constraint. If both are right about different things, apply both, and explain the choice on each thread.

## Humans

A person's comment carries more weight and more risk. The bar to act is higher.

- Act, reply and resolve only when the ask is trivial, mechanical and has exactly one correct change.
- Otherwise leave the thread alone, tell the user, and carry `--ignore-comment ID` on the next launch.
- A reply the user has vetted may carry a footer such as `🤖 (Checked by <name>)`. It is still drafted text: verify the file. Silence, moving on or merging is not approval.

## Reply templates

End each reply with the marker footer on its own line.

- Applied: `Applied in <sha>.` Cite only a commit you have verified contains the change.
- Partial: `Partially applied: kept X because Y. See <sha>.`
- Declined, pattern: `Not applying: <file>:<line> uses the same idiom; keeping it for consistency.`
- Declined, theoretical: `Not applying: no path in this PR reaches that state. Happy to revisit with a concrete repro.`
- Declined, over-correction: `Not applying: it adds complexity (X) without solving a problem this diff reaches.`

Then resolve the thread with the `thread_id` from the JSON.
