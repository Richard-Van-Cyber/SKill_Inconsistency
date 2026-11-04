from dataclasses import dataclass, field
from typing import Optional
from models.skill_map import SkillMap
from models.finding import Finding


@dataclass
class CodeFacts:
    """Structured summary of code extracted by code_parser. Shared with all LLM checkers."""
    functions: list[dict]       # [{name, params: [{name, type, default, required}], return_type, decorators}]
    raises: list[str]           # exception type names found in raise statements
    http_urls: list[str]        # string literals passed to http calls
    has_file_write: bool
    has_global_mutation: bool
    imports: list[str]          # top-level imported module names
    entry_function: Optional[str]  # best guess at the main entry point function name
    module_entry_calls: list[str] = field(default_factory=list)  # calls under `if __name__ == "__main__"`


@dataclass
class PreflightData:
    skill_map: SkillMap
    code_facts: CodeFacts
    hard_findings: list[Finding] = field(default_factory=list)
    schema_diff_summary: str = ""   # structured diff from schema_comparator, injected into LLM prompts
