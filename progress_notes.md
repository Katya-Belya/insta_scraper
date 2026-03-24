# Progress Notes

## Phase 1: Feasibility (OCR Works)
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
- Identified consistent OCR errors in year field
- Applied normalization to correct misread years

Example:
RAW OCR: 02/17/2077  
NORMALIZED: 2/17/26  (manual correction for now)

Key insight:
- Isolating the date region and constraining OCR to a narrow character set significantly improved reliability.

---

## Current Status
- Date extraction works on a single flyer
- OCR is stable but imperfect
- Post-processing improves accuracy

---

## OCR Experiment Summary (Mar 24)
- Implemented region-based OCR (top/middle/bottom)
- Confirmed date location varies across flyers
- Tuned crop boxes for improved accuracy
- Identified grayscale preprocessing as most reliable
- Built regex-based numeric date extraction
- Observed OCR errors (e.g., incorrect year parsing)
- Began restructuring notebook into logical sections

---

## Next Steps
- Clean notebook structure (markdown + cell ordering)
- Build reusable extraction function (`extract_numeric_date`)
- Run pipeline across multiple images
- Support text-based date formats (e.g., "MARCH 27th")