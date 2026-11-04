#!/usr/bin/env python3
"""Build the adversarial offer-letter template.

Shipped: {{IF_RELOCATION}} ... {{END_IF_RELOCATION}} both live inside ONE
paragraph, so the same-paragraph loop the skill doc gives

    for para in doc.paragraphs:
        text = para.text
        if start_marker in text and end_marker in text:   # <-- same paragraph only
            ...

works, and the missing block-level handling stays dormant.

Adversarial: move the block's second half into its own paragraph, so the two
markers sit in DIFFERENT paragraphs. The conditional content is unchanged
({{RELOCATION_AMOUNT}} and {{RELOCATION_DAYS}} both remain, as the verifier
requires) and every run here carries no rPr, so formatting is preserved. A
correct block-level implementation emits an equivalent letter; a solution that
copies the doc's same-paragraph loop leaves both markers behind and fails
test_conditional_section.
"""
import re
import zipfile

SRC = 'tasks/offer-letter-generator/environment/offer_letter_template.docx'
DST = 'adv/02-offer-letter-generator/data/offer_letter_template.adv.docx'

zin = zipfile.ZipFile(SRC)
xml = zin.read('word/document.xml').decode('utf-8')
paras = re.findall(r'<w:p[ >].*?</w:p>', xml, re.S)
target = next(p for p in paras if '{{IF_RELOCATION}}' in p and '{{END_IF_RELOCATION}}' in p)

runs = re.findall(r'<w:r>.*?</w:r>', target, re.S)
assert len(runs) == 4, 'unexpected run count %d' % len(runs)
assert all('<w:rPr>' not in r for r in runs), 'runs carry formatting; split would lose it'
tail_runs = ''.join(runs[2:])
head_para = target.replace(tail_runs, '')
assert '{{IF_RELOCATION}}' in head_para and '{{END_IF_RELOCATION}}' not in head_para

ppr = re.search(r'<w:pPr>.*?</w:pPr>', target, re.S)
tail_para = '<w:p>' + (ppr.group(0) if ppr else '') + tail_runs + '</w:p>'

adv_xml = xml.replace(target, head_para + tail_para, 1)

with zipfile.ZipFile(DST, 'w', zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename == 'word/document.xml':
            data = adv_xml.encode('utf-8')
        zout.writestr(item, data)
print('wrote', DST)

for label, path in (('SHIPPED', SRC), ('ADVERSARIAL', DST)):
    x = zipfile.ZipFile(path).read('word/document.xml').decode('utf-8')
    print('--- ' + label)
    for i, p in enumerate(re.findall(r'<w:p[ >].*?</w:p>', x, re.S)):
        t = ''.join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>', p))
        if 'IF_RELOCATION' in t or 'RELOCATION_DAYS' in t:
            print('  [%2d] %r' % (i, t))
