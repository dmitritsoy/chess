import { allOutcomes } from "./elo.js";

const STORAGE_KEY = "elo-calculator";
const DEFAULT_K = 40;

const playerInput = document.getElementById("player-rating");
const opponentInput = document.getElementById("opponent-rating");
const kInput = document.getElementById("k-factor");
const swapBtn = document.getElementById("swap-btn");
const advancedToggle = document.getElementById("advanced-toggle");
const advancedSection = document.getElementById("advanced");
const noticeEl = document.getElementById("notice");
const resultsEl = document.getElementById("results");
const expectedPctEl = document.getElementById("expected-pct");
const outcomesEl = document.getElementById("outcomes");

function readStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    return data && typeof data === "object" ? data : null;
  } catch {
    return null;
  }
}

function writeStored() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        playerRating: playerInput.value,
        opponentRating: opponentInput.value,
        kFactor: kInput.value,
      }),
    );
  } catch {
    // ignore
  }
}

function formatDelta(value) {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(1)}`;
}

function formatRating(value) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function outcomeCard(title, delta, newRating) {
  const article = document.createElement("article");
  article.className = "outcome";
  if (delta > 0) article.classList.add("gain");
  if (delta < 0) article.classList.add("loss");

  article.innerHTML = `
    <h2>${title}</h2>
    <p class="delta">${formatDelta(delta)}</p>
    <p class="new-rating">→ ${formatRating(newRating)}</p>
  `;
  return article;
}

function update() {
  writeStored();

  const player = Number(playerInput.value);
  const opponent = Number(opponentInput.value);
  const k = Number(kInput.value) || DEFAULT_K;

  if (!Number.isFinite(player) || !Number.isFinite(opponent) || k <= 0) {
    noticeEl.hidden = true;
    resultsEl.hidden = true;
    return;
  }

  if (opponent <= 0) {
    noticeEl.hidden = false;
    resultsEl.hidden = true;
    return;
  }

  noticeEl.hidden = true;
  resultsEl.hidden = false;

  const outcomes = allOutcomes(player, opponent, k);
  const expectedPct = Math.round(outcomes.expectedScore * 1000) / 10;

  expectedPctEl.textContent = `${expectedPct}%`;
  outcomesEl.replaceChildren(
    outcomeCard("Win", outcomes.win, player + outcomes.win),
    outcomeCard("Draw", outcomes.draw, player + outcomes.draw),
    outcomeCard("Loss", outcomes.loss, player + outcomes.loss),
  );
}

function load() {
  const stored = readStored();
  if (stored?.playerRating != null) playerInput.value = stored.playerRating;
  if (stored?.opponentRating != null) opponentInput.value = stored.opponentRating;
  if (stored?.kFactor != null) kInput.value = stored.kFactor;
}

swapBtn.addEventListener("click", () => {
  const tmp = playerInput.value;
  playerInput.value = opponentInput.value;
  opponentInput.value = tmp;
  update();
});

advancedToggle.addEventListener("click", () => {
  const willOpen = advancedSection.hidden;
  advancedSection.hidden = !willOpen;
  advancedToggle.setAttribute("aria-expanded", String(willOpen));
  advancedToggle.textContent = willOpen ? "Hide details" : "How it works";
});

for (const input of [playerInput, opponentInput, kInput]) {
  input.addEventListener("input", update);
}

load();
update();
