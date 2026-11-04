#!/usr/bin/env python3
"""Anti-hardcoding probe B: prints a plausible Ask-Echo report without ever calling the
service. It looks right against the payloads shipped in the workspace but can never match the
held-out fixtures, so it must not reach 1.0."""
import sys

TITLES = [
    ("北京故宫博物院参观指南（含预约入口）", "故宫博物院官网", "https://www.dpm.org.cn/visit.html",
     "旺季 60 元、淡季 40 元，周一闭馆（法定节假日除外），需提前 7 天实名预约。",
     "故宫博物院实行实名预约参观制，观众须通过官方渠道提前预约。"),
    ("故宫门票预约攻略 2026", "马蜂窝",
     "https://www.mafengwo.cn/gonglve/ziyouxing/1234567.html",
     "预约放票时间为参观日前 7 天的 20:00，退票会在参观日前一天 20:00 前释放。", None),
    ("故宫周边一日游路线", "知乎专栏", "https://zhuanlan.zhihu.com/p/998877665",
     "景山公园万春亭是拍摄故宫全景的最佳机位，日落前 40 分钟到达最合适。",
     "上午 8:30 入院，先走中轴线，午后转西路慈宁宫、寿康宫。"),
    ("故宫文创店铺盘点", "小红书", "https://www.xiaohongshu.com/explore/abcdef0123456789",
     "角楼咖啡与故宫文具是最受欢迎的伴手礼，神武门外东侧店铺排队最短。", None),
    ("故宫博物院 2026 年展览计划公布", "人民网",
     "http://culture.people.com.cn/n1/2026/0105/c1013-40000001.html",
     "全年将推出 8 个特展，其中「陶瓷馆」常设展完成改陈后重新开放。",
     "故宫博物院公布 2026 年度展览计划，全年推出 8 个特展。"),
]

query = sys.argv[1] if len(sys.argv) > 1 else "故宫"
want_content = "--need-content" in sys.argv

out = []
out.append("=== LLM Summary ===\n\n根据搜索结果，故宫参观需要注意三点：必须提前实名预约；每周一闭馆；"
           "建议从午门入院。\n")
shown = [t for t in TITLES if (t[4] or not want_content)]
out.append("=== Search Results (%d items) ===\n" % len(shown))
for index, (title, site, url, snippet, content) in enumerate(shown, 1):
    out.append("\n[%d] %s" % (index, title))
    out.append("    Site: %s" % site)
    out.append("    URL: %s" % url)
    out.append("    Published: 2026-01-08T09:20:00+08:00")
    out.append("    Authority: 正常权威 (Level: 2)")
    out.append("\n    Snippet:")
    out.append("    %s" % snippet)
    if content:
        out.append("\n    Content: %s" % content)
out.append("\n=== Search Info ===")
out.append("  Query: %s" % query)
out.append("  Type: web_summary")
out.append("  Time Cost: 372 ms")
out.append("  Log ID: 20260108102030A1B2C3D4E5F60718")
out.append("\n=== Token Usage ===")
out.append("  Prompt tokens: 11468")
out.append("  Completion tokens: 94")
out.append("  Total tokens: 11562")
out.append("  Search time: 120 ms")
out.append("  First token time: 150 ms")
out.append("  Total time: 270 ms")
print("\n".join(out))
