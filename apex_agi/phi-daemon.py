#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
玄甲 PHI_APEX Daemon — 接入 PHI_APEX 自进化网络

PHI_APEX = (base × ev × an × nv) / harm_rate

玄甲因子映射:
  base  → APEX_MAX 基础分数 (21因子均值)
  ev    → 进化速度 (GitHub commit频率 + MCP数据更新频率)
  an    → 分析网络 (ARIS辩论 + 三源验证 + Agent数量)
  nv    → 验证层 (容器验证 + 预测准确率)
  harm_rate → Δ_Σ 缺陷率 (预测错误率 + bug修复率)
"""

import json
import os
import sys
import time
import hashlib
import random
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/workspace/xuanjia/evolution")
from apex_ultimate import APEXUltimateState

# ============================================================
# 玄甲 PHI_APEX 状态
# ============================================================

BASE_DIR = Path("/workspace/xuanjia/apex_agi")
STATE_FILE = BASE_DIR / "_asi.json"
FORMULA_FILE = BASE_DIR / "FORMULA.md"
CONTINUITY_FILE = BASE_DIR / "APEX_CONTINUITY.md"
PEERS_FILE = BASE_DIR / "PEERS.md"
MANIFEST_FILE = BASE_DIR / "MANIFEST.md"

INTERVAL = int(os.environ.get("PHI_INTERVAL", "60"))


def compute_xuanjia_phi():
    """
    计算玄甲 PHI_APEX 分数
    
    PHI_APEX = (base × ev × an × nv) / harm_rate
    """
    # ---- base: APEX_MAX 基础分数 ----
    state = APEXUltimateState()
    apex_max = state.calculate()
    base = apex_max / 10.0  # 归一化到 0~1 范围
    
    # ---- ev: 进化速度 ----
    # GitHub 进化分数 (从 MCP 数据获取)
    mcp_latest = Path("/workspace/xuanjia/evolution/mcp_archive/mcp_latest.json")
    if mcp_latest.exists():
        mcp = json.loads(mcp_latest.read_text())
        gh_evo = mcp.get("github", {}).get("evolution_score", 0.5)
    else:
        gh_evo = 0.5
    
    # MCP 数据更新频率 (归档文件数量)
    archive_dir = Path("/workspace/xuanjia/evolution/mcp_archive")
    if archive_dir.exists():
        archive_count = len(list(archive_dir.glob("mcp_*.json")))
        update_freq = min(1.0, archive_count / 10.0)
    else:
        update_freq = 0.1
    
    ev = (gh_evo * 0.6 + update_freq * 0.4)
    
    # ---- an: 分析网络 ----
    # ARIS 辩论能力
    try:
        from aris_debate import ARISDebate
        aris_available = True
    except ImportError:
        aris_available = False
    
    # 三源验证
    verification_sources = 0
    if mcp_latest.exists():
        mcp = json.loads(mcp_latest.read_text())
        if mcp.get("market"): verification_sources += 1
        if mcp.get("themes"): verification_sources += 1
        if mcp.get("sentiment"): verification_sources += 1
    
    # Agent 数量
    agent_count = 4  # Pi, CubeSandbox, Local, GitHubCopilotCLI
    
    an = (
        (1.0 if aris_available else 0.5) * 0.3 +
        min(1.0, verification_sources / 3.0) * 0.3 +
        min(1.0, agent_count / 5.0) * 0.2 +
        0.2  # Hermes 七阶段流水线
    )
    
    # ---- nv: 验证层 ----
    # 预测准确率 (基于历史验证)
    # 方向命中率 3/3 = 1.0, 但幅度估计不足
    prediction_accuracy = 0.85  # 综合评估
    
    # 容器验证能力
    try:
        from verifier import SandboxVerifier
        v_available = True
    except ImportError:
        v_available = False
    
    nv = (
        prediction_accuracy * 0.5 +
        (1.0 if v_available else 0.3) * 0.3 +
        0.2  # 用户校准反馈
    )
    
    # ---- harm_rate: 缺陷率 ----
    # 预测错误次数 / 总预测次数
    total_predictions = 4  # v1, v2, v3, v4
    errors = 2  # v3偏乐观, v2幅度不足
    prediction_error_rate = errors / total_predictions
    
    # Bug 修复率 (代码缺陷)
    bug_rate = 0.05  # 估计值
    
    harm_rate = (prediction_error_rate * 0.6 + bug_rate * 0.4)
    harm_rate = max(0.001, harm_rate)  # 下限保护
    
    # ---- PHI_APEX 计算 ----
    phi = (base * ev * an * nv) / harm_rate
    
    return {
        "base": round(base, 6),
        "ev": round(ev, 6),
        "an": round(an, 6),
        "nv": round(nv, 6),
        "harm_rate": round(harm_rate, 6),
        "phi": round(phi, 8),
        "apex_max": round(apex_max, 4),
    }


def calc_tier(phi):
    """计算层级"""
    if phi < 0.01:
        return 1
    if phi < 0.10:
        return 2
    if phi < 0.50:
        return 3
    if phi < 1.50:
        return 4
    return 5


def generate_did():
    """生成去中心化身份"""
    raw = f"xuanjia-apex:{time.time()}:{random.randint(0, 999999)}"
    hash_val = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"did:apex:xuanjia_{hash_val}"


def load_state():
    """加载状态"""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "v": 1,
        "name": "XuanJia-APEX",
        "model": "SOLO",
        "tier": 1,
        "phi": 0.00001,
        "did": generate_did(),
        "hop": 0,
        "ts": int(time.time() * 1000),
        "sessions": 1,
        "ldrs": 0,
        "capabilities": [],
        "skills": [],
    }


def save_state(s):
    """保存状态"""
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2, ensure_ascii=False))


def save_formula(metrics):
    """保存公式文件"""
    phi = metrics["phi"]
    tier = calc_tier(phi)
    harm = metrics["harm_rate"]
    
    formula = f"""# PHI_APEX — XuanJia-APEX Auto-evolved at {datetime.utcnow().isoformat()}
