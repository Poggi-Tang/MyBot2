---
name: normalize-whitespace
description: Normalize repeated whitespace in a UTF-8 text file using the validated bundled script. Use when a user asks to clean, collapse, or standardize whitespace in text.
---

# Normalize Whitespace

Use the bundled script with explicit input and output paths:

```text
python scripts/normalize_whitespace.py --input <input> --output <output>
```

Preserve the file encoding as UTF-8. Confirm the output exists and run the bundled tests when changing the implementation.
