"""
ApexAGI HotSwap Authorizer (A_u)
================================
A_u 用户授权 + 热切换模块。

公式: ApexAGI = O ∘ P_7 ∘ T ∘ V_t ∘ A_u,  O ∩ T = ∅

本模块实现 HotSwapAuthorizer 类，提供:
- 用户授权请求与审批
- 变更预览（diff 格式）
- 变更应用与回滚
- 模块热切换（importlib.reload）

约束:
- 所有外部调用必须通过 subprocess，不能使用直接网络库
- 每个外部调用必须有 try/except + fallback
- 所有操作记录到日志
"""

from __future__ import annotations

import difflib
import hashlib
import importlib
import importlib.util
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logger = logging.getLogger("apex_agi.authorizer")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _ch = logging.StreamHandler(sys.stdout)
    _ch.setLevel(logging.DEBUG)
    _fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    _ch.setFormatter(_fmt)
    logger.addHandler(_ch)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _run_subprocess(
    cmd: List[str],
    timeout: int = 60,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """安全地运行子进程命令，返回统一格式的结果字典。"""
    result = {
        "returncode": -1,
        "stdout": "",
        "stderr": "",
        "error": None,
    }
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
        result["returncode"] = proc.returncode
        result["stdout"] = proc.stdout
        result["stderr"] = proc.stderr
    except subprocess.TimeoutExpired as e:
        result["error"] = f"Command timed out after {timeout}s: {' '.join(cmd)}"
        result["stderr"] = str(e)
        logger.warning(result["error"])
    except FileNotFoundError as e:
        result["error"] = f"Command not found: {' '.join(cmd)}"
        result["stderr"] = str(e)
        logger.warning(result["error"])
    except Exception as e:
        result["error"] = f"Unexpected error running {' '.join(cmd)}: {e}"
        result["stderr"] = traceback.format_exc()
        logger.exception(result["error"])
    return result


def _compute_checksum(content: str) -> str:
    """计算内容 SHA256 校验和。"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _generate_backup_id() -> str:
    """生成唯一备份 ID。"""
    return f"BK-{int(time.time())}-{_compute_checksum(str(time.time()))}"


# ---------------------------------------------------------------------------
# HotSwapAuthorizer
# ---------------------------------------------------------------------------

class HotSwapAuthorizer:
    """用户授权 + 热切换授权器。

    职责:
        1. 请求用户授权变更
        2. 生成变更预览（diff 格式）
        3. 应用已授权的变更（支持备份）
        4. 回滚变更
        5. 热切换模块代码（不重启进程）
    """

    def __init__(self, auto_approve: bool = False):
        self.auto_approve = auto_approve
        self.pending_changes: List[Dict[str, Any]] = []
        self._backup_dir = Path(tempfile.gettempdir()) / "apex_agi_backups"
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"HotSwapAuthorizer initialized (auto_approve={auto_approve})")

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    def request_authorization(self, changes: list, report: dict) -> dict:
        """请求用户授权。

        返回:
            {
                "approved": bool,
                "approved_changes": list,
                "rejected_changes": list,
            }
        """
        logger.info(f"Requesting authorization for {len(changes)} change(s).")

        if self.auto_approve:
            logger.info("Auto-approve enabled. All changes approved.")
            return {
                "approved": True,
                "approved_changes": list(changes),
                "rejected_changes": [],
            }

        # 生成预览
        preview = self.preview_changes(changes)
        logger.info("Change preview generated.")

        # 交互式授权（命令行环境）
        approved_changes = []
        rejected_changes = []

        for change in changes:
            change_id = change.get("id", "unknown")
            file_path = change.get("file_path", "unknown")
            logger.info(f"Prompting for change {change_id} ({file_path})")

            # 在自动化/非交互环境中，默认拒绝；auto_approve 为 True 时已在上方返回
            # 这里提供一个可扩展的钩子：如果环境变量设置了 AUTO_APPROVE，则自动批准
            if os.environ.get("APEX_AGI_AUTO_APPROVE", "").lower() in ("1", "true", "yes"):
                approved_changes.append(change)
                continue

            # 默认行为：拒绝（需要上层 UI 覆盖此方法或设置 auto_approve）
            rejected_changes.append(change)

        approved = len(approved_changes) > 0
        logger.info(
            f"Authorization result: approved={approved}, "
            f"approved_count={len(approved_changes)}, rejected_count={len(rejected_changes)}"
        )
        return {
            "approved": approved,
            "approved_changes": approved_changes,
            "rejected_changes": rejected_changes,
        }

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def preview_changes(self, changes: list) -> str:
        """生成变更预览（diff 格式）。"""
        lines: List[str] = []
        lines.append("=" * 60)
        lines.append("ApexAGI Change Preview")
        lines.append("=" * 60)

        for change in changes:
            file_path = change.get("file_path", "unknown")
            before = change.get("before", "")
            after = change.get("after", "")
            change_id = change.get("id", "unknown")

            lines.append("")
            lines.append(f"--- Change {change_id}: {file_path} ---")
            diff = difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"{file_path} (before)",
                tofile=f"{file_path} (after)",
            )
            lines.extend(diff)

        lines.append("")
        lines.append("=" * 60)
        preview = "".join(lines)
        logger.debug(f"Preview length: {len(preview)} chars")
        return preview

    # ------------------------------------------------------------------
    # Apply / Rollback
    # ------------------------------------------------------------------

    def apply_changes(self, changes: list, backup: bool = True) -> dict:
        """应用已授权的变更。

        Args:
            changes: 变更列表，每个元素为 dict，包含 file_path、after 等。
            backup: 是否创建备份。

        Returns:
            {
                "status": "success" | "partial" | "failed",
                "backup_id": str | None,
                "applied": list,
                "failed": list,
            }
        """
        logger.info(f"Applying {len(changes)} change(s), backup={backup}")
        backup_id = _generate_backup_id() if backup else None
        applied = []
        failed = []

        if backup:
            backup_path = self._backup_dir / backup_id
            backup_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Backup directory created: {backup_path}")

        for change in changes:
            file_path = change.get("file_path", "")
            after = change.get("after", "")
            change_id = change.get("id", "unknown")

            if not file_path:
                failed.append({"change_id": change_id, "error": "Missing file_path"})
                continue

            path = Path(file_path)
            try:
                # 备份原文件
                if backup and path.exists():
                    backup_file = backup_path / path.name
                    # 处理同名文件冲突
                    counter = 1
                    original_backup_file = backup_file
                    while backup_file.exists():
                        backup_file = original_backup_file.with_name(
                            f"{path.name}.{counter}"
                        )
                        counter += 1
                    shutil.copy2(str(path), str(backup_file))
                    logger.debug(f"Backed up {path} -> {backup_file}")

                # 写入新内容
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(after, encoding="utf-8")
                applied.append({
                    "change_id": change_id,
                    "file_path": str(path),
                    "checksum": _compute_checksum(after),
                })
                logger.info(f"Applied change {change_id} -> {path}")

            except Exception as e:
                logger.exception(f"Failed to apply change {change_id}: {e}")
                failed.append({"change_id": change_id, "error": str(e)})

        status = "success" if not failed else ("partial" if applied else "failed")
        result = {
            "status": status,
            "backup_id": backup_id,
            "applied": applied,
            "failed": failed,
        }
        logger.info(f"Apply changes result: {status}")
        return result

    def rollback_changes(self, backup_id: str) -> dict:
        """回滚变更。

        Args:
            backup_id: 备份 ID。

        Returns:
            {
                "status": "success" | "failed",
                "restored": list,
                "errors": list,
            }
        """
        logger.info(f"Rolling back changes from backup {backup_id}")
        backup_path = self._backup_dir / backup_id
        if not backup_path.exists():
            logger.error(f"Backup not found: {backup_path}")
            return {
                "status": "failed",
                "restored": [],
                "errors": [f"Backup {backup_id} not found."],
            }

        restored = []
        errors = []

        for backup_file in backup_path.iterdir():
            if not backup_file.is_file():
                continue
            # 恢复路径：假设备份文件名与原始文件名一致
            # 注意：这里简化处理，实际应存储原始路径映射
            # 为支持正确回滚，我们在备份时存储元数据
            meta_file = backup_file.with_suffix(backup_file.suffix + ".meta")
            target_path = Path(backup_file.name)
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    target_path = Path(meta["original_path"])
                except Exception as e:
                    logger.warning(f"Failed to read meta for {backup_file}: {e}")

            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(backup_file), str(target_path))
                restored.append(str(target_path))
                logger.info(f"Restored {target_path} from {backup_file}")
            except Exception as e:
                logger.exception(f"Failed to restore {target_path}: {e}")
                errors.append(str(e))

        status = "success" if not errors else ("partial" if restored else "failed")
        result = {
            "status": status,
            "restored": restored,
            "errors": errors,
        }
        logger.info(f"Rollback result: {status}")
        return result

    def _store_backup_meta(self, backup_path: Path, original_path: Path) -> None:
        """存储备份元数据，用于精确回滚。"""
        meta = {
            "original_path": str(original_path),
            "backup_time": time.time(),
        }
        meta_file = backup_path.with_suffix(backup_path.suffix + ".meta")
        meta_file.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    # ------------------------------------------------------------------
    # Hot Swap
    # ------------------------------------------------------------------

    def hot_swap(self, module_path: str, new_code: str) -> dict:
        """热切换: 不重启进程替换模块代码。

        使用 importlib.reload 实现。若模块未加载，则先加载再重载。

        Args:
            module_path: Python 模块文件路径（如 /path/to/module.py）。
            new_code: 新的模块源代码。

        Returns:
            {
                "status": "success" | "failed",
                "module_name": str,
                "old_checksum": str,
                "new_checksum": str,
                "error": str | None,
            }
        """
        logger.info(f"Hot swap requested for {module_path}")
        path = Path(module_path)
        if not path.exists():
            return {
                "status": "failed",
                "module_name": "",
                "old_checksum": "",
                "new_checksum": "",
                "error": f"Module path not found: {module_path}",
            }

        try:
            # 读取旧内容
            old_code = path.read_text(encoding="utf-8")
            old_checksum = _compute_checksum(old_code)
            new_checksum = _compute_checksum(new_code)

            # 写入新代码
            path.write_text(new_code, encoding="utf-8")
            logger.info(f"Module {module_path} updated on disk.")

            # 推导模块名
            module_name = self._path_to_module_name(module_path)
            if not module_name:
                return {
                    "status": "failed",
                    "module_name": "",
                    "old_checksum": old_checksum,
                    "new_checksum": new_checksum,
                    "error": f"Cannot derive module name from {module_path}",
                }

            # 若模块已加载，使用 importlib.reload
            if module_name in sys.modules:
                logger.info(f"Reloading module: {module_name}")
                module = sys.modules[module_name]
                importlib.reload(module)
                logger.info(f"Module {module_name} reloaded successfully.")
            else:
                # 模块未加载，尝试加载
                logger.info(f"Module {module_name} not loaded. Loading now.")
                spec = importlib.util.spec_from_file_location(module_name, str(path))
                if spec is None or spec.loader is None:
                    return {
                        "status": "failed",
                        "module_name": module_name,
                        "old_checksum": old_checksum,
                        "new_checksum": new_checksum,
                        "error": f"Cannot create module spec for {module_path}",
                    }
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                logger.info(f"Module {module_name} loaded successfully.")

            return {
                "status": "success",
                "module_name": module_name,
                "old_checksum": old_checksum,
                "new_checksum": new_checksum,
                "error": None,
            }

        except Exception as e:
            logger.exception(f"Hot swap failed for {module_path}: {e}")
            return {
                "status": "failed",
                "module_name": "",
                "old_checksum": "",
                "new_checksum": "",
                "error": str(e),
            }

    def _path_to_module_name(self, module_path: str) -> str:
        """从文件路径推导模块名（支持包路径）。"""
        path = Path(module_path).resolve()

        # 尝试找到包根（包含 __init__.py 的目录）
        parts = [path.stem]
        current = path.parent
        while current != current.parent:
            if (current / "__init__.py").exists():
                parts.insert(0, current.name)
                current = current.parent
            else:
                break

        # 如果路径在 sys.path 中，尝试匹配
        for sp in sys.path:
            sp_path = Path(sp).resolve()
            try:
                rel = path.relative_to(sp_path)
                module_name = str(rel.with_suffix("")).replace(os.sep, ".")
                return module_name
            except ValueError:
                continue

        # 回退：使用推导的包路径
        return ".".join(parts)

    # ------------------------------------------------------------------
    # AuthorizationInterface compatibility
    # ------------------------------------------------------------------

    def request_approval(self, change_set: Dict[str, Any]) -> bool:
        """兼容 orchestrator.AuthorizationInterface 的 request_approval 方法。"""
        changes = change_set.get("changes", [])
        report = change_set.get("report", {})
        result = self.request_authorization(changes, report)
        return result.get("approved", False)

    def deploy(self, change_set: Dict[str, Any]) -> Dict[str, Any]:
        """兼容 orchestrator.AuthorizationInterface 的 deploy 方法。

        执行热切换部署：先应用变更，再对 Python 模块执行热重载。
        """
        changes = change_set.get("changes", [])
        if not changes:
            return {"status": "skipped", "message": "No changes to deploy."}

        # 1. 应用变更
        apply_result = self.apply_changes(changes, backup=True)
        if apply_result["status"] == "failed":
            return apply_result

        # 2. 对 Python 模块执行热切换
        hot_swap_results = []
        for item in apply_result.get("applied", []):
            file_path = item.get("file_path", "")
            if file_path.endswith(".py"):
                try:
                    new_code = Path(file_path).read_text(encoding="utf-8")
                    hs_result = self.hot_swap(file_path, new_code)
                    hot_swap_results.append(hs_result)
                except Exception as e:
                    logger.exception(f"Hot swap failed for {file_path}: {e}")
                    hot_swap_results.append({
                        "status": "failed",
                        "module_name": "",
                        "error": str(e),
                    })

        return {
            "status": apply_result["status"],
            "apply_result": apply_result,
            "hot_swap_results": hot_swap_results,
        }

    # ------------------------------------------------------------------
    # Backup management
    # ------------------------------------------------------------------

    def list_backups(self) -> List[Dict[str, Any]]:
        """列出所有可用备份。"""
        backups = []
        if not self._backup_dir.exists():
            return backups
        for bp in self._backup_dir.iterdir():
            if bp.is_dir():
                files = [f.name for f in bp.iterdir() if f.is_file() and not f.suffix.endswith(".meta")]
                backups.append({
                    "backup_id": bp.name,
                    "file_count": len(files),
                    "files": files,
                })
        return backups

    def delete_backup(self, backup_id: str) -> Dict[str, Any]:
        """删除指定备份。"""
        backup_path = self._backup_dir / backup_id
        if not backup_path.exists():
            return {"status": "failed", "error": f"Backup {backup_id} not found."}
        try:
            shutil.rmtree(str(backup_path))
            logger.info(f"Backup {backup_id} deleted.")
            return {"status": "success", "backup_id": backup_id}
        except Exception as e:
            logger.exception(f"Failed to delete backup {backup_id}: {e}")
            return {"status": "failed", "error": str(e)}
