from ai_helper import ask_ai, generate_study_advice, oj_analysis, explain_question, coach_problem, generate_practice_by_knowledge, generate_practice_by_custom
from mistake_book import (
    save_mistake,
    show_mistakes,
    delete_mistake,
    count_mistakes,
    search_mistakes,
    count_by_type,
    export_markdown,
    export_pdf,
    count_by_knowledge,
    favorite_mistake,
    show_favorites,
    mistake_rank,
    load_mistakes,
    show_learning_profile,
    get_weak_knowledge
)


def get_error_type(answer):
    types = [
        "语法错误",
        "运行错误",
        "逻辑错误",
        "输入输出格式错误",
        "边界条件错误",
        "未发现明显错误"
    ]

    for t in types:
        if t in answer:
            return t

    return "未分类"


def get_knowledge(answer):
    if "【涉及知识点】" in answer:
        part = answer.split("【涉及知识点】")[1]

        if "【问题分析】" in part:
            part = part.split("【问题分析】")[0]

        return part.strip()

    return "未识别"


def input_multiline(title):
    print(title)
    print("输入 END 表示结束：")

    lines = []

    while True:
        line = input()
        if line == "END":
            break
        lines.append(line)

    return "\n".join(lines)


def main():
    while True:
        print("\n====== 面向C++程序设计学习的AI调试与错题辅导助手 ======")
        print("1. AI调试C++代码")
        print("2. 查看错题本")
        print("3. 删除错题")
        print("4. 统计错题数量")
        print("5. 按关键字搜索错题")
        print("6. 统计各类型错题数量")
        print("7. 导出Markdown学习报告")
        print("8. 统计知识点")
        print("9. 收藏错题")
        print("10. 查看收藏错题")
        print("11. 错题排行榜")
        print("12. AI生成学习建议")
        print("13. OJ专项分析")
        print("14. 导出PDF学习报告")
        print("15. AI知识问答")
        print("16. 查看学习画像")
        print("17. AI专项出题")
        print("18. AI教练模式")
        print("19. 人工指定内容出题")
        print("0. 退出")

        choice = input("请选择功能：")

        if choice == "1":
            code = input_multiline("\n请输入你的C++代码：")

            question = input("请输入你遇到的问题：")

            answer = ask_ai(code, question)

            print("\n===== AI分析结果 =====")
            print(answer)

            save = input("是否保存到错题本？y/n：")

            if save.lower() == "y":
                error_type = get_error_type(answer)
                knowledge = get_knowledge(answer)

                print("AI自动判断错误类型：", error_type)
                print("AI自动识别知识点：", knowledge)

                save_mistake(code, question, answer, error_type, knowledge)

                print("已保存到错题本。")

        elif choice == "2":
            print("\n1. 查看全部错题")
            print("2. 按错误类型查看")

            sub_choice = input("请选择：")

            if sub_choice == "1":
                show_mistakes()

            elif sub_choice == "2":
                print("\n可选类型：")
                print("语法错误、运行错误、逻辑错误、输入输出格式错误、边界条件错误、未发现明显错误、未分类")

                error_type = input("请输入错误类型：")
                show_mistakes(error_type)

            else:
                print("输入错误。")

        elif choice == "3":
            show_mistakes()

            try:
                index = int(input("请输入要删除的错题编号："))
                delete_mistake(index)
            except ValueError:
                print("请输入数字编号。")

        elif choice == "4":
            count_mistakes()

        elif choice == "5":
            keyword = input("请输入搜索关键字：")
            search_mistakes(keyword)

        elif choice == "6":
            count_by_type()

        elif choice == "7":
            export_markdown()

        elif choice == "8":
            count_by_knowledge()

        elif choice == "9":
            show_mistakes()

            try:
                index = int(input("请输入要收藏的错题编号："))
                favorite_mistake(index)
            except ValueError:
                print("请输入数字编号。")

        elif choice == "10":
            show_favorites()

        elif choice == "11":
            mistake_rank()

        elif choice == "12":
            mistakes = load_mistakes()

            if not mistakes:
                print("暂无错题记录，无法生成学习建议。")
                continue

            stat = {}

            for m in mistakes:
                error_type = m.get("type", "未分类")
                stat[error_type] = stat.get(error_type, 0) + 1

            stat_text = ""

            for error_type, count in stat.items():
                stat_text += f"{error_type}：{count}题\n"

            advice = generate_study_advice(stat_text)

            print("\n===== AI学习建议 =====")
            print(advice)

        elif choice == "13":
            problem = input_multiline("\n请输入OJ题目描述：")
            code = input_multiline("\n请输入你的C++代码：")

            result = oj_analysis(problem, code)

            print("\n===== OJ专项分析结果 =====")
            print(result)

        elif choice == "14":
            export_pdf()

        elif choice == "15":
            question = input("请输入你的C++问题：")

            result = explain_question(question)

            print("\n===== AI解答 =====")
            print(result)


        elif choice == "16":
            show_learning_profile()

        elif choice == "17":
            weak_knowledge = get_weak_knowledge()

            if weak_knowledge is None:
                print("暂无学习画像数据，请先保存一些错题。")
                continue

            print(f"\n系统检测到你的薄弱知识点是：{weak_knowledge}")
            print("正在生成专项练习题...\n")

            result = generate_practice_by_knowledge(weak_knowledge)

            print("===== AI专项练习 =====")
            print(result)

        elif choice == "18":
            problem = input_multiline("\n请输入OJ题目描述：")
            code = input_multiline("\n请输入你的C++代码：")

            result = coach_problem(problem, code)

            print("\n===== AI教练模式 =====")
            print(result)

        elif choice == "19":
            topic = input("请输入你想练习的题目内容，例如：vector删除元素、map统计次数、字符串处理：")
            difficulty = input("请输入难度，例如：基础 / 中等 / 提高：")
            count = input("请输入题目数量：")

            result = generate_practice_by_custom(topic, difficulty, count)

            print("\n===== 人工指定内容练习题 =====")
            print(result)
            
        elif choice == "0":
            print("程序已退出。")
            break

        else:
            print("输入错误，请重新选择。")


if __name__ == "__main__":
    main()