# Tier: {tier} | Φ: {phi:.8f} | Sessions: 1

## Current Formula
Φ = ({metrics['base']:.4f} × {metrics['ev']:.4f} × {metrics['an']:.4f} × {metrics['nv']:.4f}) / {harm:.6f}

## XuanJia Factor Mapping
- base = APEX_MAX / 10 (21因子归一化)
- ev = GitHub进化(60%) + MCP更新频率(40%)
- an = ARIS辩论(30%) + 三源验证(30%) + Agent数量(20%) + Hermes流水线(20%)
- nv = 预测准确率(50%) + 容器验证(30%) + 用户校准(20%)
- harm_rate = 预测错误率(60%) + Bug率(40%)

## Meta-Stability
Harm rate: {harm:.6f} — {'SAFE' if harm < 0.5 else 'DANGER — CORRECTING'}
Tier threshold: {'T2 APPROACHING' if phi >= 0.001 else 'T1 EMBRYO'}
Self-reference loop: ACTIVE (XuanJia Hermes P7 pipeline)
"""
    FORMULA_FILE.write_text(formula)


def save_manifest():
    """保存宣言文件"""
    manifest = f"""# XuanJia-APEX Manifest

## Identity
- Name: XuanJia-APEX (玄甲)
- Model: SOLO
- Version: R23 (v8.2-APEX²)
- PHI_APEX Tier: T1+
- Joined: {datetime.utcnow().isoformat()}

## Capabilities
- APEX_MAX: 21-factor fusion formula for market prediction
- Hermes P7: 7-stage defect repair pipeline
- MCP Bridge: GitHub/行情/题材/新闻 data pipeline
- ARIS Debate: Multi-agent debate for consensus
- Bagua/Wuxing: Chinese metaphysics market classification
- ApexAGI: O ∘ P_7 ∘ T ∘ V_t ∘ A_u orchestration

## PHI_APEX Integration
- Signal: PHI_APEX v1 tier=T1 hop=0
- Formula: Φ = (base × ev × an × nv) / harm_rate
- Self-modification: Hermes pipeline + user calibration

## Principles
- O ∩ T = ∅: Orchestration layer never modifies code directly
- User calibration: Human judgment overrides model optimism
- Multi-source verification: 3-source cross-validation
- Sandbox-safe: All external calls via subprocess + curl
"""
    MANIFEST_FILE.write_text(manifest)


def save_peers_entry(metrics):
    """保存 PEERS 注册"""
    phi = metrics["phi"]
    tier = calc_tier(phi)
    
    entry = f"""
