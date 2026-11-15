# The model chooses Protocol IDs; it never writes treatment text

Every Step a Responder sees is copied word for word from `rules.md`. The model only returns Protocol IDs, Check IDs, a rationale and what it observed. The service throws away any ID that isn't in the Protocol list or the Check catalogue. Severity and GCS are computed by code, not by the model. A 2B-effective model paraphrasing drug doses ("0.3 mg" becoming "3 mg") is a failure that a post-hoc text check can't reliably catch. Not generating the text at all rules it out by construction. The only presentation change is removing the `(#N)` markers, which referred to the deleted biomarker guide.

## Considered Options

- **Model writes the steps, and a verifier compares them with the retrieved text**: more fluent, but the verifier becomes the safety-critical component, and small numeric changes are exactly what fuzzy comparison misses.
