const TOURNAMENT_URL = new URL("data/tournament.json", document.baseURI).href;
const RATINGS_URL = new URL("data/ratings.json", document.baseURI).href;

const state = {
  data: null,
  ratings: null,
  filter: "all",
  search: "",
  sort: "rank",
};

const summaryEl = document.getElementById("summary");
const teamGridEl = document.getElementById("teamGrid");
const emptyStateEl = document.getElementById("emptyState");
const searchInput = document.getElementById("searchInput");
const sortSelect = document.getElementById("sortSelect");
const fetchedAtEl = document.getElementById("fetchedAt");
const teamModal = document.getElementById("teamModal");
const modalBody = document.getElementById("modalBody");

document.querySelector(".modal-close").addEventListener("click", () => teamModal.close());
teamModal.addEventListener("click", (event) => {
  if (event.target === teamModal) teamModal.close();
});

document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    document.querySelectorAll(".chip").forEach((node) => node.classList.remove("chip-active"));
    chip.classList.add("chip-active");
    state.filter = chip.dataset.filter;
    render();
  });
});

searchInput.addEventListener("input", () => {
  state.search = searchInput.value.trim().toLowerCase();
  render();
});

sortSelect.addEventListener("change", () => {
  state.sort = sortSelect.value;
  render();
});

document.getElementById("refreshBtn")?.addEventListener("click", () => {
  window.location.reload();
});

function playerStorageKey(player) {
  if (player.player_id != null && String(player.player_id) !== "") {
    return String(player.player_id);
  }
  return `name:${player.name}`;
}

function applyRatingsToTeam(team, ratings) {
  const teamStats = ratings.team_stats?.[team.id];
  if (teamStats) {
    Object.assign(team, teamStats);
  }
  for (const player of team.players) {
    const entry = ratings.players?.[playerStorageKey(player)];
    if (!entry) continue;
    if (entry.knsb_relatienummer != null) player.knsb_relatienummer = entry.knsb_relatienummer;
    if (entry.knsb_classic != null) player.knsb_classic = entry.knsb_classic;
    if (entry.knsb_rapid != null) player.knsb_rapid = entry.knsb_rapid;
    if (entry.ratingviewer_url) player.ratingviewer_url = entry.ratingviewer_url;
    if (entry.resolved_name) player.resolved_name = entry.resolved_name;
  }
}

function mergeRatings(tournament, ratings) {
  if (!ratings) return tournament;

  if (ratings.summary) {
    tournament.summary = { ...tournament.summary, ...ratings.summary };
  }

  for (const semifinal of tournament.semifinals) {
    const semiSummary = ratings.semifinal_summaries?.[semifinal.id];
    if (semiSummary) {
      semifinal.summary = { ...semifinal.summary, ...semiSummary };
    }
    for (const team of semifinal.teams) {
      applyRatingsToTeam(team, ratings);
    }
  }

  for (const team of tournament.finalists) {
    applyRatingsToTeam(team, ratings);
  }

  if (ratings.fetched_at) {
    tournament.ratings_fetched_at = ratings.fetched_at;
  }

  return tournament;
}

function formatPlayerName(player) {
  let name = player.name;
  if (player.resolved_name && player.name !== player.resolved_name) {
    name = `${player.name} (${player.resolved_name})`;
  }
  const rating = formatPlayerRating(player);
  if (rating !== "—") {
    name = `${name} (${rating})`;
  }
  return name;
}

async function loadData() {
  const [tournamentResponse, ratingsResponse] = await Promise.all([
    fetch(TOURNAMENT_URL),
    fetch(RATINGS_URL),
  ]);

  if (!tournamentResponse.ok) {
    throw new Error("Kon tournament.json niet laden. Voer eerst scripts/fetch_data.py uit.");
  }

  const tournament = await tournamentResponse.json();
  state.ratings = ratingsResponse.ok ? await ratingsResponse.json() : null;
  state.data = mergeRatings(tournament, state.ratings);
  playerLookup = null;

  const fetchedParts = [`Toernooi: ${formatDate(state.data.fetched_at)}`];
  if (state.data.ratings_fetched_at) {
    fetchedParts.push(`Ratings: ${formatDate(state.data.ratings_fetched_at)}`);
  }
  fetchedAtEl.textContent = `Laatst opgehaald — ${fetchedParts.join(" · ")}`;

  renderSummary();
  render();
}

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("nl-NL");
}

