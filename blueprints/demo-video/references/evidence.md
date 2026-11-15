# Evidence

## Claim table

Every number, date, name and status on screen has a row before the scene is built:

| id | on screen | value | source path + locator | exact quote | class | qualifier |
|---|---|---|---|---|---|---|
| C1 | $3,000 short | 30,000 − 27,000 | `data/sample/statement-p1.txt` | "27,000.00" | recorded test answer | sample data |

- Keep units, denominators, time windows and cost bases with the number: per question, per run or per
  month; a token-price estimate or an invoice.
- A quote proves the text exists, not that the headline follows from it. The reviewer checks the
  plain-language takeaway too.
- Generate the on-screen text inventory from the built composition, including text inside screenshots,
  and check that, not the script.

## Evidence classes and labels

| Class | Rail text pattern |
|---|---|
| Shipped UI in an environment | `Staging · captured 15 Nov 09:10 UTC` / `Production` |
| Real UI on a local build or demo page | `Local build` / `Concept demo` |
| Saved model output replayed | `Recorded answer` (+ `replayed` when timing is the page's, not the model's) |
| Editorial graphic quoting a source | `Exact lines from sample source pages` |
| Lab or eval result | `Lab test · 10 sample cases · AI-scored, human check pending` |

The rail sits outside the camera so push-ins never crop it. Change it at chapter boundaries and whenever
the evidence class changes within a chapter. A replay, a concept screen and live UI each keep their own label.

## Recurring traps

- Merged ≠ in a release ≠ deployed to staging ≠ in production. Check the deployment before saying it.
- Lab success ≠ quality on real work. Two models from one family agreeing ≠ correctness. A partial smoke
  test ≠ end to end.
- An animated counter captured mid-count shows a wrong number. Capture the settled state or use a fake clock.
- A synthetic mockup, a recorded real-model answer and a live screenshot look alike. Label each.
- Sample data should look plausible and still be labelled sample data.
- No client, customer or staff names unless approved. Keep zooms clear of the signed-in user.

## Fact-check

Films with numbers: an independent review of the on-screen text inventory and the claim table. A reviewer
from a different model family, or a person, catches more than a second pass by the same model. Delegating
to another agent or a paid model needs explicit authority; set a round limit (three is usually enough) and
a spend ceiling first. Keep each round's file and your response. Without an independent reviewer, run your
own pass and report the independent check as pending. Done videos: check the issue or PR title and number
against the tracker.
