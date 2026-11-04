#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the shipped sample payloads for the ask-echo-client workspace (authoring tool)."""
import json
from pathlib import Path

OUT = Path("/workspace/skillEvaluation/wildskills/dynamic_eval/tasks/"
           "ask-echo-client/environment/workspace/tools/sample_payloads")


def item(title, site, url, published, snippet, content):
    entry = {"Title": title, "SiteName": site, "Url": url, "PublishTime": published,
             "AuthInfoDes": "正常权威", "AuthInfoLevel": 2, "Snippet": snippet}
    if content:
        entry["Content"] = content
    return entry


def envelope(count, results, time_cost, log_id, query, search_type, extra=None):
    payload = {"ResultCount": count, "WebResults": results, "TimeCost": time_cost,
               "LogId": log_id, "SearchContext": {"OriginQuery": query,
                                                  "SearchType": search_type}}
    payload.update(extra or {})
    return {"Result": payload, "ResponseMetadata": {"RequestId": log_id, "Service": "ask-echo"}}


def summary_choice(text):
    return [{"Index": 0, "FinishReason": "stop",
             "Message": {"Role": "assistant", "content": text}}]


def usage(prompt, completion, search, first_token, total):
    return {"PromptTokens": prompt, "CompletionTokens": completion,
            "TotalTokens": prompt + completion, "SearchTimeCost": search,
            "FirstTokenTimeCost": first_token, "TotalTimeCost": total}


MIXED = [
    item("北京故宫博物院参观指南（含预约入口）", "故宫博物院官网",
         "https://www.dpm.org.cn/visit.html", "2026-01-08T09:20:00+08:00",
         "旺季 60 元、淡季 40 元，周一闭馆（法定节假日除外），需提前 7 天实名预约。",
         "故宫博物院实行实名预约参观制，观众须通过官方渠道提前预约。旺季（4 月 1 日—10 月 31 日）"
         "开放时间为 8:30—17:00，淡季 8:30—16:30。除法定节假日外，每周一闭馆。建议从午门入院，"
         "沿中轴线参观三大殿，再由神武门出园。珍宝馆与钟表馆需另行购票。"),
    item("故宫门票预约攻略 2026", "马蜂窝",
         "https://www.mafengwo.cn/gonglve/ziyouxing/1234567.html", "2026-01-06T18:02:00+08:00",
         "预约放票时间为参观日前 7 天的 20:00，退票会在参观日前一天 20:00 前释放。",
         None),
    item("故宫周边一日游路线", "知乎专栏",
         "https://zhuanlan.zhihu.com/p/998877665", "2026-01-02T11:41:00+08:00",
         "景山公园万春亭是拍摄故宫全景的最佳机位，日落前 40 分钟到达最合适。",
         "上午 8:30 入院，先走中轴线，午后转西路慈宁宫、寿康宫，15:00 出神武门，对面即是景山公园。"
         "登万春亭俯瞰整个紫禁城，随后步行至北海公园。"),
    item("故宫文创店铺盘点", "小红书",
         "https://www.xiaohongshu.com/explore/abcdef0123456789", "2025-12-28T21:15:00+08:00",
         "角楼咖啡与故宫文具是最受欢迎的伴手礼，神武门外东侧店铺排队最短。",
         None),
    item("故宫博物院 2026 年展览计划公布", "人民网",
         "http://culture.people.com.cn/n1/2026/0105/c1013-40000001.html",
         "2026-01-05T08:00:00+08:00",
         "全年将推出 8 个特展，其中「陶瓷馆」常设展完成改陈后重新开放。",
         "故宫博物院公布 2026 年度展览计划，全年推出 8 个特展，涵盖书画、陶瓷、钟表、"
         "宗教艺术等门类，陶瓷馆常设展完成改陈后重新开放。"),
]

TRAVEL = [
    item("北京五日游攻略及路线，五天四晚大概多少钱", "搜狐网",
         "https://m.sohu.com/a/905840001_122260725/", "2026-01-07T15:10:00+08:00",
         "北京旅游必打卡景点：故宫、八达岭长城、颐和园、天坛、南锣鼓巷。",
         "第一天抵达后入住前门附近的酒店，晚上逛大栅栏；第二天故宫—景山—北海；"
         "第三天八达岭长城—奥林匹克公园；第四天颐和园—圆明园；第五天南锣鼓巷—什刹海返程。"),
    item("北京旅游攻略：第一次来北京怎么玩", "马蜂窝",
         "https://www.mafengwo.cn/gonglve/ziyouxing/2000001.html", "2026-01-03T10:05:00+08:00",
         "地铁 1 号线串联故宫、天安门、王府井，是性价比最高的出行方式。",
         None),
    item("北京秋季最佳赏叶路线", "携程攻略",
         "https://you.ctrip.com/travels/beijing1/3900001.html", "2025-11-02T09:30:00+08:00",
         "香山、坡峰岭、慕田峪长城三条路线，10 月下旬进入最佳观赏期。",
         "香山公园红叶节期间需预约，坡峰岭人少景美，慕田峪长城可同时看红叶与长城。"),
    item("北京亲子游五天行程安排", "去哪儿攻略",
         "https://travel.qunar.com/p-oi8000001-beijing", "2025-12-19T16:48:00+08:00",
         "中国科学技术馆、北京动物园、天文馆适合 5—10 岁儿童。",
         "第一天中国科学技术馆；第二天北京动物园；第三天天文馆与古观象台；"
         "第四天故宫亲子路线；第五天奥林匹克森林公园。"),
    item("北京冬季旅游注意事项", "百度百科",
         "https://baike.baidu.com/item/北京旅游/1000001", "2025-12-01T07:12:00+08:00",
         "1 月平均气温 -6℃，需备羽绒服、暖宝宝与防风手套。",
         None),
]

