\# Flyer Evaluation Set



This folder contains a small manually labeled evaluation set for the event-date extraction pipeline.



\## Files



\- `ground\_truth.csv`: human-labeled correct answers

\- `results\_v0.1.csv`: outputs from the current pipeline version



\## Evaluation process



For each flyer:



1\. Run the image through the existing pipeline.

2\. Record the extracted date and raw OCR text.

3\. Mark the result as correct or incorrect.

4\. For failures, identify the likely stage:

&#x20;  - crop

&#x20;  - OCR

&#x20;  - cleanup

&#x20;  - regex

&#x20;  - normalization

&#x20;  - date selection