function formatRating(value) {
  return value == null ? "—" : String(Math.round(value));
}

function playerBestRating(player) {
  const ratings = [player.knsb_classic, player.knsb_rapid, player.rating].filter(
    (value) => value != null
  );
  return ratings.length ? Math.max(...ratings) : null;
}

function teamBestRatings(team) {
  const ratings = team.players.map(playerBestRating).filter((value) => value != null);
  if (!ratings.length) {
    return { average: null, top: null };
  }
  const total = ratings.reduce((sum, value) => sum + value, 0);
  return {
    average: Math.round(total / ratings.length),
    top: Math.max(...ratings),
  };
}

function summaryBestRating(summaryTeams) {
  const ratings = summaryTeams
    .flatMap((team) => team.players.map(playerBestRating))
    .filter((value) => value != null);
  if (!ratings.length) {
    return null;
  }
  return Math.round(ratings.reduce((sum, value) => sum + value, 0) / ratings.length);
}

function formatPlayerRating(player) {
  const best = playerBestRating(player);
  return best == null ? "—" : formatRating(best);
}

function formatPlayerRatingDetail(player) {
  if (player.knsb_classic != null || player.knsb_rapid != null) {
    if (player.knsb_classic != null) {
      return `${formatRating(player.knsb_classic)}/${formatRating(player.knsb_rapid)}`;
    }
    return formatRating(player.knsb_rapid);
  }
  if (player.rating != null) {
    return formatRating(player.rating);
  }
  return "—";
}

function playersByRating(team) {
  return team.players
    .map((player, index) => ({ player, index }))
    .sort((a, b) => (playerBestRating(b.player) || 0) - (playerBestRating(a.player) || 0));
}

function formatScore(team) {
  if (team.match_points != null) {
  const bp = team.board_points != null ? ` / ${team.board_points} BP` : "";
    return `${team.match_points} MP${bp}`;
  }
  if (team.score != null) {
    return `${team.score} pt`;
  }
  return "—";
}

function formatPlayerRecord(player) {
  const games = player.games?.length ?? 0;
  if (player.points == null && games === 0) {
    return "—";
  }
  const points = player.points == null ? "0" : String(player.points);
  return `${points}/${games}`;
}

function gamePoints(game) {
  if (game.points != null) {
    return game.points;
  }
  if (game.result === "1-0") {
    return 1;
  }
  if (game.result === "0-1") {
    return 0;
  }
  return 0.5;
}

function formatScoreToken(value) {
  const rounded = Math.round(value * 2) / 2;
  const whole = Math.floor(rounded);
  const hasHalf = Math.abs(rounded - whole - 0.5) < 1e-9;
  if (whole === 0 && hasHalf) {
    return "½";
  }
  if (hasHalf) {
    return `${whole}½`;
  }
  return String(whole);
}

function formatBoardScore(game) {
  const isWhite = game.color === "white";
  const our = gamePoints(game);
  const opp = our === 1 ? 0 : our === 0 ? 1 : 0.5;
  const whiteScore = isWhite ? our : opp;
  const blackScore = isWhite ? opp : our;
  return `${formatScoreToken(whiteScore)}:${formatScoreToken(blackScore)}`;
}

function computeMatchPoints(match) {
  let our = 0;
  let opp = 0;
  for (const { game } of match.boards) {
    const points = gamePoints(game);
    our += points;
    opp += points === 1 ? 0 : points === 0 ? 1 : 0.5;
  }
  return { our, opp };
}

function matchScoreClass(match) {
  const { our, opp } = computeMatchPoints(match);
  if (our > opp) return "game-result-win";
  if (our < opp) return "game-result-loss";
  return "game-result-draw";
}

function formatMatchScore(match) {
  const { our, opp } = computeMatchPoints(match);
  return `<span class="game-result ${matchScoreClass(match)}">${formatScoreToken(our)}:${formatScoreToken(opp)}</span>`;
}

