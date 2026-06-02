import json
import os
import uuid
from datetime import datetime

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase import pdfmetrics
except ImportError:
    A4 = None


FILE_NAME = "mistakes.json"
PROFILE_FILE = "learning_profile.json"
MARKDOWN_REPORT = "错题学习报告.md"
PDF_REPORT = "错题学习报告.pdf"

DEFAULT_TYPE = "未分类"
DEFAULT_KNOWLEDGE = "未识别"

KNOWLEDGE_MAP = {
    "循环结构": "循环",
    "for循环": "循环",
    "while循环": "循环",
    "string": "字符串",
    "字符串处理": "字符串",
    "STL-string": "字符串",
    "Vector": "vector",
    "STL-vector": "vector",
    "vector容器": "vector",
    "动态数组": "vector",
    "Map": "map",
    "STL-map": "map",
    "映射": "map",
    "Set": "set",
    "STL-set": "set",
    "sort": "排序",
    "sort函数": "排序",
    "二分": "二分查找",
    "binary_search": "二分查找",
    "DFS": "图",
    "BFS": "图",
}


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_knowledge(name):
    return KNOWLEDGE_MAP.get((name or "").strip(), (name or "").strip())


def _write_json(file_name, data):
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def _ensure_mistake_fields(mistakes):
    changed = False
    for mistake in mistakes:
        defaults = {
            "id": uuid.uuid4().hex,
            "favorite": False,
            "type": DEFAULT_TYPE,
            "knowledge": DEFAULT_KNOWLEDGE,
            "review_count": 0,
            "last_reviewed_at": "",
            "mastered": False,
            "time": _now(),
            "question": "",
            "code": "",
            "answer": "",
        }
        for key, value in defaults.items():
            if key not in mistake or mistake.get(key) is None:
                mistake[key] = value
                changed = True
    return changed


def load_mistakes():
    if not os.path.exists(FILE_NAME):
        return []

    try:
        with open(FILE_NAME, "r", encoding="utf-8") as f:
            mistakes = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(mistakes, list):
        return []

    if _ensure_mistake_fields(mistakes):
        _write_json(FILE_NAME, mistakes)

    return mistakes


def save_mistake(code, question, answer, error_type=DEFAULT_TYPE, knowledge=DEFAULT_KNOWLEDGE):
    mistakes = load_mistakes()
    mistake = {
        "id": uuid.uuid4().hex,
        "time": _now(),
        "type": error_type or DEFAULT_TYPE,
        "knowledge": knowledge or DEFAULT_KNOWLEDGE,
        "question": question,
        "code": code,
        "answer": answer,
        "favorite": False,
        "review_count": 0,
        "last_reviewed_at": "",
        "mastered": False,
    }
    mistakes.append(mistake)
    _write_json(FILE_NAME, mistakes)
    return mistake


def _resolve_index(mistakes, mistake_id):
    if isinstance(mistake_id, int):
        return mistake_id - 1 if 1 <= mistake_id <= len(mistakes) else None

    for index, mistake in enumerate(mistakes):
        if mistake.get("id") == str(mistake_id):
            return index
    return None


def get_mistake(mistake_id):
    mistakes = load_mistakes()
    index = _resolve_index(mistakes, mistake_id)
    if index is None:
        return None
    return mistakes[index]


def delete_mistake(mistake_id):
    mistakes = load_mistakes()
    index = _resolve_index(mistakes, mistake_id)
    if index is None:
        return False, "错题不存在。"

    mistakes.pop(index)
    _write_json(FILE_NAME, mistakes)
    return True, "删除成功。"


def favorite_mistake(mistake_id):
    mistakes = load_mistakes()
    index = _resolve_index(mistakes, mistake_id)
    if index is None:
        return False, "错题不存在。"

    mistakes[index]["favorite"] = not mistakes[index].get("favorite", False)
    _write_json(FILE_NAME, mistakes)
    return True, "已收藏该错题。" if mistakes[index]["favorite"] else "已取消收藏该错题。"


def review_mistake(mistake_id):
    mistakes = load_mistakes()
    index = _resolve_index(mistakes, mistake_id)
    if index is None:
        return False, "错题不存在。"

    mistakes[index]["review_count"] = int(mistakes[index].get("review_count", 0)) + 1
    mistakes[index]["last_reviewed_at"] = _now()
    _write_json(FILE_NAME, mistakes)
    return True, "已记录一次复习。"


