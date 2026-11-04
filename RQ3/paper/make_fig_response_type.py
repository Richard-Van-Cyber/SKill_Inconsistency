#!/usr/bin/env python3
"""RQ3.2 figure: response composition by inconsistency type and model.
Three panels, bars normalised to 100% so the shares are read directly."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({'font.family': 'serif', 'font.size': 7.5,
                     'axes.linewidth': 0.6, 'xtick.major.width': 0.6, 'ytick.major.width': 0.6})

TYPES = ['over-promised', 'cross-doc\nprocess', 'interface\ncontract',
         'env. fact\nconflict', 'shared concept\ndef.']
MODELS = ['Claude Haiku 4.5', 'Qwen3.6-35B', 'DeepSeek-V4-Flash']
DATA = {
 'DeepSeek-V4-Flash': {'Follow':[8,5,0,3,0],  'Recover':[20,12,8,8,9], 'BothFail':[3,4,5,4,3], 'Other':[5,0,2,0,0]},
 'Claude Haiku 4.5':  {'Follow':[18,7,3,6,4], 'Recover':[12,5,5,1,5], 'BothFail':[5,8,5,8,2], 'Other':[1,1,2,0,1]},
 'Qwen3.6-35B':       {'Follow':[15,6,3,4,1], 'Recover':[9,6,0,2,8],  'BothFail':[9,9,8,9,3], 'Other':[3,0,4,0,0]},
}
COL = {'Follow': '#b2182b', 'Recover': '#aed581', 'BothFail': '#999999', 'Other': '#e0e0e0'}
LBL = {'Follow': 'Follow', 'Recover': 'Recover', 'BothFail': 'BothFail (control)', 'Other': 'Other'}

fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.75), sharey=True)
y = np.arange(len(TYPES))[::-1]
for ax, model in zip(axes, MODELS):
    d = DATA[model]
    tot = np.array(d['Follow']) + np.array(d['Recover']) + np.array(d['BothFail']) + np.array(d['Other'])
    pct = {k: np.array(v) / tot * 100 for k, v in d.items()}
    left = np.zeros(len(TYPES))
    for k in ['Follow', 'Recover', 'BothFail', 'Other']:
        ax.barh(y, pct[k], left=left, height=0.66, color=COL[k], label=LBL[k],
                edgecolor='white', linewidth=0.5)
        for yi, (v, l) in enumerate(zip(pct[k], left)):
            if v >= 13:
                col = '#2e4a12' if k == 'Recover' else ('white' if k in ('Follow', 'BothFail') else '#555555')
                ax.text(l + v / 2, y[yi], '%.0f' % v, ha='center', va='center', fontsize=6, color=col)
        left += pct[k]
    for yi, t in zip(y, tot):
        ax.text(102, yi, 'n=%d' % t, va='center', ha='left', fontsize=6, color='#444444')
    ax.set_xlim(0, 128); ax.set_xticks([0, 50, 100])
    ax.set_title(model, fontsize=7.5, pad=3)
    ax.spines[['top', 'right']].set_visible(False)
    ax.tick_params(axis='y', length=0)
    ax.set_axisbelow(True)
axes[0].set_yticks(y); axes[0].set_yticklabels(TYPES, fontsize=7)
axes[1].set_xlabel('share of trials', fontsize=7.5)
h, l = axes[0].get_legend_handles_labels()
fig.legend(h, l, loc='upper center', bbox_to_anchor=(0.5, 1.16), ncol=4, frameon=False,
           fontsize=7.5, handlelength=1.1, handleheight=0.8, columnspacing=1.5)
plt.tight_layout(rect=(0, 0, 1, 0.94))
plt.savefig('RQ3/paper/fig-response-type.png', dpi=400, bbox_inches='tight')
plt.savefig('RQ3/paper/fig-response-type.pdf', bbox_inches='tight')
print('wrote fig-response-type.png + .pdf')