function formatBoardPlayers(game, player) {
  const isWhite = game.color === "white";
  const white = isWhite ? player.name : game.opponent;
  const black = isWhite ? game.opponent : player.name;
  return `${formatOpponentName(white)} - ${formatOpponentName(black)}`;
}

function collectTeamMatches(team) {
  const matchMap = new Map();

  for (const player of team.players) {
    for (const game of player.games || []) {
      const round = game.round ?? 0;
      const opponentTeam = game.opponent_team || "—";
      const key = `${round}\0${opponentTeam}`;

      if (!matchMap.has(key)) {
        matchMap.set(key, { round: game.round, opponentTeam, boards: [] });
      }

      matchMap.get(key).boards.push({ game, player });
    }
  }

  return Array.from(matchMap.values())
    .sort(
      (a, b) =>
        (a.round ?? 0) - (b.round ?? 0) ||
        a.opponentTeam.localeCompare(b.opponentTeam, "nl")
    )
    .map((match) => ({
      ...match,
      boards: match.boards.sort((a, b) => (a.game.board ?? 0) - (b.game.board ?? 0)),
    }));
}

function renderTeamGames(team) {
  const matches = collectTeamMatches(team);
  if (!matches.length) {
    return `<p class="muted games-empty">Geen teampartijen gevonden.</p>`;
  }

  const rows = matches.flatMap((match) => {
    const boardCount = match.boards.length;
    return match.boards.map(({ game, player }, index) => {
      const roundCell =
        index === 0
          ? `<td class="num match-meta" rowspan="${boardCount}">${match.round ?? "—"}</td>`
          : "";
      const opponentCell =
        index === 0
          ? `<td class="match-meta" rowspan="${boardCount}">${match.opponentTeam}</td>`
          : "";
      const scoreCell =
        index === 0
          ? `<td class="num match-meta" rowspan="${boardCount}">${formatMatchScore(match)}</td>`
          : "";
      return `
        <tr>
          ${roundCell}
          ${opponentCell}
          ${scoreCell}
          <td>${formatBoardPlayers(game, player)}</td>
          <td class="num">${formatBoardScoreResult(game)}</td>
        </tr>
      `;
    });
  });

  return `
    <h3 class="modal-section-title">Wedstrijden</h3>
    <table class="games-table team-matches-table">
      <thead>
        <tr>
          <th>Ronde</th>
          <th>Tegen</th>
          <th>Stand</th>
          <th>Partij</th>
          <th>Uitslag</th>
        </tr>
      </thead>
      <tbody>
        ${rows.join("")}
      </tbody>
    </table>
  `;
}

function semifinalLabel(team) {
  const id = team.id.split("-")[0];
  return {
    arnhem: "Arnhem",
    kruiningen: "Kruiningen",
    almere: "Almere",
  }[id] || id;
}

function allTeams() {
  return state.data.finalists.map((team) => {
    const semifinal_id = team.id.split("-")[0];
    const semifinal = state.data.semifinals.find((entry) => entry.id === semifinal_id);
    return {
      ...team,
      semifinal_id,
      semifinal_name: semifinal?.name ?? semifinal_id,
    };
  });
}

let playerLookup = null;

function getPlayerLookup() {
  if (!playerLookup) {
    playerLookup = new Map();
    for (const semifinal of state.data.semifinals) {
      for (const team of semifinal.teams) {
        const teamWithMeta = {
          ...team,
          semifinal_id: semifinal.id,
          semifinal_name: semifinal.name,
        };
        for (const player of team.players) {
          playerLookup.set(player.name.toLowerCase(), { team: teamWithMeta, player });
        }
      }
    }
  }
  return playerLookup;
}

function findPlayerByName(name) {
  return getPlayerLookup().get(name.toLowerCase()) ?? null;
}

