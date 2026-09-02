## Update before meeting

### Progress

Since the last review:

* Expanded the date parser to support abbreviated months, punctuation variations, and numeric dates.
* All automated tests pass: **68/68**.
* Re-ran the same flyer benchmark:

  * Crop-based pipeline: **0/10**
  * Full-image OCR: **5/10**
  * Full-image OCR + expanded parser: **8/10**
* The remaining two failures appear to be OCR failures rather than parser-format failures.
* Added a command-line runner so the pipeline can now process either one flyer or an entire folder with one command.

Example:

`python -m src.pipeline data/raw/`

### Current pipeline

Flyer(s)
→ full-image OCR
→ text cleanup
→ date extraction
→ date normalization
→ result

### Proposed next step: structured result

I want every processed flyer to produce the same `FlyerResult`:

* `filename`
* `raw_text`
* `clean_text`
* `date_found`
* `event_date`
* `valid`

Each `FlyerResult` would eventually become one row in the CSV, with each field becoming a column.

### Questions

1. **Is this the right V1 result schema?**

   * Are these the right fields?
   * Is anything important missing?
   * Is anything unnecessary?

2. **Should `valid` mean “a date was successfully extracted,” or do I need a more descriptive status instead?**

3. **Should review information live directly in `FlyerResult`?**
   For example:

   * `status`
   * `needs_review`
   * eventually `confidence`

4. **At 8/10 benchmark accuracy, should I stop improving extraction for now and finish the product workflow?**
   The two remaining failures appear to be OCR failures.

5. **Is this still the right order for the remaining V1 work?**

   Structured result
   → CSV export
   → review/status handling
   → more benchmark flyers
   → README

6. **For V1, what should the final user experience be?**
   Is this sufficient?

   `folder of flyers → one command → CSV → manually review flagged rows`

7. **How large should the benchmark be before I consider V1 demonstrated?**
   I currently have 10 flyers.
