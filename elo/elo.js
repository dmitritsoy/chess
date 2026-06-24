const KNSB_SIGMA = 2000 / 7;

function normCdf(x, mu = 0, sigma = KNSB_SIGMA) {
  const z = (x - mu) / (sigma * Math.SQRT2);
  return 0.5 * (1 + erf(z));
}

function erf(x) {
  const sign = x < 0 ? -1 : 1;
  const ax = Math.abs(x);
  const a1 = 0.254829592;
  const a2 = -0.284496736;
  const a3 = 1.421413741;
  const a4 = -1.453152027;
  const a5 = 1.061405429;
  const p = 0.3275911;
  const t = 1 / (1 + p * ax);
  const y =
    1 -
    (((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t * Math.exp(-ax * ax));
  return sign * y;
}

function expectedScore(playerRating, opponentRating) {
  return normCdf(playerRating - opponentRating);
}

function ratingChange(playerRating, opponentRating, score, kFactor = 40) {
  if (!Number.isFinite(playerRating) || !Number.isFinite(opponentRating)) {
    return null;
  }
  if (opponentRating <= 0) {
    return 0;
  }

  const we = expectedScore(playerRating, opponentRating);
  return Math.round(kFactor * (score - we) * 10) / 10;
}

function allOutcomes(playerRating, opponentRating, kFactor = 40) {
  return {
    win: ratingChange(playerRating, opponentRating, 1, kFactor),
    draw: ratingChange(playerRating, opponentRating, 0.5, kFactor),
    loss: ratingChange(playerRating, opponentRating, 0, kFactor),
    expectedScore: expectedScore(playerRating, opponentRating),
  };
}

export { ratingChange, expectedScore, allOutcomes };
