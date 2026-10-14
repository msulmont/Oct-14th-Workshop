# Research starter

A small research database you build with Claude Code and keep growing. You pick a
topic and a public document. Claude reads it and writes down the numbers that
answer your questions, each with the exact sentence it came from. A plain Python
script (`verify.py`, no AI) checks every number against the saved original and
marks it **verified** or **held**.

The idea: Claude does the reading, and something predictable decides what counts.

## What's in here

| File | What it is |
|---|---|
| `CLAUDE.md` | The rules Claude follows in this project |
| `questions.md` | Your topic and questions |
| `sources/` | Your original documents, never edited |
| `captures/` | The text pulled out of each original |
| `sources.json` | Each source's title, address and fingerprint |
| `claims.json` | The facts: value, unit, period and exact quote |
| `verify.py` | The checker |
| `REPORT.md` | Verified or held for every claim, with the reason |

## Get started

**1. Pick a topic and a source.** Choose a public web page or PDF with numbers
written in sentences: a planning staff report, a city housing element, a
construction cost report, the AIA billings index, a pension board report, a
Census or BLS release. Copy its address. You don't need to download anything.

**2. Open the starter in Claude Code.**
- *claude.ai/code:* on GitHub, click **Use this template → Create a new
  repository**, then pick your new repository at claude.ai/code. To let Claude
  fetch your source, set the environment's network access to **Full**.
- *Claude Code on your computer:* ask Claude Code to clone
  `https://github.com/lsarta/research-starter` into a new folder and open it.

**3. Build it, one prompt at a time.** Fill in the brackets.

```
Read CLAUDE.md and README.md and explain how this research system works. Then write questions.md for me. My topic is [topic] and I want to know [your questions].
```

```
Add this source to the system following CLAUDE.md: [address]. It's [title]. Tell me if any pages or tables didn't come through cleanly.
```

```
Add up to eight numbers from this source that answer the questions in questions.md to claims.json, following CLAUDE.md. Then run the checker and explain anything that was held.
```

```
Run a tamper test: change one word in my source's text, run the checker and show me what happened. Then put the file back and run it again.
```

```
Build index.html, a one-page view of my verified claims grouped by question. Show each number with its quote and source, and list held claims separately with the reason.
```

## Keep growing it

- **Add a second source** on the same topic and ask Claude to compare them.
- **Add a check.** For example, hold any claim whose quote mentions more than
  one month or year, so a person confirms it's the right period.
- **Chart it.** A chart of verified values over time or across places.
- **Keep it current.** Set up a Claude Code routine at claude.ai/code/routines
  that checks for new releases every week and adds them on a separate branch for
  you to review.

Keep anything private in a private repository.
