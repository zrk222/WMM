# T5 scope review

This slice changes the backend provider-read and SQLite worker path. It adds no
screen, keyboard interaction, or assistive-technology behavior, so accessibility
is not applicable here. The report acquisition is an external read effect and
is in scope: tests mock Apple endpoints and signed-segment downloads, verify the
bounded read contract, and do not contact Apple. No live Apple account read or
provider acceptance is evidenced by this review.
