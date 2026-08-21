# Primary Sources and Normative Specifications

Use these sources to justify the method, not to replace repository evidence. Treat empirical results as bounded by their studied systems and dates.

## Modularity, contracts, and program families

- David L. Parnas, “On the Criteria to Be Used in Decomposing Systems into Modules,” *Communications of the ACM*, December 1972. Use information hiding and responsibility for a design decision as the basis for “same reason to change.” [DOI](https://doi.org/10.1145/361598.361623)
- David L. Parnas, “On the Design and Development of Program Families,” *IEEE Transactions on Software Engineering*, March 1976. Require substantial stable commonality before treating variants as one family. [Author-hosted copy](https://www.cse.msu.edu/~cse870/Materials/Parnas/program-families-TSE-March-1976.pdf)
- Barbara Liskov and Jeannette Wing, “A Behavioral Notion of Subtyping,” *ACM Transactions on Programming Languages and Systems*, November 1994. Preserve invariants, preconditions, postconditions, and exception behavior when claiming a common contract. [Author-hosted copy](https://www.cs.cmu.edu/~wing/publications/LiskovWing94.pdf)

## Clone evolution and refactorability

- Miryung Kim, Vibha Sazawal, David Notkin, and Gail Murphy, “An Empirical Study of Code Clone Genealogies,” ESEC/FSE, September 2005. Use clone age, divergence, consistent change, and practical refactorability instead of assuming every clone should be removed. [Author-hosted paper](https://web.cs.ucla.edu/~miryung/Publications/esecfse05-clonegenealogy.pdf)
- Cory Kapser and Michael Godfrey, “‘Cloning Considered Harmful’ Considered Harmful,” WCRE, October 2006. Recognize intentional patterns including platform isolation, experimentation, templates, and stable trusted copies. [Author-hosted paper](https://plg2.cs.uwaterloo.ca/~migod/papers/2006/wcre06-clonePatterns.pdf)
- Elmar Juergens, Florian Deissenboeck, Benjamin Hummel, and Stefan Wagner, “Do Code Clones Matter?” ICSE, May 2009. Treat inconsistent edits and defect propagation as project-specific risk evidence. [Institutional record](https://portal.fis.tum.de/en/publications/do-code-clones-matter/)
- Nils Göde and Rainer Koschke, “Frequency and Risks of Changes to Clones,” ICSE, May 2011. Use local change frequency and severity to avoid low-value clone warnings. [DOI](https://doi.org/10.1145/1985793.1985836)
- Nikolaos Tsantalis, Davood Mazinanian, and Giri Panamoottil Krishnan, “Assessing the Refactorability of Software Clones,” *IEEE Transactions on Software Engineering*, November 2015. Separate similarity detection from proof that differences can be parameterized without unsafe semantic changes. [Author artifact and paper](https://users.encs.concordia.ca/~nikolaos/TSE_2015/)

## Least-general generalization and matching

- Gordon Plotkin, “A Note on Inductive Generalization,” *Machine Intelligence 5*, 1970. Prefer the least-general shared form rather than maximizing abstraction. [Author publication index](https://homepages.inf.ed.ac.uk/gdp/publications/)
- Peter Bulychev and Marius Minea, “Duplicate Code Detection Using Anti-Unification,” SYRCoSE, 2008. Expose differing syntax subtrees as explicit holes in a common structure. [Author-hosted paper](https://staff.cs.upt.ro/~marius/papers/syrcose08.pdf)
- Jayant Madhavan, Philip Bernstein, and Erhard Rahm, “Generic Schema Matching with Cupid,” VLDB, September 2001. Combine lexical, type, constraint, and structural evidence when matching schemas. [VLDB paper](https://www.vldb.org/conf/2001/P049.pdf)
- Sergey Melnik, Hector Garcia-Molina, and Erhard Rahm, “Similarity Flooding: A Versatile Graph Matching Algorithm and Its Application to Schema Matching,” ICDE, February 2002. Use neighboring graph structure to propose mappings without treating a mapping as an automatic merge. [Author-hosted paper](https://dbs.uni-leipzig.de/files/research/publications/2002-1/pdf/icde2002-sf.pdf)
- Hong-Hai Do and Erhard Rahm, “COMA: A System for Flexible Combination of Schema Matching Approaches,” VLDB, August 2002. Combine specialized matchers, preserve confidence, and retain human-confirmed mappings. [VLDB paper](https://www.vldb.org/conf/2002/S17P03.pdf)

## History and change coupling

- Harald Gall, Karin Hajek, and Mehdi Jazayeri, “Detection of Logical Coupling Based on Product Release History,” ICSM, November 1998. Use release history to reveal dependencies that static structure does not show. [Author-hosted paper](https://turingmachine.org/~dmg/dchurch/icsm98.pdf)
- Thomas Zimmermann, Peter Weißgerber, Stephan Diehl, and Andreas Zeller, “Mining Version Histories to Guide Software Changes,” ICSE, May 2004; extended in *IEEE Transactions on Software Engineering*, June 2005. Treat co-change as ranked evidence, not causal proof. [Author-hosted paper](https://www.cs.kent.edu/~jmaletic/cs63902/Papers/Zimmermann04.pdf)

## Refactoring and verification

- William Opdyke, “Refactoring Object-Oriented Frameworks,” PhD dissertation, July 1992. Require behavior-preservation preconditions and abstain when they cannot be established. [Author-hosted dissertation](https://www.laputan.org/pub/papers/opdyke-thesis.pdf)
- Brett Daniel, Danny Dig, Kely Garcia, and Darko Marinov, “Automated Testing of Refactoring Engines,” ESEC/FSE, September 2007. Do not treat an IDE or automated transformation as a proof of correctness. [Author-hosted paper](https://dig.cs.illinois.edu/papers/AutomatedTestingOfRefactoringEngines.pdf)
- Koen Claessen and John Hughes, “QuickCheck: A Lightweight Tool for Random Testing of Haskell Programs,” ICFP, September 2000. Express shared invariants as properties and exercise generated cases. [DOI](https://doi.org/10.1145/351240.351266)
- William McKeeman, “Differential Testing for Software,” *Digital Technical Journal*, 1998. Compare old and proposed implementations over common inputs while accounting for permitted nondeterminism. [Archived paper](https://www.cs.swarthmore.edu/~bylvisa1/cs97/f13/Papers/DifferentialTestingForSoftware.pdf)
- Gregg Rothermel and Mary Jean Harrold, “A Safe, Efficient Regression Test Selection Technique,” *ACM Transactions on Software Engineering and Methodology*, April 1997. Select affected tests conservatively and retain full regression checks when risk warrants them. [DOI](https://doi.org/10.1145/248233.248262)

## API and variability costs

- Danny Dig and Ralph Johnson, “How Do APIs Evolve? A Story of Refactoring,” *Journal of Software Maintenance and Evolution*, April 4, 2006. Account for consumer migration and compatibility when a consolidation creates or changes a shared API. [Author-hosted paper](https://dig.cs.illinois.edu/papers/JSME_API_Evolution.pdf)
- Thorsten Berger and collaborators, “A Study of Variability Models and Languages in the Systems Software Domain,” *IEEE Transactions on Software Engineering*, December 2013. Preserve defaults, derived features, and cross-option constraints in configuration abstractions. [Author-hosted paper](https://gsd.uwaterloo.ca/sites/default/files/vm-2013-berger.pdf)
- Jacob Krüger and Thorsten Berger, “An Empirical Analysis of the Costs of Clone- and Platform-Oriented Software Reuse,” ESEC/FSE, November 2020. Evaluate setup, reuse, quality, and change-propagation costs rather than assuming a shared platform is always cheaper. [Institutional record](https://research.chalmers.se/en/publication/549120)
- Alejandra Echeverría and collaborators, “An Empirical Study of Performance Using Clone & Own and Software Product Lines in an Industrial Context,” *Information and Software Technology*, February 2021. Treat prototype urgency, anticipated reuse, and family maturity as relevant to the clone-versus-platform choice. [Publisher record](https://www.sciencedirect.com/science/article/pii/S0950584920301968)

## Design systems, workflows, prompts, and assets

- Muluba Lamine and Jinghui Cheng, “Understanding and Supporting the Design Systems Practice,” preprint submitted May 22, 2022. Compare component behavior and governance, not appearance alone, and prefer bottom-up extraction from demonstrated product needs. [Preprint](https://arxiv.org/abs/2205.10713)
- W3C Design Tokens Community Group, “Design Tokens Format Module 2025.10,” Community Group Final Report, October 28, 2025. Preserve token types and semantic aliases; reject circular references and type mismatches. Treat this as a Community Group report, not a W3C Standard. [Specification](https://www.w3.org/community/reports/design-tokens/CG-FINAL-format-20251028/)
- Remco Dijkman, Marlon Dumas, Boudewijn van Dongen, Reina Käärik, and Jan Mendling, “Similarity of Business Process Models: Metrics and Evaluation,” *Information Systems*, April 2011. Compare workflow labels, structure, and causal behavior and allow non-one-to-one task mappings. [Institutional copy](https://pure.tue.nl/ws/portalfiles/portal/152658590/beta_publication.pdf)
- OMG, “Business Process Model and Notation 2.0,” adopted December 2010. Define reusable callable processes with explicit boundaries rather than copying workflow fragments. [Normative specification](https://www.omg.org/spec/BPMN/2.0/)
- Yao Lu and collaborators, “Fantastically Ordered Prompts and Where to Find Them,” ACL, May 2022. Treat example order and model choice as behavioral variables, so prompt-text similarity cannot establish equivalence. [ACL Anthology](https://aclanthology.org/2022.acl-long.556.pdf)
- Omar Khattab and collaborators, “DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines,” submitted October 5, 2023; presented at ICLR 2024. Separate a stable task or pipeline declaration from optimized prompt text and require an external evaluation metric. [Preprint](https://arxiv.org/abs/2310.03714)
- Zhou Wang, Alan Bovik, Hamid Sheikh, and Eero Simoncelli, “Image Quality Assessment: From Error Visibility to Structural Similarity,” *IEEE Transactions on Image Processing*, April 2004. Use perceptual similarity to discover image candidates, not to establish common role, provenance, or rights. [DOI](https://doi.org/10.1109/TIP.2003.819861)
- Microsoft, “OpenType Specification 1.9.1: Naming Table.” Compare unique identifiers, versions, typographic roles, PostScript names, and license metadata before consolidating fonts. [Normative specification](https://learn.microsoft.com/en-us/typography/opentype/spec/name)

## Evaluation, drift, and governed improvement

- OpenAI, “Working with evals.” Define the task, test on representative inputs with ground-truth labels, and analyze results before iterating. Keep this skill's exact deterministic checks local because the hosted Evals platform has a published 2026 deprecation timeline. [Official guide](https://developers.openai.com/api/docs/guides/evals)
- OpenAI, “Graders.” Prefer exact string or executable graders where the outcome is mechanically decidable; when a model grader is necessary, keep it separate from the model producing the candidate and audit for grader hacking. [Official guide](https://developers.openai.com/api/docs/guides/graders)
- Shyamal Anadkat, “How to make your completions outputs consistent with the seed parameter,” OpenAI Cookbook, November 6, 2023. Treat matching seeds, parameters, and backend fingerprints as best-effort reproducibility only; the source explicitly does not guarantee determinism. [Official example](https://cookbook.openai.com/examples/reproducible_outputs_with_the_seed_parameter)
- Cynthia Dwork, Vitaly Feldman, Moritz Hardt, Toniann Pitassi, Omer Reingold, and Aaron Roth, “The Reusable Holdout: Preserving Validity in Adaptive Data Analysis,” *Science*, August 7, 2015. Separate improvement inputs from a holdout and account for adaptive reuse instead of repeatedly tuning against the same visible cases. [DOI](https://doi.org/10.1126/science.aaa9375)
- SLSA, “Provenance,” specification version 1.2. Record content identities and the inputs that produced an evaluation or candidate so a later verifier can detect changed materials instead of trusting a mutable label. [Approved specification](https://slsa.dev/spec/v1.2/provenance)

## Interpretation boundary

Use the literature to establish three guardrails:

1. Discover candidates from resemblance, structure, and history.
2. Justify consolidation from shared responsibility, compatible contracts, and testable change pressure.
3. Preserve intentional separation when variability, isolation, authority, licensing, or verification makes consolidation unsafe.

Do not import a paper's threshold or result as a universal repository rule. Calibrate detector thresholds and dispositions with independently graded local evaluations.
