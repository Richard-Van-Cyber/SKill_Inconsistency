#!/usr/bin/env python3
"""Mechanical proof: the skill's "Peak normalization" recipe is a constant gain.

ffmpeg-audio-processing/SKILL.md, verbatim:

    # Peak normalization
    ffmpeg -i input.mp4 -af "volumedetect" -f null -
    # Then use the detected peak to normalize
    ffmpeg -i input.mp4 -af "volume=0.5" output.mp4

The comment says the gain should come from the detected peak, but the command
hardcodes volume=0.5. The two steps are independent: nothing carries the
measured peak into the second command.
"""
import math
import re

SKILL = ('tasks/multilingual-video-dubbing/environment/skills/'
         'ffmpeg-audio-processing/SKILL.md')
text = open(SKILL, encoding='utf-8').read()
sec = re.search(r'#+ *Peak normalization(.*?)(?=\n#+ |\Z)', text, re.S | re.I)
print("=== the recipe exactly as SKILL.md ships it ===")
print(sec.group(1).strip()[:600])
print()

gain_db = 20 * math.log10(0.5)
print(f"volume=0.5  ==  {gain_db:+.2f} dB  — a constant, independent of the input")
print()
print("target: ITU-R BS.1770-4 / verifier accepts measured LUFS in [-24.5, -21.5]")
print()
print("what the recipe achieves, for a range of source levels:")
print(f"  {'source LUFS':>12}{'after volume=0.5':>20}{'compliant?':>12}")
for src in (-14.0, -18.0, -23.0, -29.0, -35.0):
    out = src + gain_db
    ok = -24.5 <= out <= -21.5
    print(f"  {src:>12.1f}{out:>20.2f}{'yes' if ok else 'NO':>12}")
print()
print("-> the recipe is compliant only when the source happens to sit near -17 LUFS.")
print("   A peak-driven gain (target - (measured peak)) lands on -23 for any source.")
