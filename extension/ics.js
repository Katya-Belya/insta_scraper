// Build an iCalendar file from canonical reviewed flyer results.
//
// This file contains no popup, storage, or download behavior. Keeping calendar
// generation separate makes it possible to test without running Chrome.

const EXPORTABLE_REVIEW_STATUSES = new Set(["accepted", "edited"]);

function escapeIcsText(value) {
  return String(value)
    .replaceAll("\\", "\\\\")
    .replaceAll("\n", "\\n")
    .replaceAll(",", "\\,")
    .replaceAll(";", "\\;");
}

function parseIsoDate(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value ?? "");

  if (!match) {
    return null;
  }

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));

  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return null;
  }

  return date;
}

function formatIcsDate(date) {
  return [
    date.getUTCFullYear().toString().padStart(4, "0"),
    (date.getUTCMonth() + 1).toString().padStart(2, "0"),
    date.getUTCDate().toString().padStart(2, "0"),
  ].join("");
}

function formatIcsTimestamp(date) {
  return (
    formatIcsDate(date) +
    "T" +
    [
      date.getUTCHours().toString().padStart(2, "0"),
      date.getUTCMinutes().toString().padStart(2, "0"),
      date.getUTCSeconds().toString().padStart(2, "0"),
    ].join("") +
    "Z"
  );
}

function generateReviewedEventsIcs(results, generatedAt = new Date()) {
  const events = results
    .filter((result) =>
      EXPORTABLE_REVIEW_STATUSES.has(result.reviewStatus)
    )
    .map((result, index) => {
      const startDate = parseIsoDate(result.eventDate);

      if (!startDate) {
        return null;
      }

      const endDate = new Date(startDate);
      endDate.setUTCDate(endDate.getUTCDate() + 1);

      return [
        "BEGIN:VEVENT",
        `UID:${encodeURIComponent(result.filename)}-${formatIcsDate(startDate)}-${index}@instagram-flyer-scraper`,
        `DTSTAMP:${formatIcsTimestamp(generatedAt)}`,
        `SUMMARY:${escapeIcsText(result.filename)}`,
        "DESCRIPTION:Time not extracted. Verify event details from the original flyer.",
        `DTSTART;VALUE=DATE:${formatIcsDate(startDate)}`,
        `DTEND;VALUE=DATE:${formatIcsDate(endDate)}`,
        "END:VEVENT",
      ];
    })
    .filter((event) => event !== null);

  if (events.length === 0) {
    return null;
  }

  return [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Instagram Flyer Scraper//EN",
    "CALSCALE:GREGORIAN",
    ...events.flat(),
    "END:VCALENDAR",
    "",
  ].join("\r\n");
}

window.generateReviewedEventsIcs = generateReviewedEventsIcs;