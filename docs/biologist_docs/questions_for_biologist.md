# Questions for the biologist

We’re integrating your dataset into the database and dashboard. Could you help clarify the following?

1. **Which file is authoritative?** The supplied CSV and builder script have different output names and structures. Which version should we use?

2. **What does each biomarker column represent, and what are its units?** Could you provide a short data dictionary?

3. **Is `BM03_CRP` actually CRP or IL-6?** The builder reads an IL-6 source column, while the CSV calls it CRP.

4. **Is `BM05_Uromodulin` actually uromodulin or LCN2/NGAL?** The builder appears to use an LCN2 column. What units apply?

5. **Why are BM04 and BM12 absent from the CSV?** Should urinary calcium and skin score be included, or excluded from the dashboard?

6. **Which values are directly measured, calculated proxies, or filled from another subject?** Can we identify this for each observation? In particular, the script calculates PTT, WASO, ONSD, and PERCLOS from heart or respiratory rate.

7. **Who do the subject IDs represent?** Are the `I4_*` and `PHYS_AST_*` groups separate populations? Should they always remain separate, and is any mapping to our demo crew intended?

8. **What do `Chronological_Day` and `Timepoint_Label` mean?** Are these actual mission days, sample order, or another index? Are original collection dates available, and are timepoints aligned across biomarkers?

9. **What do blank cells mean?** Not measured, unavailable, below detection limit, or excluded during processing?

10. **Can you provide the original source references and transformation steps?** Ideally, each observation should be traceable to its source dataset, sample, and any calculation.

11. **Which reference ranges should the visuals use?** Please specify units, applicable population, supporting references, and whether the proposed thresholds are exploratory or intended to trigger alerts.

12. **How will future results arrive?** Manual lab entry, CSV batches, or instrument exports? What specimen, device, assay, and collection-time information should we record?

13. **What should users see first?** Which biomarkers and trends matter most, and what explanations should accompany unusual values?
