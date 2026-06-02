import shutil
import subprocess
import tempfile
from pathlib import Path


COMPILE_TIMEOUT_SECONDS = 10
RUN_TIMEOUT_SECONDS = 3


def find_cpp_compiler():
    for name in ["g++", "clang++"]:
        path = shutil.which(name)
        if path:
            return path
    return None


def run_cpp_code(code, stdin_text=""):
    compiler = find_cpp_compiler()
    if not compiler:
        return {
            "ok": False,
            "stage": "compiler",
            "message": "未找到 C++ 编译器。请先安装 g++ 或 clang++，并把它加入 PATH。",
            "compiler": "",
            "compile_stdout": "",
            "compile_stderr": "",
            "run_stdout": "",
            "run_stderr": "",
            "return_code": None,
        }

    with tempfile.TemporaryDirectory(prefix="ai_cpp_tutor_") as temp_dir:
        temp_path = Path(temp_dir)
        source_path = temp_path / "main.cpp"
        exe_path = temp_path / "main.exe"
        source_path.write_text(code, encoding="utf-8")

        compile_cmd = [
            compiler,
            str(source_path),
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-O2",
            "-o",
            str(exe_path),
        ]

        try:
            compile_result = subprocess.run(
                compile_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=COMPILE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "stage": "compile",
                "message": f"编译超时，超过 {COMPILE_TIMEOUT_SECONDS} 秒。",
                "compiler": compiler,
                "compile_stdout": "",
                "compile_stderr": "",
                "run_stdout": "",
                "run_stderr": "",
                "return_code": None,
            }

        if compile_result.returncode != 0:
            return {
                "ok": False,
                "stage": "compile",
                "message": "编译失败。",
                "compiler": compiler,
                "compile_stdout": compile_result.stdout,
                "compile_stderr": compile_result.stderr,
                "run_stdout": "",
                "run_stderr": "",
                "return_code": compile_result.returncode,
            }

        try:
            run_result = subprocess.run(
                [str(exe_path)],
                input=stdin_text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=RUN_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "stage": "run",
                "message": f"运行超时，超过 {RUN_TIMEOUT_SECONDS} 秒。可能存在死循环或等待输入。",
                "compiler": compiler,
                "compile_stdout": compile_result.stdout,
                "compile_stderr": compile_result.stderr,
                "run_stdout": "",
                "run_stderr": "",
                "return_code": None,
            }

        return {
            "ok": run_result.returncode == 0,
            "stage": "run",
            "message": "运行成功。" if run_result.returncode == 0 else "程序运行结束，但返回了非 0 状态码。",
            "compiler": compiler,
            "compile_stdout": compile_result.stdout,
            "compile_stderr": compile_result.stderr,
            "run_stdout": run_result.stdout,
            "run_stderr": run_result.stderr,
            "return_code": run_result.returncode,
        }


def format_run_result(result):
    parts = [
        "## 本地编译运行结果",
        "",
        f"- 编译器：`{result.get('compiler') or '未找到'}`",
        f"- 阶段：{result.get('stage')}",
        f"- 状态：{result.get('message')}",
    ]

    if result.get("return_code") is not None:
        parts.append(f"- 返回码：{result['return_code']}")

    sections = [
        ("编译标准输出", result.get("compile_stdout")),
        ("编译错误输出", result.get("compile_stderr")),
        ("运行标准输出", result.get("run_stdout")),
        ("运行错误输出", result.get("run_stderr")),
    ]

    for title, content in sections:
        if content:
            parts.extend(["", f"### {title}", "", "```text", content.rstrip(), "```"])

    return "\n".join(parts)


def format_run_context(result):
    if not result:
        return ""

    return f"""
本地编译运行结果：
阶段：{result.get('stage')}
状态：{result.get('message')}
返回码：{result.get('return_code')}
编译标准输出：{result.get('compile_stdout') or ''}
编译错误输出：{result.get('compile_stderr') or ''}
运行标准输出：{result.get('run_stdout') or ''}
运行错误输出：{result.get('run_stderr') or ''}
"""
