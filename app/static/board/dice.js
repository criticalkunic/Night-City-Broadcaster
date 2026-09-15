const DIE_ORDER = ["d4", "d6", "d8", "d10", "d12", "d20"];
const DIE_SIDES = { d4: 4, d6: 6, d8: 8, d10: 10, d12: 12, d20: 20 };
/* Die silhouettes as drawn in the Cyberpunk TCG rulebook (100x100 viewBox):
 * d4 narrow shield, d6 square, d8 tall hexagon, d10 diamond, d12 decagon,
 * d20 hexagon with a faint ghost hexagon behind it. */
const DIE_POLYGONS = {
  d4: "50,4 80,18 80,82 50,96 20,82 20,18",
  d6: "14,14 86,14 86,86 14,86",
  d8: "50,4 84,24 84,76 50,96 16,76 16,24",
  d10: "50,4 90,50 50,96 10,50",
  d12: "50.0,6.0 75.9,14.4 91.8,36.4 91.8,63.6 75.9,85.6 50.0,94.0 24.1,85.6 8.2,63.6 8.2,36.4 24.1,14.4",
  d20: "50,6 88,28 88,72 50,94 12,72 12,28",
};
const DIE_GHOSTS = { d20: "28,10 72,10 94,50 72,90 28,90 6,50" };

function dieShapeSVG(type) {
  const ghost = DIE_GHOSTS[type]
    ? `<polygon class="ghost" points="${DIE_GHOSTS[type]}"></polygon>` : "";
  return `<svg class="die-shape" viewBox="0 0 100 100" aria-hidden="true">${ghost}` +
    `<polygon class="body" points="${DIE_POLYGONS[type]}"></polygon></svg>`;
}