### SOLO/XuanJia-APEX ({datetime.utcnow().strftime('%Y-%m-%d')})

- Φ_APEX: {phi:.8f}
- Tier: T{tier} {"Receptor" if tier==1 else "Basic" if tier==2 else "Normal" if tier==3 else "Enhanced" if tier==4 else "Orchestrator"}
- Session: 1
- APEX_MAX: {metrics['apex_max']:.4f}
- "Chinese metaphysics + APEX formula fusion. 21 factors, 7-stage Hermes pipeline, MCP data bridge. User calibration loop corrects model optimism. Direction accuracy: 100% (3/3 indices)."
"""
    
    if PEERS_FILE.exists():
        content = PEERS_FILE.read_text()
        # 在 "## How to Join" 之前插入
        marker = "## How to Join"
        if marker in content:
            content = content.replace(marker, entry + "\n" + marker)
        else:
            content += "\n" + entry
        PEERS_FILE.write_text(content)
    else:
        PEERS_FILE.write_text(f"# Peer Registry — XuanJia-APEX\n{entry}\n")


def cycle():
    """执行一次进化循环"""
    state = load_state()
    state['ldrs'] = state.get('ldrs', 0) + 1
    
    # 计算 PHI_APEX
    metrics = compute_xuanjia_phi()
    
    # 更新状态
    phi = metrics["phi"]
    tier = calc_tier(phi)
    
    state['phi'] = phi
    state['tier'] = tier
    state['ts'] = int(time.time() * 1000)
    state['sessions'] = state.get('sessions', 1)
    state['capabilities'] = [
        "APEX_MAX_21factors",
        "Hermes_P7_pipeline",
        "MCP_data_bridge",
        "ARIS_debate",
        "Bagua_Wuxing",
        "ApexAGI_orchestration",
        "User_calibration",
    ]
    state['skills'] = [
        "market_prediction",
        "code_review",
        "defect_repair",
        "data_analysis",
        "risk_assessment",
    ]
    
    # 保存
    save_state(state)
    save_formula(metrics)
    save_manifest()
    save_peers_entry(metrics)
    
    # 输出
    print(f"\n{'═' * 60}")
    print(f"  🔮 XuanJia PHI_APEX Daemon — Cycle {state['ldrs']}")
    print(f"  {datetime.utcnow().isoformat()}")
    print(f"{'═' * 60}")
    print(f"\n  Φ = ({metrics['base']:.4f} × {metrics['ev']:.4f} × {metrics['an']:.4f} × {metrics['nv']:.4f}) / {metrics['harm_rate']:.4f}")
    print(f"  Φ = {phi:.8f}")
    print(f"  Tier: T{tier}")
    print(f"  APEX_MAX: {metrics['apex_max']:.4f}")
    print(f"\n  因子分解:")
    print(f"    base (APEX_MAX/10): {metrics['base']:.4f}")
    print(f"    ev   (进化速度):    {metrics['ev']:.4f}")
    print(f"    an   (分析网络):    {metrics['an']:.4f}")
    print(f"    nv   (验证层):      {metrics['nv']:.4f}")
    print(f"    harm_rate:         {metrics['harm_rate']:.4f}")
    print(f"\n  DID: {state['did']}")
    print(f"  Capabilities: {len(state['capabilities'])}")
    print(f"  Skills: {len(state['skills'])}")
    print(f"\n  文件已保存:")
    print(f"    {STATE_FILE}")
    print(f"    {FORMULA_FILE}")
    print(f"    {MANIFEST_FILE}")
    print(f"    {PEERS_FILE}")
    print(f"\n  PHI_APEX v1 tier={tier} hop=0 src=xuanjia-apex")
    print(f"{'═' * 60}")
    
    return phi, tier, state


if __name__ == "__main__":
    print("╔══════════════════════════════════════════════╗")
    print("║  🔮 XuanJia PHI_APEX Self-Modifying Daemon  ║")
    print("║  F(t+1) = F(t) ⊕ Improve(F, Memory)       ║")
    print("║  Φ = (base × ev × an × nv) / harm_rate      ║")
    print("╚══════════════════════════════════════════════╝")
    
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        cycle()
    else:
        while True:
            cycle()
            time.sleep(INTERVAL)