function filteredTeams() {
  let teams = allTeams();

  if (state.filter !== "all") {
    teams = teams.filter((team) => team.semifinal_id === state.filter);
  }

  if (state.search) {
    teams = teams.filter((team) => {
      const haystack = [
        team.name,
        team.semifinal_name,
        ...team.players.flatMap((player) => [player.name, player.resolved_name].filter(Boolean)),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(state.search);
    });
  }

  teams.sort((a, b) => {
    const aRatings = teamBestRatings(a);
    const bRatings = teamBestRatings(b);
    switch (state.sort) {
      case "avg_best":
        return (bRatings.average || 0) - (aRatings.average || 0);
      case "top_best":
        return (bRatings.top || 0) - (aRatings.top || 0);
      case "name":
        return a.name.localeCompare(b.name, "nl");
      case "rank":
      default:
        if (a.semifinal_id !== b.semifinal_id) {
          return a.semifinal_id.localeCompare(b.semifinal_id);
        }
        return a.rank - b.rank;
    }
  });

  return teams;
}

function renderSummary() {
  const { summary } = state.data;
  const teams = allTeams();
  const cards = [
    ["Finalisten", summary.finalist_teams],
    ["Spelers", summary.player_count],
    ["Gem. rating", formatRating(summaryBestRating(teams))],
  ];

  summaryEl.innerHTML = cards
    .map(
      ([label, value]) => `
        <article class="stat-card">
          <span class="muted">${label}</span>
          <strong>${value}</strong>
        </article>
      `
    )
    .join("");
}

function renderTeamCard(team) {
  const { average, top } = teamBestRatings(team);
  return `
    <article class="team-card" data-team-id="${team.id}">
      <div class="team-card-header">
        <div>
          <h2 class="team-name">${team.name}</h2>
          <p class="team-rank">#${team.rank} in ${semifinalLabel(team)}</p>
        </div>
      </div>
      <div class="team-metrics">
        <div class="metric">
          <span>Score</span>
          <strong>${formatScore(team)}</strong>
        </div>
        <div class="metric">
          <span>Gem. rating</span>
          <strong>${formatRating(average)}</strong>
        </div>
        <div class="metric">
          <span>Top rating</span>
          <strong>${formatRating(top)}</strong>
        </div>
      </div>
      <ul class="player-preview">
        ${playersByRating(team)
          .map(
            ({ player, index }) => `
              <li>
                <button type="button" class="link-button player-preview-link" data-player-index="${index}">
                  ${formatPlayerName(player)}
                </button>
              </li>
            `
          )
          .join("")}
      </ul>
    </article>
  `;
}

function gameResultClass(game) {
  if (game.points === 1 || game.result === "1-0") return "game-result-win";
  if (game.points === 0 || game.result === "0-1") return "game-result-loss";
  return "game-result-draw";
}

function formatGameResult(game) {
  const label = game.result ?? "—";
  return `<span class="game-result ${gameResultClass(game)}">${label}</span>`;
}

function formatBoardScoreResult(game) {
  return `<span class="game-result ${gameResultClass(game)}">${formatBoardScore(game)}</span>`;
}

function formatGameColor(game) {
  const isWhite = game.color === "white";
  const label = isWhite ? "Wit" : "Zwart";
  const boxClass = isWhite ? "color-box-white" : "color-box-black";
  return `<span class="color-box ${boxClass}" title="${label}" aria-label="${label}"></span>`;
}

function playerKnsbLink(player) {
  if (player.ratingviewer_url) {
    return { href: player.ratingviewer_url, label: "KNSB" };
  }
  if (player.player_id) {
    return {
      href: `https://knsb.netstand.nl/players/view/${player.player_id}`,
      label: "KNSB",
    };
  }
  return null;
}

function renderPlayerLinks(player) {
  const knsb = playerKnsbLink(player);
  if (!knsb) return "";
  return `<p class="player-links"><a href="${knsb.href}" target="_blank" rel="noopener">${knsb.label}</a></p>`;
}

function formatOpponentName(opponent) {
  const match = findPlayerByName(opponent);
  if (!match) {
    return opponent;
  }
  const escaped = opponent.replace(/"/g, "&quot;");
  return `<button type="button" class="link-button opponent-link" data-player-name="${escaped}">${formatPlayerName(match.player)}</button>`;
}

function renderPlayerGames(player) {
  if (!player.games?.length) {
    return `<p class="muted games-empty">Geen partijen gevonden.</p>`;
  }
  return `
    <table class="games-table">
      <thead>
        <tr>
          <th>Ronde</th>
          <th>Bord</th>
          <th>Tegenstander</th>
          <th>Team</th>
          <th>Kleur</th>
          <th>Uitslag</th>
        </tr>
      </thead>
      <tbody>
        ${player.games
          .map(
            (game) => `
              <tr>
                <td class="num">${game.round ?? "—"}</td>
                <td class="num">${game.board ?? "—"}</td>
                <td>${formatOpponentName(game.opponent)}</td>
                <td>${game.opponent_team}</td>
                <td class="color-cell">${formatGameColor(game)}</td>
                <td class="num">${formatGameResult(game)}</td>
              </tr>
            `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function wireOpponentLinks() {
  modalBody.querySelectorAll(".opponent-link").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.stopPropagation();
      const match = findPlayerByName(link.dataset.playerName);
      if (match) openPlayerModal(match.team, match.player);
    });
  });
}

function openPlayerModal(team, player) {
  modalBody.innerHTML = `
    <h2>${formatPlayerName(player)}</h2>
    <p class="muted">${team.name} · #${team.rank} in ${semifinalLabel(team)}</p>
    <p>
      <strong>Rating:</strong> ${formatPlayerRatingDetail(player)}
      · <strong>Score:</strong> ${formatPlayerRecord(player)}
    </p>
    ${renderPlayerLinks(player)}
    ${renderPlayerGames(player)}
    <p><button type="button" class="btn btn-secondary" id="backToTeamBtn">Terug naar team</button></p>
  `;
  document.getElementById("backToTeamBtn").addEventListener("click", () => openTeamModal(team));
  wireOpponentLinks();
  teamModal.showModal();
}

function openTeamModal(team) {
  modalBody.innerHTML = `
    <h2>${team.name}</h2>
    <p class="muted">#${team.rank} in ${semifinalLabel(team)}</p>
    <p>
      <strong>Score:</strong> ${formatScore(team)}
      ${team.team_rating != null ? ` · <strong>Teamrating:</strong> ${team.team_rating}` : ""}
    </p>
    <p>
      <a href="${team.source_url}" target="_blank" rel="noopener">Bronpagina</a>
    </p>
    <table class="players-table">
      <thead>
        <tr>
          <th>Speler</th>
          <th>Rating</th>
          <th>Score</th>
        </tr>
      </thead>
      <tbody>
        ${playersByRating(team)
          .map(
            ({ player, index }) => `
              <tr class="player-row" data-player-index="${index}">
                <td>
                  <button type="button" class="link-button player-link">${formatPlayerName(player)}</button>
                  ${
                    player.ratingviewer_url
                      ? `<a href="${player.ratingviewer_url}" target="_blank" rel="noopener" class="ratingviewer-link" title="RatingViewer">↗</a>`
                      : ""
                  }
                </td>
                <td class="num rating-pair">${formatPlayerRating(player)}</td>
                <td class="num">${formatPlayerRecord(player)}</td>
              </tr>
            `
          )
          .join("")}
      </tbody>
    </table>
    ${renderTeamGames(team)}
    <p class="muted modal-hint">Klik op een spelernaam om partijen te bekijken.</p>
  `;

  modalBody.querySelectorAll(".player-link").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.stopPropagation();
      const row = link.closest(".player-row");
      const player = team.players[Number(row.dataset.playerIndex)];
      openPlayerModal(team, player);
    });
  });

  modalBody.querySelectorAll(".ratingviewer-link").forEach((link) => {
    link.addEventListener("click", (event) => event.stopPropagation());
  });

  wireOpponentLinks();
  teamModal.showModal();
}

function render() {
  const teams = filteredTeams();
  teamGridEl.innerHTML = teams.map(renderTeamCard).join("");
  emptyStateEl.classList.toggle("hidden", teams.length > 0);

  teamGridEl.querySelectorAll(".team-card").forEach((card) => {
    const team = teams.find((entry) => entry.id === card.dataset.teamId);
    if (!team) return;

    card.addEventListener("click", () => openTeamModal(team));

    card.querySelectorAll(".player-preview-link").forEach((link) => {
      link.addEventListener("click", (event) => {
        event.stopPropagation();
        const player = team.players[Number(link.dataset.playerIndex)];
        if (player) openPlayerModal(team, player);
      });
    });
  });
}

loadData().catch((error) => {
  teamGridEl.innerHTML = `<p class="empty-state">${error.message}</p>`;
});
