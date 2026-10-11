# Manual Labeling Guide

For each candidate phrase:

1. Read the phrase and open the original `source_url` if context is unclear.
2. Correct the phrase only if extraction introduced an error.
3. Assign one valid research category.
4. Map to an exact PSF-AAI competency only when the framework supports the mapping.
5. Use `IRRELEVANT` for non-skill/non-competency text.
6. Do not infer a competency that is not supported by the source text.
7. Keep human labels separate from later model predictions.

Minimum quality checks before training:
- at least 2 classes
- preferably >= 30 total reviewed phrases for software training to run
- preferably >= 5 examples per class as a bare minimum
- substantially more reviewed examples are recommended for final research reporting
