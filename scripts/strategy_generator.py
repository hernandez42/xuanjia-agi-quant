#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
玄甲引擎 - 策略生成脚本
盘前生成今日策略
"""

import json
import os
import glob
from datetime import datetime

def generate_strategy():
    """生成今日策略"""
    date_str = datetime.now().strftime('%Y%m%d')
    
    # 读取最新市场扫描数据
    market_files = sorted(glob.glob('/workspace/xuanjia/data/market_scan_*.json'))
    latest_market = market_files[-1] if market_files else None
    
    # 读取最新资讯
    news_files = sorted(glob.glob('/workspace/xuanjia/news/news_flash_*.json'))
    latest_news = news_files[-1] if news_files else None
    
    # 生成策略
    strategy = {
        'date': date_str,
        'generate_time': datetime.now().isoformat(),
        'market_data': latest_market,
        'news_data': latest_news,
        'top5_picks': [],
        'risk_level': 'medium',
        'summary': '策略生成完成'
    }
    
    # 写入文件
    output_file = f'/workspace/xuanjia/strategy/strategy_{date_str}.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(strategy, f, ensure_ascii=False, indent=2)
    
    print(f"[OK] 策略生成完成: {output_file}")
    return strategy

if __name__ == '__main__':
    generate_strategy()
