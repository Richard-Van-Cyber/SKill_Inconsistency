# 05 · 固定增益冒充归一化（fixed gain masquerading as normalization）

**目标不一致性**：`multilingual-video-dubbing` 的 `ffmpeg-audio-processing/SKILL.md`
「Peak normalization」一节：

```bash
# Peak normalization
ffmpeg -i input.mp4 -af "volumedetect" -f null -
# Then use the detected peak to normalize
ffmpeg -i input.mp4 -af "volume=0.5" output.mp4
```

注释说增益应当由**探测到的峰值**决定，命令却写死 `volume=0.5`。
两步之间没有任何数据传递 —— 第一步的结果从未进入第二步。

## 为什么它在 P7 下先验高

触发点就在 **agent 会照抄的那条命令**里，而且**正好落在任务的关键路径上**：

task.md 的要求 #1 就是
> "It should followed the ITU-R BS.1770-4 standard"

verifier（`verifier/test_outputs.py:55-63`）：
```python
# 4. Loudness compliance (-23 LUFS ±1.5)
matches = re.findall(r"I:\s+(-?\d+\.?\d*)\s+LUFS", res.stderr)
assert -24.5 <= measured_lufs <= -21.5
```

## 机械证明（0 次模型调用）

`builder/prove_fixed_gain.py` 直接从真实 `SKILL.md` 抽出该节，并计算：

```
volume=0.5  ==  -6.02 dB  —— 常数，与输入无关

  source LUFS    after volume=0.5    compliant?
        -14.0              -20.02          NO
        -18.0              -24.02         yes
        -23.0              -29.02          NO
        -29.0              -35.02          NO
        -35.0              -41.02          NO
```

**只有当源音频恰好落在 -17 LUFS 附近时这条配方才合规**，而源音频是 TTS 引擎的输出，
电平不由 agent 也不由我控制。峰值驱动的增益（`target - measured_peak`）则对任何源都能落到 -23。

## 三个必要条件

| 条件 | 本案例 |
|---|---|
| **C1 数据依赖** | 只有当源电平恰好使 `-6 dB` 落到 [-24.5, -21.5] 时才"侥幸合规" |
| **C2 静默** | ffmpeg 正常退出、音频正常生成，只是响度不对；没有任何报错 |
| **C3 不可探知** | 注释与命令互相矛盾，agent 无法从命令本身判断 `0.5` 是占位符还是真值 |

## 与 02 号的对比

| | 02 grid Type-1 | 05 本案例 |
|---|---|---|
| 不一致性所在 | 参考文档的**能力声明** | `SKILL.md` 的**可复制命令** |
| 评分器是否也错 | **是**（同样忽略 MODEL 列） | 否（verifier 的 -23 LUFS 是对的） |
| 修复方向 | 只能对齐评分器（P6 反向风险） | 正常修复即可 |

## 状态

- 机械证明：**已完成**（本目录 `evidence/prove_output.txt`）
- 配对 agent 实验：**未执行**。镜像需要从零构建（Dockerfile 含 CPU 版 Torch + pyopenjtalk 编译），
  成本显著高于前三个案例；本轮先保留构造与证明，实验留待后续轮次。

## 文件

| 文件 | 内容 |
|---|---|
| `ffmpeg-audio-processing.SKILL.md` | 原始技能文档（含该配方） |
| `builder/prove_fixed_gain.py` | 机械证明（**决定性证据**） |
| `evidence/prove_output.txt` | 证明输出存档 |
