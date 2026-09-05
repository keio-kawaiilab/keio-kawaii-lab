# Keikyu Main ↔ Airport diagnostic policy

This branch is diagnostic only. It does not alter production same-train edges.

A candidate is accepted only when the same official Keikyu printed train column contains both:

- an exact Shinagawa time that resolves to exactly one Keikyu Main fragment for the service day; and
- an exact Haneda Airport time that resolves to exactly one Keikyu Airport fragment for the service day.

Train number alone and time proximity alone are never accepted as train identity evidence. Ambiguous or missing matches remain unresolved.