def toggle_mastered_mistake(mistake_id):
    mistakes = load_mistakes()
    index = _resolve_index(mistakes, mistake_id)
    if index is None:
        return False, "错题不存在。"

    mistakes[index]["mastered"] = not mistakes[index].get("mastered", False)
    if mistakes[index]["mastered"] and not mistakes[index].get("last_reviewed_at"):
        mistakes[index]["last_reviewed_at"] = _now()
    _write_json(FILE_NAME, mistakes)
    return True, "已标记为掌握。" if mistakes[index]["mastered"] else "已改回待复习。"


def get_review_stat(mistakes=None):
    mistakes = mistakes if mistakes is not None else load_mistakes()
    mastered = sum(1 for m in mistakes if m.get("mastered", False))
    pending = len(mistakes) - mastered
    reviewed = sum(1 for m in mistakes if int(m.get("review_count", 0)) > 0)
    return {"total": len(mistakes), "pending": pending, "mastered": mastered, "reviewed": reviewed}


def _split_knowledge(knowledge):
    for item in (knowledge or "").replace("，", ",").split(","):
        item = normalize_knowledge(item)
        if item:
            yield item


def build_learning_profile():
    profile = {}
    for mistake in load_mistakes():
        for item in _split_knowledge(mistake.get("knowledge", DEFAULT_KNOWLEDGE)):
            if item != DEFAULT_KNOWLEDGE:
                profile[item] = profile.get(item, 0) + 1

    _write_json(PROFILE_FILE, profile)
    return profile


def get_weak_knowledge():
    profile = build_learning_profile()
    if not profile:
        return None
    return sorted(profile.items(), key=lambda item: item[1], reverse=True)[0][0]


def export_markdown():
    mistakes = load_mistakes()
    if not mistakes:
        return False, "暂无错题记录，无法导出 Markdown 报告。", None

    review_stat = get_review_stat(mistakes)
    with open(MARKDOWN_REPORT, "w", encoding="utf-8") as f:
        f.write("# C++ 程序设计错题学习报告\n\n")
        f.write(f"生成时间：{_now()}\n\n")
        f.write(f"错题总数：{len(mistakes)}\n")
        f.write(f"待复习：{review_stat['pending']}，已掌握：{review_stat['mastered']}，已复习：{review_stat['reviewed']}\n\n")

        f.write("## 一、错题类型统计\n\n")
        stat = {}
        for mistake in mistakes:
            error_type = mistake.get("type", DEFAULT_TYPE)
            stat[error_type] = stat.get(error_type, 0) + 1
        for error_type, count in stat.items():
            f.write(f"- {error_type}：{count} 题\n")

        f.write("\n## 二、错题详情\n\n")
        for i, mistake in enumerate(mistakes, 1):
            f.write(f"### 错题 {i}\n\n")
            f.write(f"- 记录时间：{mistake.get('time', '未知')}\n")
            f.write(f"- 错误类型：{mistake.get('type', DEFAULT_TYPE)}\n")
            f.write(f"- 涉及知识点：{mistake.get('knowledge', DEFAULT_KNOWLEDGE)}\n")
            f.write(f"- 复习次数：{mistake.get('review_count', 0)}\n")
            f.write(f"- 最近复习：{mistake.get('last_reviewed_at') or '未复习'}\n")
            f.write(f"- 掌握状态：{'已掌握' if mistake.get('mastered') else '待复习'}\n")
            f.write(f"- 问题描述：{mistake.get('question', '')}\n\n")
            f.write("#### 用户代码\n\n```cpp\n")
            f.write(mistake.get("code", ""))
            f.write("\n```\n\n#### AI 分析\n\n")
            f.write(mistake.get("answer", ""))
            f.write("\n\n---\n\n")

    return True, "Markdown 报告导出成功。", MARKDOWN_REPORT


