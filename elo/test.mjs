import { test } from "node:test";
import assert from "node:assert/strict";
import { ratingChange } from "./elo.js";

const TOLERANCE = 0.1;

function assertNear(actual, expected, message) {
  assert.ok(
    Math.abs(actual - expected) <= TOLERANCE,
    message ?? `got ${actual}, expected ${expected} (±${TOLERANCE})`,
  );
}

const casesK40 = [
  [1750, 1682, 1, 16.2],
  [1750, 2043, 0, -6.1],
  [1750, 1766, 0, -19.1],
  [1750, 1991, 0.5, 12],
  [1750, 1751, 0, -19.9],
  [1750, 1802, 1, 22.9],
  [1750, 2214, 0, -2.1],
  [1750, 1403, 1, 4.5],
  [1750, 1574, 1, 10.8],
  [1991, 0, 1, 0],
  [1991, 2036, 0, -17.5],
  [1991, 2043, 0.5, 2.9],
  [1991, 1304, 1, 0.3],
  [1991, 1830, 0.5, -8.5],
  [1991, 1750, 0.5, -12],
  [1991, 1688, 1, 5.8],
  [1991, 2135, 0, -12.3],
  [1991, 1423, 1, 0.9],
];

const casesK10 = [
  [2600, 2632, 0.5, 0.5],
  [2600, 2556, 0.5, -0.6],
  [2600, 2590, 0.5, -0.1],
];

for (const [player, opponent, score, expected] of casesK40) {
  test(`K=40: ${player} vs ${opponent}, score ${score} → ${expected}`, () => {
    assertNear(ratingChange(player, opponent, score, 40), expected);
  });
}

for (const [player, opponent, score, expected] of casesK10) {
  test(`K=10: ${player} vs ${opponent}, score ${score} → ${expected}`, () => {
    assertNear(ratingChange(player, opponent, score, 10), expected);
  });
}
