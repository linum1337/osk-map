# Product copy

Keep user-facing portal pages free of editorial and work-process commentary. Do not add phrases about what was checked, added, missing earlier, matched from a table, or still needs investigation. Report progress and research limitations in chat, not in product content.

Use names, factual technical descriptions, meaningful differences, and source links. Show unknown comparison values as an em dash; never invent a value or claim interchangeability. Preserve provenance and verification metadata internally.

In cable reference lists and comparisons, show manufacturers in this priority order: OSK (`osk`), Beltelecabel (`beltele`), Incab (`incab`), SOCC (`socc`), Saranskkabel-Optika (`sarko`), then the remaining manufacturers.

Cable analogue groups must separate two peripheral FRP rods from a single central strength member. Do not group all optical/electrical hybrid cables as structural analogues solely because they contain both copper and fibres.

Section access is enforced by section_access.py for documents, APIs, assets and legacy aliases. Keep per-user grants in the persistent database; never write production grants into source. Preserve existing role defaults, keep optical closures administrator-only by default, and protect the owner account from lockout. Revoke existing sessions after permission changes and record the actor in the audit.

Every published optical closure record must have a reviewed model or clearly labelled same-model housing image from its product source or manufacturer, never a no-photo placeholder. Validate complete image coverage before publication. Closure analogue selection must separate splice closures from terminal/cross closures, enforce specified construction, capacity, port count, seal, transit, IP and climate requirements, and exclude unknown required values. Mixed heat-shrink/mechanical cable seals are a separate choice, not equivalent to uniformly heat-shrink or uniformly mechanical inputs.

Closure price refresh is restricted to the portal owner account, including direct API calls. Preserve every publicly published price tier and its quantity/VAT conditions; do not scrape related-product prices or turn missing/zero values into free offers. Keep the daily 86400-second schedule and last price timestamps in persistent runtime state; never commit live price snapshots.
