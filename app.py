import base64
import binascii
import os
import re
import shutil
import subprocess
import tempfile

from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for
from PIL import Image, ImageEnhance, ImageFilter

from ai_helper import (
    analyze_code,
    chat_with_history,
    coach_problem,
    explain_question,
    generate_practice_by_custom,
    generate_practice_by_knowledge,
    generate_study_advice,
    oj_analysis,
)
from conversation_store import (
    VALID_SCOPES,
    append_message,
    create_conversation,
    delete_conversation,
    find_empty_conversation,
    get_conversation,
    list_conversation_summaries,
    messages_for_model,
    normalize_scope,
)
from cpp_runner import format_run_context, format_run_result, run_cpp_code
from mistake_book import (
    DEFAULT_TYPE,
    build_learning_profile,
    delete_mistake,
    export_markdown,
    export_pdf,
    favorite_mistake,
    get_mistake,
    get_review_stat,
    get_weak_knowledge,
    load_mistakes,
    review_mistake,
    save_mistake,
    toggle_mastered_mistake,
)


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "ai-cpp-tutor-dev-secret")
MAX_IMAGE_BYTES = 4 * 1024 * 1024
ALLOWED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
IMAGE_DATA_URL_RE = re.compile(r"^data:(image/(?:png|jpeg|webp|gif));base64,([A-Za-z0-9+/=\s]+)$")
IMAGE_SUFFIXES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
OCR_LANG = os.getenv("OCR_LANG", "chi_sim+eng")
OCR_PSM = os.getenv("OCR_PSM", "6")
OCR_PSM_CANDIDATES = [item.strip() for item in os.getenv("OCR_PSM_CANDIDATES", f"{OCR_PSM},4,11,3").split(",") if item.strip()]
OCR_TIMEOUT = int(os.getenv("OCR_TIMEOUT", "20"))

SCOPE_LABELS = {
    "debug": "AI 调试",
    "ask": "知识问答",
    "oj": "OJ 分析",
    "coach": "教练模式",
    "practice": "专项练习",
    "profile": "学习建议",
}


def anchor_url(endpoint, anchor, **values):
    return url_for(endpoint, _anchor=anchor, **values)


def _current_ids():
    current_ids = session.get("current_conversation_ids")
    if not isinstance(current_ids, dict):
        old_id = session.get("current_conversation_id")
        current_ids = {"ask": old_id} if old_id else {}
        session["current_conversation_ids"] = current_ids
    return current_ids


def set_current_conversation(conversation_id, scope=None):
    conversation = get_conversation(conversation_id)
    scope = normalize_scope(scope or (conversation or {}).get("scope"))
    current_ids = _current_ids()
    current_ids[scope] = conversation_id
    session["current_conversation_ids"] = current_ids
    session["current_conversation_id"] = conversation_id
    session.modified = True


def current_conversation(scope="ask"):
    scope = normalize_scope(scope)
    current_ids = _current_ids()
    conversation_id = current_ids.get(scope)
    conversation = get_conversation(conversation_id) if conversation_id else None
    if conversation and normalize_scope(conversation.get("scope")) == scope:
        return conversation

    summaries = list_conversation_summaries(scope)
    if summaries:
        conversation = get_conversation(summaries[0]["id"])
        set_current_conversation(conversation["id"], scope)
        return conversation

    conversation = create_conversation(title="新对话", scope=scope)
    set_current_conversation(conversation["id"], scope)
    return conversation


def empty_or_new_conversation(scope="ask"):
    scope = normalize_scope(scope)
    conversation = find_empty_conversation(scope)
    reused = conversation is not None
    if not conversation:
        conversation = create_conversation(scope=scope)
    set_current_conversation(conversation["id"], scope)
    return conversation, reused


def build_conversation_state():
    state = {}
    for scope in ["debug", "ask", "oj", "coach", "practice", "profile"]:
        conversation = current_conversation(scope)
        state[scope] = {
            "label": SCOPE_LABELS[scope],
            "current": conversation,
            "conversations": list_conversation_summaries(scope),
            "messages": conversation.get("messages", []),
        }
    return state


def short_title(prefix, text):
    text = " ".join((text or "").split())
    if not text:
        return prefix
    return f"{prefix}：{text[:18]}{'...' if len(text) > 18 else ''}"


