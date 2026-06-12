# 文件说明：项目工程卫生测试：验证启动脚本和依赖清单保持可复现、轻量。

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProjectHygieneTests(unittest.TestCase):
    # 后端脚本应优先使用项目虚拟环境，避免依赖安装在系统 Python 时启动失败。
    def test_backend_start_script_prefers_project_virtualenv_uvicorn(self):
        script = (ROOT / "scripts" / "run_backend.sh").read_text(encoding="utf-8")

        self.assertIn('backend/.venv/bin/uvicorn', script)
        self.assertIn('.venv/bin/uvicorn', script)
        self.assertIn('exec "$UVICORN_BIN"', script)

    # requirements 只保留源码实际需要的运行/测试依赖。
    def test_backend_requirements_do_not_include_unused_pandas(self):
        requirements = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")

        self.assertNotIn("pandas", requirements)


if __name__ == "__main__":
    unittest.main()
