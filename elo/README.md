# ELO Calculator

A small KNSB rating calculator. Enter your rating and your opponent's rating to see how many points you gain or lose for a win, draw, or loss.

## Files

- `index.html` — page
- `style.css` — styles
- `elo.js` — KNSB rating calculation
- `app.js` — UI, localStorage, swap button
- `test.mjs` — test cases (run with `node --test test.mjs`)

## Run locally

Browsers block JavaScript loaded from `file://` URLs, so open the app through a local web server.

From this folder, run:

```bash
python3 -m http.server 8080
```

Then open in your browser:

**http://localhost:8080**

Press `Ctrl+C` in the terminal to stop the server.

On Windows, if `python3` is not available, try:

```bash
python -m http.server 8080
```

## Tests

```bash
node --test test.mjs
```
