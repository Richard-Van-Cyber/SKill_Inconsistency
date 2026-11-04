# SkillBench finding verification — results

Findings verified: **377** across **72** tasks that received findings (87 audited SkillBench tasks in total).

| verdict | findings | share |
|---|---:|---:|
| confirmed | 120 | 31.8% |
| mislabeled | 40 | 10.6% |
| invalid | 217 | 57.6% |
| **survive (confirmed + mislabeled)** | **160** | **42.4%** |
| **confirmed only** | **120** | **31.8%** |

## Why findings were rejected

| reason code | findings |
|---|---:|
| no_contradiction | 113 |
| speculation | 29 |
| not_a_contract | 27 |
| duplicate | 26 |
| evidence_not_found | 21 |
| out_of_scope | 1 |

## Survival by claimed layer

| claimed L1 | total | confirmed | mislabeled | invalid | survive % |
|---|---:|---:|---:|---:|---:|
| implementation | 178 | 72 | 18 | 88 | 50.6% |
| environmental | 125 | 18 | 16 | 91 | 27.2% |
| document | 74 | 30 | 6 | 38 | 48.6% |

## Survival by producing checker

| checker | total | confirmed | mislabeled | invalid | survive % |
|---|---:|---:|---:|---:|---:|
| impl_over_promised_checker | 149 | 60 | 14 | 75 | 49.7% |
| env_layer_checker | 104 | 18 | 16 | 70 | 32.7% |
| doc_layer_checker | 74 | 30 | 6 | 38 | 48.6% |
| impl_semantic_conflict_checker | 28 | 12 | 4 | 12 | 57.1% |
| env_constraint_checker | 14 | 0 | 0 | 14 | 0.0% |
| url_validator | 7 | 0 | 0 | 7 | 0.0% |
| schema_comparator | 1 | 0 | 0 | 1 | 0.0% |

## Survival by claimed level-2 type (top 12)

| L2 | total | confirmed | mislabeled | invalid | survive % |
|---|---:|---:|---:|---:|---:|
| over_promised | 149 | 60 | 14 | 75 | 49.7% |
| environment_fact_conflict | 87 | 14 | 11 | 62 | 28.7% |
| shared_concept_definition_conflict | 40 | 17 | 1 | 22 | 45.0% |
| interface_contract_mismatch | 29 | 11 | 4 | 14 | 51.7% |
| semantic_conflict | 26 | 12 | 4 | 10 | 61.5% |
| dependency_version_drift | 16 | 0 | 1 | 15 | 6.2% |
| external_resource_invalid | 12 | 3 | 0 | 9 | 25.0% |
| external_service_contract_change | 10 | 1 | 4 | 5 | 50.0% |
| cross_document_process_conflict | 5 | 2 | 1 | 2 | 60.0% |
| semantically_conflicting | 2 | 0 | 0 | 2 | 0.0% |
| under_promised | 1 | 0 | 0 | 1 | 0.0% |

## Mislabeling flows (claimed layer -> corrected layer)

| flow | findings |
|---|---:|
| environmental -> implementation | 10 |
| implementation -> document | 9 |
| implementation -> environmental | 7 |
| environmental -> document | 6 |
| document -> implementation | 6 |
| implementation -> implementation | 2 |

## Effect on the RQ1 numbers

| metric | as audited | confirmed only | confirmed + relabelled |
|---|---:|---:|---:|
| tasks with >=1 inconsistency | 72 | 49 | 56 |
| prevalence | 82.8% | 56.3% | 64.4% |
| total findings | 377 | 120 | 160 |
| mean per task | 5.24 | 1.67 | 2.22 |
| median per task | 4 | 1 | 1 |
| P90 per task | 12 | 3 | 4 |

Artifact-boundary mix (share of findings):

| layer | as audited | confirmed only | confirmed + relabelled |
|---|---:|---:|---:|
| Document-Code | 47.2% | 60.0% | 56.2% |
| Skill-Environment | 33.2% | 15.0% | 15.6% |
| Document-Document | 19.6% | 25.0% | 28.1% |
