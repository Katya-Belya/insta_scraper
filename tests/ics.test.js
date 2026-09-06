/*
 * Tests for extension/ics.js.
 *
 * Run with:
 *
 *     node tests/ics.test.js
 */

const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const ICS_SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "extension", "ics.js"),
  "utf8"
);

const sandbox = { window: {} };
vm.createContext(sandbox);
vm.runInContext(ICS_SOURCE, sandbox);

const generateIcs = sandbox.window.generateReviewedEventsIcs;
const generatedAt = new Date("2026-09-06T04:00:00Z");

const failures = [];

function test(name, run) {
  try {
    run();
    console.log(`ok   ${name}`);
  } catch (error) {
    failures.push(name);
    console.log(`FAIL ${name}\n     ${error.message}`);
  }
}

test("an accepted result becomes an all-day event", () => {
  const ics = generateIcs(
    [
      {
        filename: "cherry_blossom_market.jpeg",
        originalEventDate: "2027-03-27",
        eventDate: "2027-03-27",
        needsReview: false,
        reviewStatus: "accepted",
      },
    ],
    generatedAt
  );

  assert.ok(ics.includes("SUMMARY:cherry_blossom_market.jpeg"));
  assert.ok(
  ics.includes(
    "DESCRIPTION:Time not extracted. Verify event details from the original flyer."
  )
);
  assert.ok(ics.includes("DTSTART;VALUE=DATE:20270327"));
  assert.ok(ics.includes("DTEND;VALUE=DATE:20270328"));
});

test("an edited result uses eventDate instead of originalEventDate", () => {
  const ics = generateIcs(
    [
      {
        filename: "corrected_flyer.jpeg",
        originalEventDate: "2027-03-27",
        eventDate: "2027-03-29",
        needsReview: true,
        reviewStatus: "edited",
      },
    ],
    generatedAt
  );

  assert.ok(ics.includes("DTSTART;VALUE=DATE:20270329"));
  assert.ok(ics.includes("DTEND;VALUE=DATE:20270330"));
  assert.ok(!ics.includes("DTSTART;VALUE=DATE:20270327"));
});

test("a pending result is not exported", () => {
  const ics = generateIcs(
    [
      {
        filename: "pending_flyer.jpeg",
        originalEventDate: "2027-04-10",
        eventDate: "2027-04-10",
        needsReview: true,
        reviewStatus: "pending",
      },
    ],
    generatedAt
  );

  assert.strictEqual(ics, null);
});

if (failures.length > 0) {
  console.log(`\n${failures.length} check(s) failed.`);
  process.exitCode = 1;
} else {
  console.log("\nAll checks passed.");
}