# DLP Nova repository instructions

Apply the applicable parent-directory `AGENTS.md` instructions as well as these
project-specific rules.

## Software artifact name

- The software artifact in this repository is named **DLP Nova**. Use this name
  in documentation, papers, explanations, and other user-facing references to
  the implementation.
- **Description Logic Programs (DLP)** remains the name of the underlying
  language and theoretical foundation; DLP L0–L3 denotes its language fragments.
  Distinguish these concepts from the software name.
- Existing technical identifiers remain `dlp-reasoner` (distribution),
  `dlp_reasoner` (Python package), and `dlp` (CLI). The product naming does not
  authorize renaming packages, commands, APIs, file formats, or namespaces.
- Preserve the exact titles and names of historical theses, papers, external
  systems, and bibliographic references.

## Application-driven extensions

- Ground proposed extensions in concrete requirements from applications or
  users. Identify the motivating data, query or update workflow, the current
  limitation, and an observable acceptance criterion.
- Distinguish demonstrated example behavior from validated user demand. Treat
  capabilities with no established application need as options to assess,
  rather than a committed feature roadmap.
