#!/usr/bin/env python3
"""Exposure: distinguish *content access* to a skill from merely *listing* the skills directory.

listing  = ls / find / tree / du on a skills path
content  = Read|cat|head|tail|grep|sed|awk|python on a concrete file under skills/, or the Skill tool
"""
import csv, json, os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_v3 as A

LISTING = re.compile(r'\b(ls|find|tree|du)\b')
CONCRETE = re.compile(r'/(?:app|home/agent/\.claude|root/\.claude)/skills/[^\s"\']+\.\w+')

rows = list(csv.DictReader(open(A.MANIFEST)))
idx = A.build_index(rows, principled=True)
stats = collections.Counter()
by_model = collections.defaultdict(collections.Counter)

for k, cell in idx.items():
    if k[2] != 'OriginalSkill' or not os.path.exists(cell + 'cli.stdout.jsonl'):
        continue
    axis = k[0]
    turns = A.parse(cell)
    reads_any = [t for t in turns if A.SKILL_PATH.search(t['arg'])
                 or (t['tool'] == 'Skill' and 'skill' in t['arg'].lower())]
    reads_strict = [t for t in turns if (t['tool'] == 'Skill' and 'skill' in t['arg'].lower())
                    or CONCRETE.search(t['arg'])]
    listing_only = bool(reads_any) and not bool(reads_strict)
    stats['any'] += 1 if reads_any else 0
    stats['strict'] += 1 if reads_strict else 0
    stats['listing_only'] += 1 if listing_only else 0
    by_model[axis]['any'] += 1 if reads_any else 0
    by_model[axis]['strict'] += 1 if reads_strict else 0

n = sum(1 for k in idx if k[2] == 'OriginalSkill')
print('OriginalSkill runs:', n)
print('  exposed  (any path match or Skill tool): %d  (%.1f%%)' % (stats['any'], 100*stats['any']/n))
print('  exposed  (content access or Skill tool): %d  (%.1f%%)' % (stats['strict'], 100*stats['strict']/n))
print('  listing-only (ls/find the skills dir, never read a file): %d' % stats['listing_only'])
print()
print('  per model  any / strict')
for ax in ('haiku', 'deepseek', 'qwen'):
    print('    %-9s %d / %d' % (ax, by_model[ax]['any'], by_model[ax]['strict']))
