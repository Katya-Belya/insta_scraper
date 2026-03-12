# Insta Scraper OCR Project

## Current milestone
Working prototype for extracting flyer dates using OCR.

Pipeline:
image → crop → preprocess → OCR → regex

Example result:

RAW OCR: Pa 3/17/3679!
DATE FOUND: 3/17/36

Actual flyer text:
TUES 2/17/26 7 PM

## Next steps
1. Improve crop region
2. Add Tesseract whitelist for digits
3. Improve preprocessing
4. Test extraction on multiple flyers