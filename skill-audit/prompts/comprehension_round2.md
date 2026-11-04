You are analyzing a skill directory to produce a structured component map for an inconsistency audit.

A "skill" may contain multiple sub-skills that collaborate together. Your job is to understand the full structure: what each file is, how components relate to each other, and how sub-skills interact.

## File contents

{file_contents}

## Round 1 role guesses (use as hints, not ground truth)

{round1_guesses}

## Instructions

Produce a complete SkillMap as JSON. Specifically:

1. **components**: For each logical unit of content, create a component entry. One file can produce multiple components (e.g. a .md file containing both a description section and an embedded parameter table).

2. **sub_skills**: List all distinct sub-skill names mentioned or implemented in this directory.

3. **sub_skill_relations**: For each documented collaboration flow between sub-skills (A feeds into B, B depends on A, etc.), record the relationship. Extract these from the natural language descriptions.

4. **entry_functions**: For each implementation file, identify the main entry point function if discernible.

5. **comprehension_notes**: Write a short paragraph summarizing the overall skill structure, its purpose, and any ambiguities you noticed.

Respond with ONLY valid JSON in this exact format:
```json
{
  "components": [
    {
      "component_id": "c1",
      "component_type": "description | parameter_schema | implementation | dependency_ref | config | test | unknown",
      "source_file": "relative/path",
      "source_span": [start_line, end_line],
      "content_summary": "brief summary of what this component contains",
      "linked_components": ["c2"]
    }
  ],
  "sub_skills": ["skill_a", "skill_b"],
  "sub_skill_relations": [
    {
      "from_skill": "skill_a",
      "to_skill": "skill_b",
      "relation_type": "feeds_into | depends_on | parallel",
      "description": "skill_a output is used as input to skill_b"
    }
  ],
  "entry_functions": {
    "relative/path/impl.py": "function_name"
  },
  "comprehension_notes": "..."
}
```
