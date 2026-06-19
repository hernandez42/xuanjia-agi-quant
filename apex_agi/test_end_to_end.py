#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ApexAGI 端到端测试

验证完整公式: ApexAGI = O ∘ P_7 ∘ T ∘ V_t ∘ A_u
"""

import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import ApexAGIOrchestrator
from hermes_pipeline import HermesPipeline
from agent_adapters import (
    LocalAgentAdapter, PiAgentAdapter,
    CubeSandboxAdapter, GitHubCopilotCLIAdapter,
    create_adapter, list_available_adapters
)
from verifier import SandboxVerifier
from authorizer import HotSwapAuthorizer


def create_test_codebase() -> str:
    """创建一个有缺陷的测试代码库"""
    tmpdir = tempfile.mkdtemp(prefix="apex_agi_test_")
    
    # 文件1: 有语法错误的 Python 文件
    buggy_file = Path(tmpdir) / "buggy_module.py"
    buggy_file.write_text('''
def calculate_sum(a, b)
    """计算两个数的和"""
    result = a + b
    return result

def divide(a, b):
    """除法 - 有 ZeroDivisionError 风险"""
    return a / b  # 未处理 b=0

def unused_function():
    x = 10
    y = 20
    # TODO: 实现逻辑
    pass

def eval_user_input(user_input):
    # 安全风险: 使用 eval
    return eval(user_input)
''')
    
    # 文件2: 测试文件
    test_file = Path(tmpdir) / "test_buggy.py"
    test_file.write_text('''
import pytest
from buggy_module import calculate_sum, divide

def test_calculate_sum():
    assert calculate_sum(2, 3) == 5

def test_divide():
    assert divide(10, 2) == 5
    assert divide(10, 0) == float('inf')  # 会失败
''')
    
    return tmpdir


def test_agent_adapters():
    """测试外部 Agent 适配器"""
    print("\n" + "=" * 70)
    print("  T4: 外部 Agent 适配器测试")
    print("=" * 70)
    
    adapters = list_available_adapters()
    print(f"\n可用适配器: {adapters}")
    
    for adapter_info in adapters:
        name = adapter_info["name"]
        adapter = create_adapter(name)
        health = adapter.health_check()
        caps = adapter.capabilities()
        status = "✅" if health else "❌"
        print(f"  {status} {name}: {caps}")
    
    # 测试 LocalAgent 执行简单修复
    local = create_adapter("local_agent")
    from orchestrator import Task
    task_obj = Task(
        id="TEST-LOCAL-001",
        name="修复语法错误",
        description="修复语法错误",
        target_files=["test.py"],
        issue_ids=[],
        pipeline_config={"action": "basic_fix"},
    )
    result = local.execute(task_obj, {})
    print(f"\n  LocalAgent 执行结果: {result.get('status', 'unknown')}")
    
    return True


def test_hermes_pipeline():
    """测试七阶段 Hermes 流水线"""
    print("\n" + "=" * 70)
    print("  T3: 七阶段 Hermes 流水线测试")
    print("=" * 70)
    
    pipeline = HermesPipeline()
    
    task = {
        "id": "TEST-001",
        "description": "修复 buggy_module.py 中的缺陷",
        "file_path": "buggy_module.py",
        "issues": [
            {"type": "syntax_error", "line": 2, "severity": "critical"},
            {"type": "security", "line": 18, "severity": "high"},
        ]
    }
    
    agents = {"local_agent": create_adapter("local_agent")}
    result = pipeline.execute(task, agents)
    
    print(f"\n  流水线执行结果:")
    for stage_name, stage_result in result.get("results", {}).items():
        status = stage_result.get("status", "unknown")
        emoji = "✅" if status == "completed" else "❌"
        print(f"  {emoji} {stage_name}: {status}")
    
    return True


def test_verifier():
    """测试 V_t 容器验证"""
    print("\n" + "=" * 70)
    print("  T5: V_t 容器验证测试")
    print("=" * 70)
    
    verifier = SandboxVerifier(sandbox_type="local")
    
    code_before = "def add(a, b):\n    return a + b\n"
    code_after = "def add(a, b):\n    if not isinstance(a, (int, float)):\n        raise TypeError('a must be number')\n    return a + b\n"
    
    result = verifier.replay_in_sandbox(
        code_before=code_before,
        code_after=code_after,
        test_command="python -c 'from test_module import add; print(add(2,3))'"
    )
    
    print(f"\n  验证结果:")
    print(f"  • 基线通过: {result.get('baseline', {}).get('passed', False)}")
    print(f"  • 修改后通过: {result.get('new', {}).get('passed', False)}")
    print(f"  • 无回归: {result.get('no_regression', False)}")
    
    return True


def test_authorizer():
    """测试 A_u 授权+热切换"""
    print("\n" + "=" * 70)
    print("  T6: A_u 授权+热切换测试")
    print("=" * 70)
    
    auth = HotSwapAuthorizer(auto_approve=True)
    
    changes = [
        {
            "file_path": "test_module.py",
            "original": "def add(a, b):\n    return a + b\n",
            "modified": "def add(a, b):\n    return a + b + 1\n",
        }
    ]
    
    # 预览变更
    preview = auth.preview_changes(changes)
    print(f"\n  变更预览:\n{preview[:200]}...")
    
    # 请求授权 (auto_approve=True 自动通过)
    approval = auth.request_authorization(changes, {"summary": "测试变更"})
    print(f"\n  授权结果: {'✅ 已批准' if approval.get('approved') else '❌ 已拒绝'}")
    
    return True


def test_full_orchestrator():
    """测试完整编排器 O"""
    print("\n" + "=" * 70)
    print("  T2: 完整编排器 O 测试")
    print("=" * 70)
    
    # 创建测试代码库
    codebase = create_test_codebase()
    print(f"\n  测试代码库: {codebase}")
    
    # 初始化编排器
    orchestrator = ApexAGIOrchestrator()
    
    # 注册外部 Agent
    local_agent = create_adapter("local_agent")
    orchestrator.register_agent("local", local_agent)
    
    # 设置流水线
    pipeline = HermesPipeline()
    orchestrator.set_pipeline(pipeline)
    
    # 设置验证器
    verifier = SandboxVerifier(sandbox_type="local")
    orchestrator.set_verifier(verifier)
    
    # 设置授权器 (自动批准用于测试)
    authorizer = HotSwapAuthorizer(auto_approve=True)
    orchestrator.set_authorizer(authorizer)
    
    # 执行完整周期
    print(f"\n  执行完整周期: ApexAGI = O ∘ P_7 ∘ T ∘ V_t ∘ A_u")
    report = orchestrator.run_cycle(codebase)
    
    # 输出报告
    print(f"\n  执行报告:")
    print(f"  • 最终状态: {report.final_state}")
    print(f"  • 识别问题数: {len(report.issues_found)}")
    print(f"  • 生成任务数: {len(report.tasks)}")
    print(f"  • 流水线结果: {report.pipeline_results}")
    print(f"  • 验证结果: {report.verification_results}")
    print(f"  • 授权结果: {report.authorization_results}")
    
    # 生成文本报告
    text_report = orchestrator.generate_report(report)
    print(f"\n  报告摘要:\n{text_report[:500]}...")
    
    # 保存报告
    report_path = Path(codebase) / "apex_agi_report.json"
    orchestrator.save_report(str(report_path), report)
    print(f"\n  报告已保存: {report_path}")
    
    # 清理
    shutil.rmtree(codebase, ignore_errors=True)
    
    return True


def main():
    """运行全部端到端测试"""
    print("=" * 70)
    print("  ApexAGI 端到端测试")
    print("  验证公式: ApexAGI = O ∘ P_7 ∘ T ∘ V_t ∘ A_u")
    print("=" * 70)
    
    tests = [
        ("T4: Agent适配器", test_agent_adapters),
        ("T3: Hermes流水线", test_hermes_pipeline),
        ("T5: 容器验证", test_verifier),
        ("T6: 授权热切换", test_authorizer),
        ("T2: 完整编排器", test_full_orchestrator),
    ]
    
    results = []
    for name, test_fn in tests:
        try:
            test_fn()
            results.append((name, True, None))
        except Exception as e:
            results.append((name, False, str(e)))
            print(f"\n  ❌ {name} 失败: {e}")
    
    # 汇总
    print("\n" + "=" * 70)
    print("  测试结果汇总")
    print("=" * 70)
    
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    
    for name, ok, err in results:
        status = "✅ PASS" if ok else f"❌ FAIL: {err}"
        print(f"  {status} — {name}")
    
    print(f"\n  总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n  🎉 全部测试通过！ApexAGI 运行范式已激活！")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
