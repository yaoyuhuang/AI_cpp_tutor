import json
import os
import re

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


load_dotenv()

API_KEY = os.getenv("DEEPSEEK_API_KEY")
API_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
client = OpenAI(api_key=API_KEY, base_url=API_BASE_URL) if OpenAI and API_KEY else None
CHAT_MODEL = os.getenv("DEEPSEEK_CHAT_MODEL", "deepseek-chat")
DEEPSEEK_THINKING = os.getenv("DEEPSEEK_THINKING", "").strip()
DEEPSEEK_REASONING_EFFORT = os.getenv("DEEPSEEK_REASONING_EFFORT", "").strip()


def apply_model_options(kwargs):
    if DEEPSEEK_THINKING:
        kwargs.setdefault("extra_body", {})["thinking"] = {"type": DEEPSEEK_THINKING}
    if DEEPSEEK_REASONING_EFFORT:
        kwargs["reasoning_effort"] = DEEPSEEK_REASONING_EFFORT
    return kwargs

ERROR_TYPES = [
    "语法错误",
    "运行错误",
    "逻辑错误",
    "输入输出格式错误",
    "边界条件错误",
    "未发现明显错误",
]

KNOWLEDGE_POINTS = [
    "变量",
    "输入输出",
    "选择结构",
    "循环",
    "函数",
    "数组",
    "字符串",
    "结构体",
    "vector",
    "map",
    "set",
    "栈",
    "队列",
    "链表",
    "树",
    "图",
    "排序",
    "查找",
    "递归",
    "二分查找",
    "贪心",
    "动态规划",
    "文件操作",
]


def code_comment_instruction(include_comments=False):
    if include_comments:
        return "代码示例或修复代码需要保留必要注释，注释要简短、解释关键思路，不要逐行啰嗦。"
    return "代码示例或修复代码不要包含注释，保持代码简洁。"


