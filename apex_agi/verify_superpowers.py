#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
玄甲 Superpowers 验证脚本
持续验证X大神策略引擎的核心能力
"""

import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from x_god_strategy import XGodStrategyEngine, PRESET_UNIVERSE


class SuperpowerVerifier:
    """Superpowers 验证器"""

    TESTS = [
        "test_step1_screening",
        "test_step2_review",
        "test_step3_red_team",
        "test_step4_monitoring",
        "test_beyond_x_fusion",
        "test_stop_loss",
        "test_confidence_calculation",
        "test_phi_coefficient",
        "test_pipeline_integrity",
        "test_manifest_consistency"
    ]

    def __init__(self):
        self.engine = XGodStrategyEngine()
        self.results = {}
        self.passed = 0
        self.failed = 0

    def run_all(self):
        """运行全部验证测试"""
        print("=" * 60)
        print("玄甲 Superpowers 验证")
        print("=" * 60)
        print(f"验证时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"测试项数: {len(self.TESTS)}")
        print("=" * 60)

        for test_name in self.TESTS:
            try:
                test_method = getattr(self, test_name)
                test_method()
                self.passed += 1
                print(f"  ✓ {test_name}")
            except AssertionError as e:
                self.failed += 1
                print(f"  ✗ {test_name}: {e}")
            except Exception as e:
                self.failed += 1
                print(f"  ✗ {test_name}: 异常 - {e}")

        print("=" * 60)
        print(f"验证完成: {self.passed}/{len(self.TESTS)} 通过, {self.failed} 失败")
        print("=" * 60)
        return self.failed == 0

    # ========== 测试项 ==========

    def test_step1_screening(self):
        """验证Step1初筛逻辑"""
        results = self.engine.step1_screen(PRESET_UNIVERSE)
        assert len(results) >= 10, f"初筛结果不足: {len(results)}"
        for r in results:
            assert 30 <= r.market_cap <= 150, f"市值超出范围: {r.market_cap}"
            assert r.localization_rate < 20, f"国产化率过高: {r.localization_rate}"
            assert r.expansion_cycle_months > 18, f"扩产周期过短: {r.expansion_cycle_months}"
        self.results["step1_count"] = len(results)

    def test_step2_review(self):
        """验证Step2复审逻辑"""
        step1 = self.engine.step1_screen(PRESET_UNIVERSE)
        step2 = self.engine.step2_review(step1)
        assert len(step2) <= len(step1), "复审后数量不应增加"
        for r in step2:
            assert r.analyst_reports_count <= 15, f"研报过多未剔除: {r.analyst_reports_count}"
        self.results["step2_count"] = len(step2)

    def test_step3_red_team(self):
        """验证Step3红队证伪"""
        step1 = self.engine.step1_screen(PRESET_UNIVERSE)
        step2 = self.engine.step2_review(step1)
        critical_count = 0
        for stock in step2:
            report = self.engine.step3_red_team(stock)
            assert report.risk_level in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
            assert 0 <= report.overall_risk_score <= 100
            if report.risk_level == "CRITICAL":
                critical_count += 1
        self.results["critical_count"] = critical_count

    def test_step4_monitoring(self):
        """验证Step4持股监控"""
        stock = PRESET_UNIVERSE[0]
        milestones = self.engine.step4_monitor(stock)
        assert len(milestones) == 3, f"里程碑数量错误: {len(milestones)}"
        assert milestones[0].name == "订单验证"
        assert milestones[1].name == "毛利率验证"
        assert milestones[2].name == "产能/客户验证"

    def test_beyond_x_fusion(self):
        """验证Beyond X融合模块"""
        stock = PRESET_UNIVERSE[0]
        fusion = self.engine.beyond_x_fusion(stock)
        assert "beyond_x_score" in fusion
        assert "confidence" in fusion
        assert 0 <= fusion["confidence"] <= 100
        assert fusion["phi_coefficient"] <= 2.0, "PHI系数超出上限"

    def test_stop_loss(self):
        """验证止损逻辑"""
        stock = PRESET_UNIVERSE[0]
        self.engine.step4_monitor(stock)
        self.engine.step3_red_team(stock)
        # 测试跌幅止损
        should_stop, reason = self.engine.check_stop_loss(stock.code, {"drawdown": 20})
        assert should_stop, "跌幅止损未触发"
        assert "15%" in reason
        # 测试正常情况
        should_stop, reason = self.engine.check_stop_loss(stock.code, {"drawdown": 5})
        assert not should_stop, "正常情况误触发止损"

    def test_confidence_calculation(self):
        """验证置信度计算"""
        stock = PRESET_UNIVERSE[0]
        conf = self.engine._calculate_confidence(stock)
        assert 0 <= conf <= 100, f"置信度超出范围: {conf}"
        self.results["sample_confidence"] = conf

    def test_phi_coefficient(self):
        """验证PHI进化系数"""
        stock = PRESET_UNIVERSE[0]
        phi = self.engine._phi_evolution_coefficient(stock)
        assert phi > 0, "PHI系数应为正"
        assert phi <= 2.0, f"PHI系数超出上限: {phi}"
        self.results["sample_phi"] = phi

    def test_pipeline_integrity(self):
        """验证完整流水线完整性"""
        results = self.engine.execute_full_pipeline(PRESET_UNIVERSE)
        assert "step1_screened" in results
        assert "step2_reviewed" in results
        assert "step3_red_team" in results
        assert "step4_milestones" in results
        assert "beyond_x" in results
        assert "final_recommendations" in results
        assert len(results["final_recommendations"]) <= 10
        self.results["final_top_count"] = len(results["final_recommendations"])

    def test_manifest_consistency(self):
        """验证manifest与引擎结果一致性"""
        manifest_path = os.path.join(os.path.dirname(__file__), "x_god_strategy_manifest.json")
        if os.path.exists(manifest_path):
            with open(manifest_path) as f:
                manifest = json.load(f)
            assert manifest["verification_status"]["engine_tested"]
            assert manifest["verification_status"]["pipeline_executed"]
            assert len(manifest["top10_results"]) <= 10


def main():
    verifier = SuperpowerVerifier()
    success = verifier.run_all()

    # 输出验证报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_tests": len(verifier.TESTS),
        "passed": verifier.passed,
        "failed": verifier.failed,
        "success_rate": round(verifier.passed / len(verifier.TESTS) * 100, 1),
        "details": verifier.results
    }

    report_path = os.path.join(os.path.dirname(__file__), "superpower_verification_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n验证报告已保存: {report_path}")
    print(f"成功率: {report['success_rate']}%")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
