---
trigger: always_on
---

Use conda environment "web_app".

Design documentation is provided in ./docs/design.md.

Update design.md only when architecture rules, cross-file contracts, or design rationale change. Do not add file inventories, class field listings, or other content derivable from the code — design.md deliberately omits those. If you encounter any inconsistencies between the design documentation and the code, raise the issue and ask for permission before making corrections.

The TrueSkillThroughTime library is vendored in ./vendor/trueskillthroughtime/ (v2.0.0, plus local fixes recorded in git history). Upstream documentation and examples are at https://github.com/glandfried/TrueSkillThroughTime.py; ./examples/ has a local usage example.