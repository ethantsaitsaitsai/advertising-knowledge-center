# Config NameError Fix

## Problem
A `NameError: name 'config' is not defined` occurred in `nodes/response_synthesizer.py`.
- **Root Cause**: The code attempted to access `config.get_hidden_columns()` to hide technical IDs during fallback execution, but the `config` object (from `config.registry`) was not imported.

## Solution
Added the missing import to `nodes/response_synthesizer.py`:
```python
from config.registry import config
```

## Verification
The syntax error is resolved. The fallback logic will now correctly retrieve the list of hidden columns (e.g., `cmpid`, `id`) and remove them from the dataframe, ensuring a clean user output even when data fusion fails.