def call_deepseek(prompt, system_prompt="你是一名专业的 C++ 程序设计辅导老师。", temperature=0.3, json_mode=False):
    if not API_KEY:
        return "API 调用失败：未配置 DEEPSEEK_API_KEY。"
    if not client:
        return "API 调用失败：当前环境未安装 openai 包。"

    try:
        kwargs = {
            "model": CHAT_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        apply_model_options(kwargs)
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
    except Exception as e:
        return f"API 调用失败：{str(e)}"


def chat_with_history(history, include_comments=False):
    if not API_KEY:
        return "API 调用失败：未配置 DEEPSEEK_API_KEY。"
    if not client:
        return "API 调用失败：当前环境未安装 openai 包。"

    messages = [
        {
            "role": "system",
            "content": (
                "你是一名耐心的 C++ 程序设计学习辅导老师。"
                "请结合上下文连续答疑，回答要适合初学者，尽量给出简短代码例子。"
                "如果学生追问中的“这个、它、上面”指代不明确，请根据最近上下文推断。"
                + code_comment_instruction(include_comments)
            ),
        }
    ]
    for message in history:
        messages.append({
            "role": message.get("role", "user"),
            "content": message.get("content", ""),
        })

    try:
        response = client.chat.completions.create(
            **apply_model_options({
                "model": CHAT_MODEL,
                "messages": messages,
                "temperature": 0.3,
            })
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"API 调用失败：{str(e)}"


def _extract_json(text):
    if not text or text.startswith("API 调用失败"):
        return None

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _normalize_debug_data(data, raw_text=""):
    data = data or {}
    error_type = data.get("error_type", "未分类")
    if error_type not in ERROR_TYPES:
        error_type = "未分类"

    knowledge_points = data.get("knowledge_points", [])
    if isinstance(knowledge_points, str):
        knowledge_points = [item.strip() for item in knowledge_points.split(",") if item.strip()]
    if not isinstance(knowledge_points, list):
        knowledge_points = []

    normalized = []
    for point in knowledge_points:
        if point in KNOWLEDGE_POINTS and point not in normalized:
            normalized.append(point)

    tests = data.get("tests", [])
    if not isinstance(tests, list):
        tests = []

    return {
        "error_type": error_type,
        "knowledge_points": normalized,
        "analysis": data.get("analysis", raw_text or "AI 未返回有效分析。"),
        "suggestion": data.get("suggestion", ""),
        "fixed_code": data.get("fixed_code", "无需修改"),
        "tests": tests,
        "raw": raw_text,
    }


def format_debug_result(data):
    knowledge = ",".join(data["knowledge_points"]) if data["knowledge_points"] else "未识别"
    parts = [
        "## AI 调试分析",
        "",
        "### 错误类型",
        data["error_type"],
        "",
        "### 涉及知识点",
        knowledge,
        "",
        "### 问题分析",
        data["analysis"],
        "",
        "### 修改建议",
        data["suggestion"] or "暂无",
        "",
        "### 修复后的代码",
        "```cpp",
        data["fixed_code"] or "无需修改",
        "```",
    ]

    if data["tests"]:
        parts.extend(["", "### 测试样例"])
        for i, test in enumerate(data["tests"], 1):
            if isinstance(test, dict):
                parts.extend([
                    f"{i}. 输入：{test.get('input', '无')}",
                    f"   预期输出：{test.get('expected_output', '无')}",
                    f"   测试目的：{test.get('purpose', '未说明')}",
                ])
            else:
                parts.append(f"{i}. {test}")

    return "\n".join(parts)


def analyze_code(code, question, compiler_context="", include_comments=False):
    compiler_section = ""
    if compiler_context:
        compiler_section = f"""

下面是系统已经在本地对代码进行编译运行得到的真实结果。请优先结合这些信息分析：
{compiler_context}
"""

    prompt = f"""
请分析下面的 C++ 代码和用户问题。
你必须只返回 JSON，不要返回 Markdown，不要包裹代码块。JSON 字段如下：
{{
  "error_type": "只能从 {ERROR_TYPES} 中选择一个",
  "knowledge_points": ["只能从 {KNOWLEDGE_POINTS} 中选择，允许多个"],
  "analysis": "详细分析问题原因，若有本地编译运行结果，必须结合该结果说明",
  "suggestion": "给出修改方法",
  "fixed_code": "如果需要修改，给出完整修复代码；如果无需修改，写无需修改",
  "tests": [
    {{"input": "输入", "expected_output": "预期输出", "purpose": "测试目的"}}
  ]
}}

用户问题：
{question}
{compiler_section}

C++ 代码：
{code}

{code_comment_instruction(include_comments)}
"""

    raw = call_deepseek(prompt, json_mode=True)
    parsed = _extract_json(raw)
    data = _normalize_debug_data(parsed, raw)
    data["display"] = format_debug_result(data)
    return data


def ask_ai(code, question):
    return analyze_code(code, question)["display"]


def generate_study_advice(stat_text):
    prompt = f"""
你是一名 C++ 学习辅导老师。
下面是学生的错题统计结果：
{stat_text}

请生成一份简短学习建议，包括：
1. 主要薄弱点
2. 需要重点复习的知识点
3. 后续练习建议
"""
    return call_deepseek(prompt)


def oj_analysis(problem, code, include_comments=False):
    prompt = f"""
你是一名 ACM/OJ 竞赛辅导老师。
请根据题目描述和学生代码，分析代码可能无法通过 OJ 的原因。
必须包括：
1. 题意理解
2. 可能错误
3. 边界情况
4. 时间复杂度分析
5. 修改建议
6. 修复后的代码

题目描述：
{problem}

学生代码：
{code}

{code_comment_instruction(include_comments)}
"""
    return call_deepseek(prompt)


def explain_question(question, include_comments=False):
    prompt = f"""
请详细回答学生的 C++ 问题：
{question}

要求：
1. 先解释相关概念
2. 给出 C++ 代码示例
3. 说明常见错误
4. 给出实际应用场景
5. 语言通俗易懂，适合初学者
{code_comment_instruction(include_comments)}
"""
    return call_deepseek(prompt, system_prompt="你是一名耐心的 C++ 程序设计学习辅导老师。")


def coach_problem(problem, code, include_comments=False):
    prompt = f"""
你是一名 C++ 程序设计教练。
不要直接给完整答案。
请按下面格式输出：

【第一层提示】只给思路方向

【第二层提示】指出可能使用的数据结构或算法

【第三层提示】给出关键代码框架

题目：
{problem}

学生代码：
{code}

{code_comment_instruction(include_comments)}
"""
    return call_deepseek(prompt)


def generate_practice_by_knowledge(knowledge, include_comments=False):
    prompt = f"""
你是一名 C++ 程序设计出题老师。
请根据学生的薄弱知识点生成专项练习题。
薄弱知识点：
{knowledge}

请生成 3 道 C++ 练习题：基础题、提高题、综合题。
每道题必须包含题目名称、题目描述、输入格式、输出格式、样例输入、样例输出、考查知识点、解题提示。
不要直接给完整答案代码。题目难度适合 C++ 初学者。
{code_comment_instruction(include_comments)}
"""
    return call_deepseek(prompt)


def generate_practice_by_custom(topic, difficulty, count, include_comments=False):
    prompt = f"""
你是一名 C++ 程序设计出题老师。
请根据用户指定内容生成 C++ 练习题。
用户指定题目内容：{topic}

题目难度：{difficulty}

题目数量：{count}

每道题必须包含题目名称、题目描述、输入格式、输出格式、样例输入、样例输出、考查知识点、解题提示。
不要直接给完整答案代码。题目适合 C++ 初学者。
{code_comment_instruction(include_comments)}
"""
    return call_deepseek(prompt)
