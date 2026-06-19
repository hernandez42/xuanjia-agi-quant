#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
消息面自动匹配模块 — 接入快兰斯实时财经快讯
═══════════════════════════════════════════════════════════════════════════════
功能：
1. 从快兰斯(m.financebe.com)实时获取财经快讯
2. NLP关键词匹配：自动识别消息对行业/板块/个股的影响
3. 生成消息面情绪评分，自动注入到96因子模型的舆情因子中
4. 输出消息面分析报告

数据接口：
  GET http://m.fbecn.com/24h/news_fbe0406.json?newsid=0
  返回: {"list": [{"newsID", "time", "content", "Level", "Type", "Keywords"}]}
═══════════════════════════════════════════════════════════════════════════════
"""

import json
import urllib.request
import re
import sys
import os
from datetime import datetime
from collections import defaultdict

# ==============================================================================
# 行业-关键词映射表
# ==============================================================================
SECTOR_KEYWORDS = {
    "半导体": {
        "positive": ["芯片", "半导体", "晶圆", "光刻", "封装", "集成电路", "中芯", "华虹",
                      "英伟达", "台积电", "ASML", "氮化镓", "碳化硅", "GaN", "SiC", "国产替代"],
        "negative": ["制裁", "断供", "禁令", "出口管制", "实体清单", "关税", "专利侵权"],
    },
    "新能源": {
        "positive": ["光伏", "太阳能", "钙钛矿", "风电", "储能", "电池", "锂电", "新能源车",
                      "充电桩", "氢能", "叠层电池", "碳中和", "绿电"],
        "negative": ["产能过剩", "反补贴", "反倾销", "欧盟关税", "补贴退坡", "降价"],
    },
    "医药生物": {
        "positive": ["创新药", "临床", "FDA", "NDA", "IND", "生物药", "基因治疗", "疫苗",
                      "获批", "上市", "疗效", "医保谈判"],
        "negative": ["集采", "降价", "不良反应", "召回", "临床失败", "专利到期", "制裁"],
    },
    "消费": {
        "positive": ["消费复苏", "零售", "餐饮", "旅游", "白酒", "免税", "消费升级",
                      "双十一", "春节", "促消费"],
        "negative": ["消费降级", "库存", "关店", "业绩下滑", "价格战"],
    },
    "金融": {
        "positive": ["降息", "降准", "宽松", "放水", "LPR下调", "社融超预期", "信贷",
                      "牛市", "资金流入", "北向资金", "外资"],
        "negative": ["加息", "收紧", "缩表", "去杠杆", "违约", "暴雷", "退市",
                      "监管", "罚款", "立案"],
    },
    "房地产": {
        "positive": ["楼市回暖", "销售增长", "房价上涨", "保交楼", "放松限购", "降首付",
                      "城中村", "地产股"],
        "negative": ["暴雷", "违约", "烂尾", "降价", "库存高企", "销售下滑"],
    },
    "科技AI": {
        "positive": ["AI", "人工智能", "大模型", "算力", "数据中心", "云计算", "机器人",
                      "自动驾驶", "华为", "苹果", "OpenAI", "英伟达", "数字经济",
                      "数据要素", "5G", "6G", "量子计算"],
        "negative": ["AI监管", "数据安全", "隐私", "垄断", "封杀"],
    },
    "有色金属": {
        "positive": ["稀土", "锂", "钴", "镍", "铜", "铝", "黄金", "白银", "涨价",
                      "供给收缩", "需求增长"],
        "negative": ["跌价", "供给过剩", "库存增加", "进口增加"],
    },
    "石油石化": {
        "positive": ["油价上涨", "OPEC减产", "天然气", "能源安全", "页岩油"],
        "negative": ["油价下跌", "需求疲软", "库存增加", "OPEC增产"],
    },
    "汽车": {
        "positive": ["销量增长", "新能源车", "智能驾驶", "出口", "比亚迪", "特斯拉",
                      "自动驾驶", "固态电池"],
        "negative": ["销量下滑", "价格战", "召回", "补贴退坡", "关税"],
    },
    "电力设备": {
        "positive": ["电网", "特高压", "变压器", "配电", "电力投资", "新能源装机",
                      "储能", "充电桩"],
        "negative": ["弃风弃光", "电网故障", "检修", "停电"],
    },
}

# 个股关键词映射
STOCK_KEYWORDS = {
    "中芯国际": ["中芯", "SMIC", "晶圆代工"],
    "比亚迪": ["比亚迪", "BYD", "新能源车", "刀片电池"],
    "宁德时代": ["宁德时代", "CATL", "动力电池", "储能"],
    "北方稀土": ["北方稀土", "稀土", "轻稀土"],
    "贵州茅台": ["茅台", "白酒", "高端白酒"],
    "药明康德": ["药明", "CXO", "生物药外包"],
    "中国石化": ["中国石化", "中石化", "石化", "成品油"],
    "中微公司": ["中微", "刻蚀", "半导体设备"],
    "金山办公": ["金山办公", "WPS", "信创", "办公软件"],
    "科大讯飞": ["科大讯飞", "语音", "AI", "大模型"],
    "通威股份": ["通威", "光伏", "硅料", "水产"],
    "掌阅科技": ["掌阅", "阅读", "数字阅读", "AI阅读"],
    "英诺赛科": ["英诺赛科", "氮化镓", "GaN"],
    "荣耀": ["荣耀", "Honor", "手机"],
    "中国电建": ["中国电建", "水电", "基建"],
    "永福股份": ["永福股份", "储能", "光储"],
}

# 宏观情绪关键词
MACRO_SENTIMENT = {
    "positive": ["降息", "降准", "宽松", "刺激", "利好", "超预期", "增长", "复苏",
                  "突破", "创新高", "大涨", "涨停", "资金流入", "外资买入",
                  "中美合作", "经贸合作", "签约", "战略合作"],
    "negative": ["加息", "收紧", "制裁", "禁令", "暴跌", "大跌", "熔断", "跌停",
                  "违约", "暴雷", "退市", "立案", "调查", "罚款", "制裁",
                  "贸易战", "关税", "脱钩", "地缘冲突", "战争", "通胀"],
}

# ==============================================================================
# 消息面分析引擎
# ==============================================================================
class NewsSentimentEngine:
    """消息面情绪分析引擎 — 接入快兰斯实时快讯"""

    API_URL = "http://m.fbecn.com/24h/news_fbe0406.json?newsid=0"

    def __init__(self):
        self.news_cache = []
        self.sector_scores = defaultdict(lambda: {"positive": 0, "negative": 0, "neutral": 0, "signals": []})
        self.stock_scores = defaultdict(lambda: {"positive": 0, "negative": 0, "neutral": 0, "signals": []})
        self.macro_score = {"positive": 0, "negative": 0, "neutral": 0}

    def fetch_news(self):
        """从快兰斯获取最新快讯"""
        try:
            req = urllib.request.Request(
                self.API_URL,
                headers={"User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8-sig")
                data = json.loads(raw)
                self.news_cache = data.get("list", [])
                return self.news_cache
        except Exception as e:
            print(f"  [警告] 快兰斯数据获取失败: {e}")
            return []

    def analyze_news(self, news_list=None):
        """分析快讯对行业/个股/宏观的影响"""
        if news_list is None:
            news_list = self.news_cache

        for item in news_list:
            content = item.get("content", "")
            time_str = item.get("time", "")
            level = item.get("Level", "1")

            # 1. 行业分析
            for sector, keywords in SECTOR_KEYWORDS.items():
                pos_hits = [k for k in keywords["positive"] if k in content]
                neg_hits = [k for k in keywords["negative"] if k in content]
                if pos_hits or neg_hits:
                    if len(pos_hits) > len(neg_hits):
                        self.sector_scores[sector]["positive"] += 1
                        self.sector_scores[sector]["signals"].append(
                            {"time": time_str, "type": "positive", "keywords": pos_hits,
                             "summary": content[:60]})
                    elif len(neg_hits) > len(pos_hits):
                        self.sector_scores[sector]["negative"] += 1
                        self.sector_scores[sector]["signals"].append(
                            {"time": time_str, "type": "negative", "keywords": neg_hits,
                             "summary": content[:60]})
                    else:
                        self.sector_scores[sector]["neutral"] += 1

            # 2. 个股分析
            for stock, keywords in STOCK_KEYWORDS.items():
                hits = [k for k in keywords if k in content]
                if hits:
                    # 判断情绪方向
                    is_pos = any(k in MACRO_SENTIMENT["positive"] for k in content.split())
                    is_neg = any(k in MACRO_SENTIMENT["negative"] for k in content.split())
                    if is_pos and not is_neg:
                        self.stock_scores[stock]["positive"] += 1
                        self.stock_scores[stock]["signals"].append(
                            {"time": time_str, "type": "positive", "keywords": hits,
                             "summary": content[:60]})
                    elif is_neg and not is_pos:
                        self.stock_scores[stock]["negative"] += 1
                        self.stock_scores[stock]["signals"].append(
                            {"time": time_str, "type": "negative", "keywords": hits,
                             "summary": content[:60]})
                    else:
                        self.stock_scores[stock]["neutral"] += 1
                        self.stock_scores[stock]["signals"].append(
                            {"time": time_str, "type": "neutral", "keywords": hits,
                             "summary": content[:60]})

            # 3. 宏观情绪
            pos_hits = [k for k in MACRO_SENTIMENT["positive"] if k in content]
            neg_hits = [k for k in MACRO_SENTIMENT["negative"] if k in content]
            if pos_hits and not neg_hits:
                self.macro_score["positive"] += 1
            elif neg_hits and not pos_hits:
                self.macro_score["negative"] += 1

    def get_sector_sentiment(self, sector):
        """获取行业情绪评分 (-1.0 ~ +1.0)"""
        s = self.sector_scores[sector]
        total = s["positive"] + s["negative"] + s["neutral"]
        if total == 0:
            return 0.0
        return (s["positive"] - s["negative"]) / total

    def get_stock_sentiment(self, stock):
        """获取个股情绪评分 (-1.0 ~ +1.0)"""
        s = self.stock_scores[stock]
        total = s["positive"] + s["negative"] + s["neutral"]
        if total == 0:
            return 0.0
        return (s["positive"] - s["negative"]) / total

    def get_macro_sentiment(self):
        """获取宏观情绪评分 (-1.0 ~ +1.0)"""
        total = self.macro_score["positive"] + self.macro_score["negative"]
        if total == 0:
            return 0.0
        return (self.macro_score["positive"] - self.macro_score["negative"]) / total

    def generate_report(self):
        """生成消息面分析报告"""
        print("=" * 78)
        print("【消息面分析报告】快兰斯实时快讯 × 96因子模型")
        print("=" * 78)

        # 宏观情绪
        macro = self.get_macro_sentiment()
        macro_label = "积极" if macro > 0.2 else "谨慎" if macro < -0.2 else "中性"
        print(f"\n  ━━ 宏观情绪: {macro:+.2f} ({macro_label}) ━━")
        print(f"    正面信号: {self.macro_score['positive']} | 负面信号: {self.macro_score['negative']}")

        # 行业情绪
        print(f"\n  ━━ 行业情绪排名 ━━")
        sector_ranking = []
        for sector in self.sector_scores:
            score = self.get_sector_sentiment(sector)
            s = self.sector_scores[sector]
            total = s["positive"] + s["negative"] + s["neutral"]
            if total > 0:
                sector_ranking.append((sector, score, s["positive"], s["negative"], total))
        sector_ranking.sort(key=lambda x: x[1], reverse=True)

        for sector, score, pos, neg, total in sector_ranking:
            bar = "█" * int(abs(score) * 10)
            label = "+" if score > 0 else ""
            print(f"    {sector:<8} {label}{score:.2f} ({pos}正/{neg}负/{total}总) {bar}")

        # 个股信号
        print(f"\n  ━━ 个股信号 ━━")
        for stock in self.stock_scores:
            s = self.stock_scores[stock]
            total = s["positive"] + s["negative"] + s["neutral"]
            if total > 0:
                score = self.get_stock_sentiment(stock)
                print(f"    {stock:<10} 情绪: {score:+.2f} ({s['positive']}正/{s['negative']}负)")
                for sig in s["signals"][:3]:
                    print(f"      [{sig['time'][-8:-3]}] {sig['type']}: {sig['summary']}...")

        # 消息面与因子模型的对接建议
        print(f"\n  ━━ 因子模型注入建议 ━━")
        print(f"    news_sentiment_score → {macro:+.2f} (宏观)")
        print(f"    social_heat_anomaly → {len(self.news_cache)} 条快讯密度")
        print(f"    policy_signal → {macro:+.2f} (政策面)")
        print(f"    analyst_consensus_breakout → 基于行业情绪排名")

        return {
            "macro_sentiment": macro,
            "sector_sentiments": {s: self.get_sector_sentiment(s) for s in self.sector_scores},
            "stock_sentiments": {s: self.get_stock_sentiment(s) for s in self.stock_scores},
            "news_count": len(self.news_cache),
        }


# ==============================================================================
# 主流程
# ==============================================================================
if __name__ == "__main__":
    engine = NewsSentimentEngine()

    print("正在获取快兰斯实时快讯...")
    news = engine.fetch_news()
    print(f"获取到 {len(news)} 条快讯\n")

    if news:
        engine.analyze_news()
        result = engine.generate_report()

        # 保存结果
        output_path = "/workspace/xuanjia/apex_agi/news_sentiment_result.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n  结果已保存: {output_path}")
    else:
        print("未获取到快讯数据，使用模拟数据演示...")
        # 模拟数据演示
        demo_news = [
            {"content": "现货黄金跌破4150美元，日内下跌1.45%。", "time": "2026-06-19 12:00:04", "Level": "1"},
            {"content": "韩国KOSPI指数转跌，此前一度大涨3%。", "time": "2026-06-19 11:34:12", "Level": "1"},
            {"content": "中国驻美国大使谢锋会见维萨公司首席执行官麦凯恩，双方就加强中美经贸合作交换意见。", "time": "2026-06-19 11:18:18", "Level": "1"},
            {"content": "英诺赛科现有产品不受德国慕尼黑地区法院诉讼结果影响。", "time": "2026-06-19 10:57:52", "Level": "1"},
            {"content": "中澳校企合作开发无铟叠层光伏电池，光电转化效率超30%。", "time": "2026-06-19 09:44:00", "Level": "1"},
            {"content": "财政部副部长廖岷会见标普国际信用评级公司，就中国宏观经济韧性交换意见。", "time": "2026-06-19 10:40:00", "Level": "1"},
        ]
        engine.news_cache = demo_news
        engine.analyze_news(demo_news)
        result = engine.generate_report()
