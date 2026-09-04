from pathlib import Path

path = Path("scripts/test_route_core.js")
text = path.read_text(encoding="utf-8")
text = text.replace(
    '''  [lineA]: {
    timeBasis: "station-departure-only",''',
    '''  [lineA]: {
    railway: lineA,
    timeBasis: "station-departure-only",''',
    1,
)
text = text.replace(
    '''  [lineB]: {
    timeBasis: "station-departure-only",''',
    '''  [lineB]: {
    railway: lineB,
    timeBasis: "station-departure-only",''',
    1,
)
old = '''const throughTimed = model.timedItinerary(path, throughTimetables, 475, "weekday", 5);
assert.equal(throughTimed.arrival, 502, "a matching same-operator continuation must preserve dwell without a fictitious transfer wait");
assert.equal(throughTimed.transfers, 0);
assert.equal(throughTimed.segments[1].throughFromPrevious, true);
'''
new = '''const throughWithoutIdentity = model.timedItinerary(path, throughTimetables, 475, "weekday", 5);
assert.equal(throughWithoutIdentity, null, "same operator, destination, and short dwell must not establish same-train identity");
const strictSameTrainResolver = (identityKey, fromRailway, toRailway) => {
  if (identityKey === `inf:${lineA}:0` && fromRailway === lineA && toRailway === lineB) return new Set([`inf:${lineB}:0`]);
  return null;
};
const throughTimed = model.timedItinerary(path, throughTimetables, 475, "weekday", 5, null, strictSameTrainResolver);
assert.ok(throughTimed, "an explicit same-train edge must preserve the continuation");
assert.equal(throughTimed.arrival, 502, "an explicit same-train continuation must preserve dwell without a fictitious transfer wait");
assert.equal(throughTimed.transfers, 0);
assert.equal(throughTimed.segments[1].throughFromPrevious, true);
'''
if old not in text:
    raise SystemExit("stale through-service test anchor was not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
