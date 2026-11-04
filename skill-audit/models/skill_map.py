from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FileEntry:
    path: str           # relative to skill root
    extension: str
    size_bytes: int
    first_lines: str    # first 3 lines concatenated


@dataclass
class Component:
    component_id: str
    component_type: str  # description | parameter_schema | implementation | dependency_ref | config | test | unknown
    source_file: str     # relative to skill root
    source_span: Optional[tuple[int, int]]  # (line_start, line_end), None if whole file
    content: str
    linked_components: list[str] = field(default_factory=list)  # component_ids


@dataclass
class SubSkillRelation:
    from_skill: str     # sub-skill name
    to_skill: str       # sub-skill name
    relation_type: str  # "feeds_into" | "depends_on" | "parallel"
    description: str    # extracted from doc


@dataclass
class SkillMap:
    skill_root: str
    all_files: list[FileEntry]
    files_read: list[str]           # paths of files loaded in Round2
    components: list[Component]
    sub_skills: list[str]           # sub-skill names identified in this directory
    sub_skill_relations: list[SubSkillRelation]
    comprehension_notes: str        # LLM's free-text notes about the skill structure
