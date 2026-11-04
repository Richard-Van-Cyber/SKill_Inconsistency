You are analyzing a skill directory to determine which files need to be fully read for a thorough inconsistency audit.

A "skill" is a unit of AI agent capability. It may contain one or more sub-skills that collaborate together. Each skill directory may contain:
- Natural language description documents (what the skill does, parameters, usage)
- Parameter/return value schema definitions
- Implementation code
- Configuration files
- Dependency declarations
- Test files
- Any combination of the above in non-standard formats and filenames

Below is the directory listing with metadata for each file. Your job is to decide which files must be read in full to understand the skill's contract (what it promises) and implementation (what it does).

## Directory listing

{file_listing}

## Instructions

For each file that should be read in full, output a JSON entry with:
- `path`: the relative file path
- `suspected_role`: one of: description | parameter_schema | implementation | dependency_ref | config | test | unknown
- `reason`: brief reason why this file is important to read

Prioritize files that likely contain:
1. Natural language descriptions of what the skill does
2. Parameter and return value definitions (any format: JSON Schema, YAML, inline docs, etc.)
3. Implementation code (main entry points)
4. Sub-skill collaboration descriptions

Skip obvious non-content files (lock files, binary assets, compiled artifacts).

Respond with ONLY valid JSON in this exact format:
```json
{
  "files_to_read": [
    {
      "path": "relative/path",
      "suspected_role": "description",
      "reason": "..."
    }
  ]
}
```
