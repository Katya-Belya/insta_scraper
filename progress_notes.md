# Progress Notes

## Phase 1: Feasibility (OCR works)
- Set up Tesseract and environment
- Ran OCR on full images (too noisy)
- Introduced region-based cropping
- Successfully extracted rough date text

Example:
RAW OCR: Pa 3/17/3679!
DATE FOUND: 3/17/36

---

## Phase 2: Crop Optimization
- Tested multiple crop regions
- Identified best crop:
  (120, 930, 980, 1080)
- Result: reduced noise and improved OCR consistency
---

## Phase 3: Preprocessing Experiments
Tested:
- grayscale
- resize
- threshold
- threshold + resize

Finding:
- grayscale alone performed best
- resizing and thresholding degraded OCR accuracy

---

## Phase 4: OCR Configuration
- Tested multiple PSM modes (6, 7, 8, 13)
- Finding: minimal impact on results
- Added character whitelist (digits + "/")

---

## Phase 5: Date Extraction
- Implemented regex:
  (\d{1,2})/(\d{1,2})/(\d{2,4})
- Parsed month/day/year
- Added validation (month 1–12, day 1–31)

---

## Phase 6: Post-processing
- Identified consistent OCR error in year field
- Implemented normalization step to correct misread years

Example:
RAW OCR: 02/17/2077  
NORMALIZED: 2/17/26   (human eye balling)

The key improvement was isolating the date region and constraining OCR to a narrow character set, which turned noisy text into a consistent, parseable format.

---

## Current Status
- Date extraction works on a single flyer
- OCR is stable but imperfect
- Post-processing improves accuracy

## Session Summary 3/24/2026

- Implemented region-based OCR (top/middle/bottom)
- Identified best crop for cherry_blossom_market.jpeg
- Determined grayscale preprocessing is most reliable
- Built working numeric date extraction prototype
- Began restructuring notebook with markdown sections

## Next steps:
- clean notebook structure
- build reusable extraction function
- run pipeline across multiple images
- support text-based date formats