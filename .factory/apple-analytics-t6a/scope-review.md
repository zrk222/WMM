# T6a scope review

This backend slice adds a deterministic selector for the newest complete daily
Apple App Downloads Standard instance and a bounded read-only agent operation.
It adds no visible interface or keyboard/assistive-technology behavior, so
accessibility is not applicable. Provider inventory and segment calls are
mocked in local tests. The tests confirm which exact instance would be read;
they do not demonstrate a live Apple account read.
