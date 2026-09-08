const fs = require("fs");

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

const venueData = JSON.parse(fs.readFileSync("data/venues.json", "utf8"));
const venueListSource = fs.readFileSync("venues.js", "utf8");
const detailSource = fs.readFileSync("venue-detail.js", "utf8");
const detailHtml = fs.readFileSync("venue.html", "utf8");

expect(Array.isArray(venueData.venues) && venueData.venues.length > 0, "data/venues.json must contain venues");

const ids = new Set();
for (const venue of venueData.venues) {
  expect(typeof venue.id === "string" && venue.id.trim(), `venue id is missing: ${venue.name || "(unknown)"}`);
  expect(!ids.has(venue.id), `duplicate venue id: ${venue.id}`);
  ids.add(venue.id);
}

expect(ids.has("tokyo-garden-theater"), "Tokyo Garden Theater stable venue id is missing");

expect(
  venueListSource.includes('if(venue.id)return"venue.html?id="+encodeURIComponent(venue.id);'),
  "venue list must prefer stable venue IDs for detail links"
);

expect(detailSource.includes('var id=params.get("id")||"";'), "venue detail must accept ?id=");
expect(detailSource.includes('if(id&&candidate.id===id)return true;'), "venue detail must resolve exact stable venue IDs");
expect(detailSource.includes('var requestedKey=normalize(requested);'), "venue detail must normalize ?name= fallback keys");
expect(detailSource.includes('return requestedKey===key;'), "venue detail must match normalized names/aliases exactly");
expect(
  detailSource.includes("会場情報を読み込めませんでした。"),
  "venue detail must replace the loading state when venue data fetch fails"
);
expect(
  /venue-detail\.js\?v=[^"']+/.test(detailHtml),
  "venue-detail.js must be cache-busted so a stale broken script cannot leave the loading placeholder"
);
expect(
  /venue-detail-cleanup\.js\?v=[^"']+/.test(detailHtml),
  "venue-detail-cleanup.js must be cache-busted"
);

console.log(`venue detail contract: ${ids.size} stable venue IDs verified`);