def export_pdf():
    if A4 is None:
        return False, "PDF 导出失败：当前环境未安装 reportlab。", None

    mistakes = load_mistakes()
    if not mistakes:
        return False, "暂无错题记录，无法导出 PDF 报告。", None

    try:
        pdfmetrics.registerFont(TTFont("SimSun", "C:/Windows/Fonts/simsun.ttc"))
        doc = SimpleDocTemplate(PDF_REPORT, pagesize=A4)
        styles = getSampleStyleSheet()
        for style_name in ["Title", "Heading2", "Normal", "Code"]:
            styles[style_name].fontName = "SimSun"

        review_stat = get_review_stat(mistakes)
        story = [
            Paragraph("C++ 程序设计错题学习报告", styles["Title"]),
            Spacer(1, 12),
            Paragraph(f"生成时间：{_now()}", styles["Normal"]),
            Paragraph(f"错题总数：{len(mistakes)}", styles["Normal"]),
            Paragraph(f"待复习：{review_stat['pending']}，已掌握：{review_stat['mastered']}，已复习：{review_stat['reviewed']}", styles["Normal"]),
            Spacer(1, 12),
            Paragraph("一、错题类型统计", styles["Heading2"]),
        ]

        stat = {}
        for mistake in mistakes:
            error_type = mistake.get("type", DEFAULT_TYPE)
            stat[error_type] = stat.get(error_type, 0) + 1
        for error_type, count in stat.items():
            story.append(Paragraph(f"{error_type}：{count} 题", styles["Normal"]))

        story.extend([Spacer(1, 12), Paragraph("二、错题详情", styles["Heading2"])])
        for i, mistake in enumerate(mistakes, 1):
            story.append(Spacer(1, 12))
            story.append(Paragraph(f"错题 {i}", styles["Heading2"]))
            story.append(Paragraph(f"记录时间：{mistake.get('time', '未知')}", styles["Normal"]))
            story.append(Paragraph(f"错误类型：{mistake.get('type', DEFAULT_TYPE)}", styles["Normal"]))
            story.append(Paragraph(f"涉及知识点：{mistake.get('knowledge', DEFAULT_KNOWLEDGE)}", styles["Normal"]))
            story.append(Paragraph(f"复习次数：{mistake.get('review_count', 0)}", styles["Normal"]))
            story.append(Paragraph(f"最近复习：{mistake.get('last_reviewed_at') or '未复习'}", styles["Normal"]))
            story.append(Paragraph(f"掌握状态：{'已掌握' if mistake.get('mastered') else '待复习'}", styles["Normal"]))
            story.append(Paragraph(f"问题描述：{mistake.get('question', '')}", styles["Normal"]))
            story.append(Spacer(1, 6))
            story.append(Paragraph("用户代码：", styles["Normal"]))
            story.append(Preformatted(mistake.get("code", ""), styles["Code"]))
            story.append(Spacer(1, 6))
            story.append(Paragraph("AI 分析：", styles["Normal"]))
            story.append(Preformatted(mistake.get("answer", ""), styles["Code"]))

        doc.build(story)
        return True, "PDF 报告导出成功。", PDF_REPORT
    except Exception as e:
        return False, f"PDF 导出失败：{e}", None


def print_mistakes(mistakes):
    for i, mistake in enumerate(mistakes, 1):
        print(f"{i}. {mistake.get('question', '')}")


def show_mistakes(error_type=None):
    mistakes = load_mistakes()
    if error_type:
        mistakes = [m for m in mistakes if m.get("type", DEFAULT_TYPE) == error_type]
    print_mistakes(mistakes)


def search_mistakes(keyword):
    mistakes = [
        m for m in load_mistakes()
        if keyword in (
            m.get("question", "") +
            m.get("code", "") +
            m.get("answer", "") +
            m.get("type", "") +
            m.get("knowledge", "")
        )
    ]
    print_mistakes(mistakes)


def count_mistakes():
    print(f"当前共有 {len(load_mistakes())} 条错题记录。")


def count_by_type():
    stat = {}
    for mistake in load_mistakes():
        error_type = mistake.get("type", DEFAULT_TYPE)
        stat[error_type] = stat.get(error_type, 0) + 1
    for error_type, count in stat.items():
        print(f"{error_type}：{count} 题")


def count_by_knowledge():
    profile = build_learning_profile()
    for knowledge, count in profile.items():
        print(f"{knowledge}：{count} 题")


def favorite_mistake_by_index(index):
    ok, message = favorite_mistake(index)
    print(message)
    return ok


def delete_mistake_by_index(index):
    ok, message = delete_mistake(index)
    print(message)
    return ok


def show_favorites():
    print_mistakes([m for m in load_mistakes() if m.get("favorite", False)])


def mistake_rank():
    stat = {}
    for mistake in load_mistakes():
        error_type = mistake.get("type", DEFAULT_TYPE)
        stat[error_type] = stat.get(error_type, 0) + 1
    for i, item in enumerate(sorted(stat.items(), key=lambda x: x[1], reverse=True), 1):
        print(f"{i}. {item[0]}：{item[1]} 题")


def show_learning_profile():
    profile = build_learning_profile()
    if not profile:
        print("暂无学习画像数据，请先保存一些错题。")
        return
    for knowledge, count in sorted(profile.items(), key=lambda x: x[1], reverse=True):
        print(f"{knowledge}：出现 {count} 次")