def save_result_conversation(scope, title, user_content, assistant_content, user_attachments=None):
    if not assistant_content:
        return ""
    scope = normalize_scope(scope)
    conversation = create_conversation(title, scope)
    append_message(conversation["id"], "user", user_content, user_attachments)
    append_message(conversation["id"], "assistant", assistant_content)
    set_current_conversation(conversation["id"], scope)
    return conversation["id"]


def wants_code_comments(source):
    return source.get("include_comments") == "on" or source.get("include_comments") is True


def parse_image_attachments(raw_attachments):
    attachments = []
    if not raw_attachments:
        return True, attachments, ""
    if not isinstance(raw_attachments, list):
        return False, attachments, "图片数据格式不正确。"
    if len(raw_attachments) > 1:
        return False, attachments, "一次最多上传 1 张图片。"

    for raw in raw_attachments:
        if not isinstance(raw, dict):
            return False, attachments, "图片数据格式不正确。"
        data_url = raw.get("data_url") or ""
        if not isinstance(data_url, str):
            return False, attachments, "图片数据格式不正确。"
        match = IMAGE_DATA_URL_RE.match(data_url)
        if not match:
            return False, attachments, "仅支持 PNG、JPG、WebP 或 GIF 图片。"
        mime_type, payload = match.groups()
        payload = "".join(payload.split())
        if mime_type not in ALLOWED_IMAGE_MIME_TYPES:
            return False, attachments, "图片类型不受支持。"
        try:
            image_bytes = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError):
            return False, attachments, "图片数据无法解析。"
        if len(image_bytes) > MAX_IMAGE_BYTES:
            return False, attachments, "图片不能超过 4MB。"
        attachments.append({
            "type": "image",
            "mime_type": mime_type,
            "name": str(raw.get("name") or "uploaded-image")[:120],
            "size": len(image_bytes),
            "data_url": f"data:{mime_type};base64,{payload.strip()}",
        })
    return True, attachments, ""


def parse_form_image_attachment(form):
    data_url = (form.get("image_data_url") or "").strip()
    if not data_url:
        return True, [], ""
    return parse_image_attachments([{
        "type": "image",
        "name": form.get("image_name") or "uploaded-image",
        "data_url": data_url,
    }])


def tesseract_command():
    configured = os.getenv("TESSERACT_CMD")
    if configured and os.path.exists(configured):
        return configured
    found = shutil.which("tesseract")
    if found:
        return found
    for path in [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]:
        if os.path.exists(path):
            return path
    return None


def preprocess_image_for_ocr(source_path):
    with Image.open(source_path) as image:
        image = image.convert("RGB")
        width, height = image.size
        scale = max(1.0, min(3.0, 1600 / max(width, 1)))
        if scale > 1:
            image = image.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)

        image = image.convert("L")
        image = ImageEnhance.Contrast(image).enhance(1.8)
        image = ImageEnhance.Sharpness(image).enhance(1.6)
        image = image.filter(ImageFilter.MedianFilter(size=3))
        image = image.point(lambda pixel: 255 if pixel > 172 else 0)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            image.save(tmp.name, "PNG")
            return tmp.name


def score_ocr_text(text):
    useful = sum(1 for char in text if char.isalnum() or "\u4e00" <= char <= "\u9fff")
    code_symbols = sum(1 for char in text if char in "{}[]();#<>+-=*/_&|.:,\"'")
    lines = len([line for line in text.splitlines() if line.strip()])
    return useful + code_symbols * 0.45 + lines * 2


