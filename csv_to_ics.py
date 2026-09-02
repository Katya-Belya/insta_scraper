import csv
from datetime import date
from icalendar import Calendar, Event


cal = Calendar()
cal.add("prodid", "-//Instagram Flyer Scraper//")
cal.add("version", "2.0")


with open("results.csv", newline="", encoding="utf-8") as csv_file:
    reader = csv.DictReader(csv_file)

    for row in reader:
        # Skip rows where the pipeline did not find a usable date.
        if not row["event_date"]:
            continue

        event = Event()

        # TEMPORARY: use filename as the event title.
        # Later, we'll replace this with a real subject/title field.
        event.add("summary", row["filename"])

        # Your event_date is already YYYY-MM-DD.
        event_date = date.fromisoformat(row["event_date"])

        # A date, rather than a datetime, makes this an all-day event.
        event.add("dtstart", event_date)

        cal.add_component(event)


with open("events.ics", "wb") as output_file:
    output_file.write(cal.to_ical())


print("Created events.ics")