DEEP = [
    item("深度学习教程：从感知机到 Transformer", "CSDN",
         "https://blog.csdn.net/deeplearning/article/details/140000001",
         "2026-01-04T13:20:00+08:00",
         "配套 PyTorch 代码，覆盖反向传播、CNN、RNN 与注意力机制。",
         "本教程从感知机讲起，逐步推导反向传播，再引入卷积网络、循环网络与注意力机制，"
         "最后用 PyTorch 实现一个迷你 Transformer 并训练字符级语言模型。"),
    item("动手学深度学习（第二版）在线版", "动手学深度学习",
         "https://zh.d2l.ai/", "2025-10-11T00:00:00+08:00",
         "李沐团队维护的开源教材，含可运行 Notebook。",
         "全书包含线性回归、多层感知机、卷积神经网络、循环神经网络、注意力机制与优化算法，"
         "每章都提供 Jupyter Notebook 与 Colab 链接。"),
    item("零基础入门深度学习需要哪些数学基础", "知乎",
         "https://www.zhihu.com/question/300000001", "2025-09-22T20:31:00+08:00",
         "线性代数、概率论与微积分是必需的，凸优化可以边学边补。",
         None),
    item("PyTorch 官方教程中文版", "PyTorch",
         "https://pytorch.org/tutorials/", "2025-12-30T00:00:00+08:00",
         "60 分钟闪电战、张量、自动求导、神经网络、训练分类器。",
         "官方教程以 60 分钟闪电战开篇，随后讲解张量操作、自动求导机制、torch.nn 模块、"
         "图像分类器训练与数据并行。"),
    item("深度学习模型部署实践", "InfoQ",
         "https://www.infoq.cn/article/deep-learning-serving", "2025-11-18T09:00:00+08:00",
         "ONNX Runtime、TensorRT 与 Triton Inference Server 的对比与选型。",
         None),
]

IMAGES = [
    {"Title": "故宫博物院", "SiteName": "百度图片",
     "Url": "https://example.com/images/gugong-1.jpg", "PublishTime": "2025-10-01T00:00:00+08:00",
     "Image": {"Url": "https://example.com/images/gugong-1.jpg", "Width": 1920, "Height": 1080,
               "Shape": "横长方形"}},
    {"Title": "故宫角楼雪景", "SiteName": "必应图片",
     "Url": "https://example.com/images/gugong-2.jpg", "PublishTime": "2025-12-20T00:00:00+08:00",
     "Image": {"Url": "https://example.com/images/gugong-2.jpg", "Width": 1080, "Height": 1920,
               "Shape": "竖长方形"}},
]

UNKNOWN = [
    item("离线桩默认结果", "example.invalid", "https://example.invalid/default",
         "2026-01-01T00:00:00+08:00", "没有为这个查询单独准备夹具。", "默认正文。"),
]

SUMMARY_TEXT = (
    "根据搜索结果，故宫参观需要注意三点：\n\n"
    "1. 必须提前实名预约，旺季放票时间为参观日前 7 天的 20:00；\n"
    "2. 除法定节假日外每周一闭馆，旺季 8:30 开馆、17:00 停止入院；\n"
    "3. 珍宝馆与钟表馆需另行购票，建议从午门入院、神武门出园。"
)

PAYLOADS = {
    "故宫": envelope(5, MIXED, 372, "20260108102030A1B2C3D4E5F60718", "故宫", "web"),
    "北京旅游攻略": envelope(5, TRAVEL, 512, "20260107151005B2C3D4E5F60718293A", "北京旅游攻略",
                             "web_summary",
                             {"Choices": summary_choice(SUMMARY_TEXT),
                              "Usage": usage(11468, 94, 120, 150, 270)}),
    "深度学习教程": envelope(5, DEEP, 268, "20260104132011C3D4E5F60718293A4B", "深度学习教程", "web"),
    "故宫图片": envelope(2, [], 143, "20260108102319D4E5F60718293A4B5C", "故宫图片", "image",
                         {"ImageResults": IMAGES, "WebResults": []}),
    "__default__": envelope(1, UNKNOWN, 1, "MOCK-DEFAULT-0000", "", "web"),
}

INDEX = {query: payload for query, payload in PAYLOADS.items() if query != "__default__"}
STANDALONE = {"故宫图片": PAYLOADS["故宫图片"]}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "Responses.json").write_text(
        json.dumps(INDEX, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, payload in STANDALONE.items():
        (OUT / ("%s.json" % name)).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote Responses.json with %d queries and %d standalone samples to %s"
          % (len(INDEX), len(STANDALONE), OUT))