def run_tesseract(command, image_path, psm):
    return subprocess.run(
        [command, image_path, "stdout", "-l", OCR_LANG, "--psm", psm, "--oem", "1", "-c", "preserve_interword_spaces=1"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=OCR_TIMEOUT,
    )


def extract_text_from_image_attachment(attachment):
    command = tesseract_command()
    if not command:
        return False, "", (
            "图片已上传，但本机没有找到 Tesseract OCR。请先安装 Tesseract，"
            "并确保 tesseract 命令在 PATH 中，或在 .env 中配置 TESSERACT_CMD。"
        )

    data_url = attachment.get("data_url", "")
    match = IMAGE_DATA_URL_RE.match(data_url)
    if not match:
        return False, "", "图片数据格式不正确，无法 OCR。"
    mime_type, payload = match.groups()
    payload = "".join(payload.split())
    suffix = IMAGE_SUFFIXES.get(mime_type, ".png")

    tmp_path = None
    processed_path = None
    try:
        image_bytes = base64.b64decode(payload, validate=True)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        processed_path = preprocess_image_for_ocr(tmp_path)
        candidates = []
        last_error = ""
        for psm in OCR_PSM_CANDIDATES:
            result = run_tesseract(command, processed_path, psm)
            text = (result.stdout or "").strip()
            if result.returncode == 0 and text:
                candidates.append((score_ocr_text(text), text, psm))
            elif result.returncode != 0:
                last_error = (result.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return False, "", "OCR 识别超时，请换一张更清晰或更小的图片。"
    except (OSError, ValueError, binascii.Error) as e:
        return False, "", f"OCR 识别失败：{e}"
    finally:
        for path in [tmp_path, processed_path]:
            if not path:
                continue
            try:
                os.remove(path)
            except OSError:
                pass

    if not candidates:
        if last_error:
            return False, "", f"OCR 识别失败：{last_error}"
        return False, "", "OCR 没有识别出文字，请上传更清晰的图片。"
    _, text, best_psm = max(candidates, key=lambda item: item[0])
    text = f"{text}\n\n[OCR 参数：lang={OCR_LANG}, psm={best_psm}]"
    return True, text, ""


def enrich_question_with_ocr(question, attachments):
    if not attachments:
        return True, question, attachments, ""

    ocr_sections = []
    for index, attachment in enumerate(attachments, 1):
        ok, text, error = extract_text_from_image_attachment(attachment)
        if not ok:
            return False, question, attachments, error
        attachment["ocr_text"] = text
        name = attachment.get("name") or f"图片 {index}"
        ocr_sections.append(f"### {name}\n{text}")

    original_question = question or "请根据图片 OCR 识别出的文字进行解答。"
    ocr_text = "\n\n".join(ocr_sections)
    enriched = (
        f"{original_question}\n\n"
        "下面是用户上传图片经过 OCR 识别得到的文字。"
        "请基于这些文字回答；如果你判断 OCR 可能把 C++ 代码、符号或题目条件识别错了，"
        "请先指出可能的识别误差，再给出解答。\n\n"
        "```text\n"
        f"{ocr_text}\n"
        "```"
    )
    return True, enriched, attachments, ""


def enrich_form_text_with_ocr(text, form):
    ok, attachments, attachment_error = parse_form_image_attachment(form)
    if not ok:
        return False, text, attachments, attachment_error
    if not attachments:
        return True, text, attachments, ""
    return enrich_question_with_ocr(text, attachments)


def get_type_stat(mistakes):
    stat = {}
    for mistake in mistakes:
        error_type = mistake.get("type", DEFAULT_TYPE)
        stat[error_type] = stat.get(error_type, 0) + 1
    return stat


def get_mistake_rank(mistakes):
    return sorted(get_type_stat(mistakes).items(), key=lambda x: x[1], reverse=True)


def filter_mistakes(mistakes, keyword, error_type, show_fav, review_filter):
    display_mistakes = mistakes

    if keyword:
        display_mistakes = [
            m for m in display_mistakes
            if keyword in (
                m.get("question", "") +
                m.get("code", "") +
                m.get("answer", "") +
                m.get("type", "") +
                m.get("knowledge", "")
            )
        ]

    if error_type:
        display_mistakes = [m for m in display_mistakes if m.get("type", DEFAULT_TYPE) == error_type]
    if show_fav == "1":
        display_mistakes = [m for m in display_mistakes if m.get("favorite", False)]
    if review_filter == "pending":
        display_mistakes = [m for m in display_mistakes if not m.get("mastered", False)]
    elif review_filter == "mastered":
        display_mistakes = [m for m in display_mistakes if m.get("mastered", False)]
    elif review_filter == "unreviewed":
        display_mistakes = [m for m in display_mistakes if int(m.get("review_count", 0)) == 0]

    return display_mistakes


@app.route("/", methods=["GET", "POST"])
def index():
    result = ""
    result_conversation_id = ""
    result_scope = ""
    notice = request.args.get("notice", "")
    search_keyword = request.args.get("keyword", "")
    filter_type = request.args.get("type", "")
    show_fav = request.args.get("fav", "")
    review_filter = request.args.get("review", "")

    mistakes = load_mistakes()
    profile = build_learning_profile()

    if request.method == "POST":
        action = request.form.get("action")
        include_comments = wants_code_comments(request.form)

        if action in ["debug", "run_cpp"]:
            code = request.form.get("code", "")
            question = request.form.get("question", "")
            stdin_text = request.form.get("stdin", "")
            attachments = []
            if action == "debug":
                ok, question, attachments, ocr_error = enrich_form_text_with_ocr(question, request.form)
                if not ok:
                    result = ocr_error
                    result_scope = "debug"
                    result_conversation_id = save_result_conversation("debug", short_title("AI 调试", question or code), question, result, attachments)
                    notice = ocr_error
            run_local = action == "run_cpp" or request.form.get("run_local") == "on"
            local_result = run_cpp_code(code, stdin_text) if run_local else None
            local_display = format_run_result(local_result) if local_result else ""
            result_scope = "debug"

            if action == "run_cpp":
                result = local_display
                user_content = f"请记录并解释这段 C++ 本地运行结果。\n\n标准输入：\n{stdin_text}\n\n代码：\n```cpp\n{code}\n```"
                result_conversation_id = save_result_conversation("debug", "本地运行：C++ 代码", user_content, result)
            elif not result:
                compiler_context = format_run_context(local_result) if local_result else ""
                analysis = analyze_code(code, question, compiler_context, include_comments)
                result = local_display + "\n\n---\n\n" + analysis["display"] if local_display else analysis["display"]
                user_content = f"请分析这段 C++ 代码。\n\n问题：{question}\n\n标准输入：\n{stdin_text}\n\n代码：\n```cpp\n{code}\n```"
                result_conversation_id = save_result_conversation("debug", short_title("AI 调试", question or code), user_content, result, attachments)

                if request.form.get("save") == "on":
                    knowledge = ",".join(analysis["knowledge_points"]) or "未识别"
                    save_mistake(code, question, result, analysis["error_type"], knowledge)
                    notice = "已保存到错题本。"

        elif action == "explain":
            question = request.form.get("explain_question", "")
            result_scope = "ask"
            ok, attachments, attachment_error = parse_form_image_attachment(request.form)
            if not ok:
                result = attachment_error
                notice = attachment_error
                result_conversation_id = save_result_conversation("ask", short_title("知识问答", question), question, result)
            else:
                if attachments:
                    ok, question, attachments, ocr_error = enrich_question_with_ocr(question, attachments)
                    if not ok:
                        result = ocr_error
                        notice = ocr_error
                    else:
                        result = explain_question(question, include_comments)
                    result_conversation_id = save_result_conversation("ask", short_title("知识问答", question), question, result, attachments)
                else:
                    result = explain_question(question, include_comments)
                    result_conversation_id = save_result_conversation("ask", short_title("知识问答", question), question, result)

        elif action == "oj":
            problem = request.form.get("problem", "")
            code = request.form.get("oj_code", "")
            result_scope = "oj"
            ok, problem, attachments, ocr_error = enrich_form_text_with_ocr(problem, request.form)
            if not ok:
                result = ocr_error
                notice = ocr_error
            else:
                result = oj_analysis(problem, code, include_comments)
            user_content = f"请分析这道 OJ 题和我的代码。\n\n题目：\n{problem}\n\n代码：\n```cpp\n{code}\n```"
            result_conversation_id = save_result_conversation("oj", short_title("OJ 分析", problem), user_content, result, attachments)

        elif action == "coach":
            problem = request.form.get("coach_problem", "")
            code = request.form.get("coach_code", "")
            result_scope = "coach"
            ok, problem, attachments, ocr_error = enrich_form_text_with_ocr(problem, request.form)
            if not ok:
                result = ocr_error
                notice = ocr_error
            else:
                result = coach_problem(problem, code, include_comments)
            user_content = f"请用教练模式提示我这道题。\n\n题目：\n{problem}\n\n我的代码：\n```cpp\n{code}\n```"
            result_conversation_id = save_result_conversation("coach", short_title("教练模式", problem), user_content, result, attachments)

        elif action == "practice":
            weak = get_weak_knowledge()
            if weak is None:
                result = "暂无学习画像数据，请先保存一些错题。"
            else:
                result = generate_practice_by_knowledge(weak, include_comments)
                user_content = f"请根据我的薄弱知识点“{weak}”生成 C++ 专项练习。"
                result_scope = "practice"
                result_conversation_id = save_result_conversation("practice", short_title("专项练习", weak), user_content, result)

        elif action == "custom_practice":
            topic = request.form.get("custom_topic", "")
            difficulty = request.form.get("custom_difficulty", "基础")
            count = request.form.get("custom_count", "3")
            ok, topic, attachments, ocr_error = enrich_form_text_with_ocr(topic, request.form)
            if not ok:
                result = ocr_error
                notice = ocr_error
                result_scope = "practice"
                result_conversation_id = save_result_conversation("practice", short_title("自定义练习", topic), topic, result, attachments)
            elif topic.strip() == "":
                result = "请输入你想练习的题目内容。"
                result_scope = "practice"
            else:
                result = generate_practice_by_custom(topic, difficulty, count, include_comments)
                user_content = f"请围绕“{topic}”生成 {count} 道 {difficulty} 难度的 C++ 练习题。"
                result_scope = "practice"
                result_conversation_id = save_result_conversation("practice", short_title("自定义练习", topic), user_content, result, attachments)

        elif action == "advice":
            if not mistakes:
                result = "暂无错题记录，无法生成学习建议。"
            else:
                stat_text = "\n".join(f"{error_type}：{count} 题" for error_type, count in get_type_stat(mistakes).items())
                result = generate_study_advice(stat_text)
                result_scope = "profile"
                result_conversation_id = save_result_conversation("profile", "学习建议", f"请根据错题统计生成学习建议：\n{stat_text}", result)

        mistakes = load_mistakes()
        profile = build_learning_profile()

    display_mistakes = filter_mistakes(mistakes, search_keyword, filter_type, show_fav, review_filter)
    conversation_state = build_conversation_state()

    return render_template(
        "index.html",
        result=result,
        result_conversation_id=result_conversation_id,
        result_scope=result_scope,
        notice=notice,
        conversation_state=conversation_state,
        current_conversation_ids={scope: data["current"]["id"] for scope, data in conversation_state.items()},
        mistakes=mistakes,
        display_mistakes=display_mistakes,
        profile=profile,
        type_stat=get_type_stat(mistakes),
        rank=get_mistake_rank(mistakes),
        review_stat=get_review_stat(mistakes),
        search_keyword=search_keyword,
        filter_type=filter_type,
        show_fav=show_fav,
        review_filter=review_filter,
    )


@app.get("/api/conversations")
def api_conversations():
    scope = normalize_scope(request.args.get("scope", "ask"))
    return jsonify({
        "ok": True,
        "scope": scope,
        "conversations": list_conversation_summaries(scope),
        "current_id": _current_ids().get(scope),
    })


@app.post("/api/conversations")
def api_create_conversation():
    data = request.get_json(silent=True) or {}

    scope = normalize_scope(data.get("scope") or request.args.get("scope", "ask"))
    conversation, reused = empty_or_new_conversation(scope)
    return jsonify({
        "ok": True,
        "reused": reused,
        "message": "已存在空白新对话，已切换到该对话。" if reused else "已新建对话。",
        "conversation": conversation,
        "conversations": list_conversation_summaries(scope),
    })


@app.get("/api/conversations/<conversation_id>")
def api_get_conversation(conversation_id):
    conversation = get_conversation(conversation_id)
    if not conversation:
        return jsonify({"ok": False, "message": "对话不存在。"}), 404
    scope = normalize_scope(conversation.get("scope"))
    set_current_conversation(conversation_id, scope)
    return jsonify({
        "ok": True,
        "conversation": conversation,
        "conversations": list_conversation_summaries(scope),
    })


@app.post("/api/conversations/<conversation_id>/chat")
def api_conversation_chat(conversation_id):
    data = request.get_json(silent=True) or {}
    question = (data.get("message") or "").strip()
    ok, attachments, attachment_error = parse_image_attachments(data.get("attachments"))
    if not ok:
        return jsonify({"ok": False, "message": attachment_error}), 400
    include_comments = wants_code_comments(data)
    if not question and not attachments:
        return jsonify({"ok": False, "message": "请输入问题。"}), 400
    if attachments:
        ok, question, attachments, ocr_error = enrich_question_with_ocr(question, attachments)
        if not ok:
            return jsonify({"ok": False, "message": ocr_error}), 400

    scope = normalize_scope(data.get("scope") or request.args.get("scope", "ask"))
    conversation = get_conversation(conversation_id)
    if not conversation:
        conversation = create_conversation(scope=scope)
        conversation_id = conversation["id"]
    else:
        scope = normalize_scope(conversation.get("scope"))

    set_current_conversation(conversation_id, scope)
    conversation = append_message(conversation_id, "user", question, attachments)
    answer = chat_with_history(messages_for_model(conversation), include_comments)
    conversation = append_message(conversation_id, "assistant", answer)

    return jsonify({
        "ok": True,
        "answer": answer,
        "conversation": conversation,
        "conversations": list_conversation_summaries(scope),
    })


@app.delete("/api/conversations/<conversation_id>")
def api_delete_conversation(conversation_id):
    conversation = get_conversation(conversation_id)
    if not conversation:
        return jsonify({"ok": False, "message": "对话不存在。"}), 404
    scope = normalize_scope(conversation.get("scope"))
    delete_conversation(conversation_id)

    if _current_ids().get(scope) == conversation_id:
        next_conversation, _ = empty_or_new_conversation(scope)
    else:
        next_conversation = current_conversation(scope)

    return jsonify({
        "ok": True,
        "message": "对话已删除。",
        "conversation": next_conversation,
        "conversations": list_conversation_summaries(scope),
    })


@app.post("/api/chat")
def api_chat():
    data = request.get_json(silent=True) or {}
    scope = normalize_scope(data.get("scope") or request.args.get("scope", "ask"))
    conversation = current_conversation(scope)
    return api_conversation_chat(conversation["id"])


@app.post("/api/chat/clear")
def api_chat_clear():
    data = request.get_json(silent=True) or {}
    scope = normalize_scope(data.get("scope") or request.args.get("scope", "ask"))
    conversation, reused = empty_or_new_conversation(scope)
    return jsonify({
        "ok": True,
        "reused": reused,
        "message": "已存在空白新对话，已切换到该对话。" if reused else "已新建空白对话。",
        "conversation": conversation,
        "conversations": list_conversation_summaries(scope),
    })


def api_response(ok, message, mistake_id=None):
    mistakes = load_mistakes()
    data = {
        "ok": ok,
        "message": message,
        "review_stat": get_review_stat(mistakes),
        "type_stat": get_type_stat(mistakes),
        "rank": get_mistake_rank(mistakes),
    }
    if mistake_id:
        data["mistake"] = get_mistake(mistake_id)
    return jsonify(data), 200 if ok else 404


@app.route("/delete/<mistake_id>")
def delete(mistake_id):
    ok, message = delete_mistake(mistake_id)
    return redirect(anchor_url("index", "mistakes", notice=message))


@app.route("/favorite/<mistake_id>")
def favorite(mistake_id):
    ok, message = favorite_mistake(mistake_id)
    return redirect(anchor_url("index", "mistakes", notice=message))


@app.route("/review/<mistake_id>")
def review(mistake_id):
    ok, message = review_mistake(mistake_id)
    return redirect(anchor_url("index", "mistakes", notice=message))


@app.route("/mastered/<mistake_id>")
def mastered(mistake_id):
    ok, message = toggle_mastered_mistake(mistake_id)
    return redirect(anchor_url("index", "mistakes", notice=message))


@app.post("/api/favorite/<mistake_id>")
def api_favorite(mistake_id):
    ok, message = favorite_mistake(mistake_id)
    return api_response(ok, message, mistake_id)


@app.post("/api/review/<mistake_id>")
def api_review(mistake_id):
    ok, message = review_mistake(mistake_id)
    return api_response(ok, message, mistake_id)


@app.post("/api/mastered/<mistake_id>")
def api_mastered(mistake_id):
    ok, message = toggle_mastered_mistake(mistake_id)
    return api_response(ok, message, mistake_id)


@app.post("/api/delete/<mistake_id>")
def api_delete(mistake_id):
    ok, message = delete_mistake(mistake_id)
    return api_response(ok, message)


@app.route("/export_md")
def export_md():
    ok, message, file_path = export_markdown()
    if not ok:
        return redirect(anchor_url("index", "mistakes", notice=message))
    return send_file(file_path, as_attachment=True)


@app.route("/export_pdf")
def export_pdf_file():
    ok, message, file_path = export_pdf()
    if not ok:
        return redirect(anchor_url("index", "mistakes", notice=message))
    return send_file(file_path, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
