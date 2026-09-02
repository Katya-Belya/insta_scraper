# **Mentor Meeting Notes — August 26, 2026**

---

## **Progress Since Last Review**

### **Benchmark / Extraction**

Tested the pipeline on a harder V2 benchmark of 10 Instagram flyer screenshots.

The new benchmark exposed four main issues:

* Additional OCR/date-format variations  
* Multiple dates in the same Instagram screenshot  
* Benchmark results changing depending on the current date  
* Wrong-but-confident results where Instagram metadata is selected as the event date

The parser now handles cases such as:

SEPT. 5TH

AUGUST)27th

APR. 25

AUG.12

8/4

8-4

The date-selection logic also changed from:

find first date → assume it is the event date

to:

extract all date candidates → select most plausible event date → normalize

The current rule selects the candidate whose next occurrence is closest to the reference date.

To make benchmarks reproducible, the pipeline now accepts a fixed reference date:

python \-m src.pipeline data/raw/benchmark\_v2 \--today 2026-08-20

Normal usage still uses the actual current date.

| Benchmark | Accuracy |
| ----- | ----- |
| Original 10-flyer benchmark | **8/10 (80%)** |
| Harder V2 10-flyer benchmark | **7/10 (70%)** |

These are different flyer sets, so the percentages are not a direct before/after comparison.

The three V2 failures are:

| File | Expected | Actual | Issue |
| ----- | ----- | ----- | ----- |
| `1000035680.jpg` | 9/12/2026 | None | OCR failure |
| `1000035687.jpg` | 10/10/2026 | 7/27/2027 | Actual flyer date missed; metadata date selected |
| `1000035707.jpg` | 8/21/2026 | 7/21/2027 | Actual flyer date missed; metadata date selected |

The main conclusion is that basic date parsing is no longer the obvious bottleneck.

### **Reliability / Review**

The harder benchmark exposed an important distinction:

**Safe failure**

no date found

status \= "no\_date\_found"

needs\_review \= True

**Dangerous failure**

wrong date

status \= "ok"

needs\_review \= False

The second case is more concerning because the program is wrong without knowing it.

Improving `needs_review` for these silent errors remains on the to-do list, especially where Instagram metadata can be mistaken for the event date. However, broader backend/OCR refinement should not prevent completing the V1 workflow.

### **Chrome Extension Prototype**

Built a small local Chrome extension proof of concept.

It currently:

* Displays a fake structured `FlyerResult`  
* Shows filename, date, status, and review state  
* Supports basic Accept/Edit interactions  
* Populates the UI from JavaScript data

This proves that structured result data can feed a browser UI.

The mentor recommendation was to **stick with desktop/Chrome for V1** rather than spending limited project time solving mobile support.

The next UI goal is therefore to move toward a full desktop end-to-end workflow rather than continuing to investigate different interface platforms.

### **Testing**

**79/79 automated tests passing.**

Tests now cover:

* Existing parser behavior  
* New date formats  
* Multiple date candidates  
* Event-date selection  
* Date normalization  
* Fixed reference-date behavior

---

## **V1 Progress**

* ✅ Parser improvements  
* ✅ One-command pipeline  
* ✅ Structured results  
* ✅ CSV export  
* ✅ Basic review statuses  
* ✅ Multiple-date extraction  
* ✅ Event-date selection  
* ✅ Reproducible benchmark runs  
* ✅ Chrome extension proof of concept  
* ⬜ Improve obvious silent-error / `needs_review` cases  
* ⬜ Connect real pipeline results to the Chrome UI  
* ⬜ Complete an end-to-end desktop run  
* ⬜ Improve the Accept/Edit review experience  
* ⬜ Experiment with CSV → iCal/ICS output  
* ⬜ Update README  
* ⬜ V1 demo/polish

Broader OCR improvements, additional backend refinement, mobile support, and more sophisticated confidence scoring can move to a V2/backlog unless they block the V1 workflow.

---

## **Mentor Feedback / Decisions**

### **1\. Prioritize the full workflow over further backend optimization**

With limited time remaining, the priority should be getting the project working **end to end** rather than continuing to optimize OCR/date extraction.

The goal is to demonstrate the full user experience:

flyer → extraction → structured result → review → accepted result → export

Backend improvements should be made when they directly affect this workflow, but deeper OCR optimization can be deferred.

### **2\. Keep silent errors / `needs_review` on the to-do list**

Wrong-but-confident metadata dates are still an important reliability issue.

The system should ideally identify suspicious results and send them to review, but this does not need to become a large confidence-scoring project for V1.

Focus on practical fixes that improve the user experience.

### **3\. Stick with desktop / Chrome for V1**

Do not spend time trying to solve mobile support right now.

The Chrome extension is an acceptable V1 direction, and the immediate goal should be making the desktop workflow work well.

Mobile and alternate interfaces can be revisited later.

### **4\. Spend more time experimenting with UX**

Now that the basic backend exists, try more ideas for how the user actually interacts with the result.

This includes:

* How warnings are shown  
* How Accept/Edit works  
* How obvious it is when something needs review  
* How the final result is presented  
* How much technical information the user actually needs to see

A coding agent/free-tier development tool can be useful for trying bounded UX changes quickly.

### **5\. Try CSV → iCal/ICS export**

Since the eventual purpose is to turn flyer information into usable event data, experiment with converting the CSV output into calendar format.

This provides another useful end-to-end output without requiring major new OCR work.

---

## **Next Week**

### **Main priority: full end-to-end V1**

1. Get a real flyer through the complete workflow.  
2. Connect real `FlyerResult` output to the Chrome interface.  
3. Make the Accept/Edit review flow functional.  
4. Make `needs_review` catch the most obvious suspicious metadata-date cases.  
5. Run the full workflow repeatedly with several flyers.  
6. Improve the UX based on what feels awkward or unclear.  
7. Experiment with converting CSV output to iCal/ICS.  
8. Update the README and prepare a clean V1 demo.

### **Backlog / V2**

Unless they block the V1 workflow, defer:

* Additional OCR optimization  
* More complex date-selection logic  
* Sophisticated confidence scoring  
* Large benchmark expansion  
* Mobile support  
* Other backend refinements

---

## **V1 Direction**

The target is now:

flyer

  ↓

OCR / date extraction

  ↓

structured result

  ↓

review if needed

  ↓

Accept / Edit

  ↓

final result

  ↓

CSV / calendar export

The immediate goal is no longer to make the extraction technology as accurate as possible.

The goal is to **finish a usable desktop workflow, try the complete user experience, and move nonessential backend improvements into V2.**

