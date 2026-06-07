# C++ AI 学习助手

这是一个面向 C++ 程序设计学习的 Flask Web 应用，集成 AI 讲解、代码调试、OJ 题目分析、错题管理和学习画像功能，适合课程学习、刷题复盘和日常编程练习使用。

## 项目功能

- AI 代码调试：提交 C++ 代码和问题描述后，系统会结合 AI 分析错误原因、修改思路和关键知识点。
- 本地编译运行：自动寻找本机 C++ 编译器，支持编译、运行代码，并把编译输出作为 AI 分析上下文。
- AI 题目讲解：针对 C++ 概念题、代码题或学习疑问生成分步骤解释。
- OJ 分析：输入题目和代码后，辅助分析解题思路、复杂度、边界情况和代码问题。
- 教练模式：通过引导式提示帮助用户自己推导解法，而不是直接给出完整答案。
- 专项练习生成：根据薄弱知识点或自定义主题生成练习题，支持不同难度和题量。
- 图片题目识别：支持上传题目图片，通过 OCR 提取文字后交给 AI 继续讲解或分析。
- 错题本管理：保存调试结果，支持搜索、分类、收藏、复习、标记掌握和删除错题。
- 学习分析：统计错误类型、薄弱知识点和复习状态，并生成针对性的学习建议。
- 对话记录：按不同学习场景保存历史对话，便于继续追问和回看学习过程。
- 报告导出：错题本可导出为 Markdown 或 PDF，方便整理课程报告和复习资料。

## 技术栈

- 后端：Python、Flask
- 前端：HTML、CSS、JavaScript
- AI 接口：DeepSeek Chat API
- 本地运行：C++ 编译器，例如 g++ 或 clang++
- 图片识别：Tesseract OCR
- 数据存储：本地 JSON 文件

## 项目结构

```text
AI_cpp_tutor/
├── app.py                  # Flask 主应用和路由
├── ai_helper.py            # AI 提示词、模型调用和结果格式化
├── cpp_runner.py           # C++ 编译运行工具
├── conversation_store.py   # 对话历史存储
├── mistake_book.py         # 错题本、统计和导出功能
├── main.py                 # 命令行入口
├── templates/
│   └── index.html          # 主页面
└── .gitignore
```

## 运行方式

1. 安装 Python 依赖：

```powershell
pip install flask openai python-dotenv reportlab pillow
```

2. 配置环境变量，在项目根目录创建 `.env`：

```env
DEEPSEEK_API_KEY=你的 DeepSeek API Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_CHAT_MODEL=deepseek-chat
```

3. 启动应用：

```powershell
python app.py
```

4. 在浏览器中打开：

```text
http://127.0.0.1:5000
```

## 可选环境

- 如需本地编译运行 C++ 代码，请安装 `g++` 或 `clang++`，并确保命令可在终端中使用。
- 如需图片 OCR 功能，请安装 Tesseract OCR，并将其加入系统环境变量。

## 数据文件说明

应用运行时会在本地生成以下数据文件，这些文件已被 `.gitignore` 忽略，不会上传到仓库：

- `conversations.json`：对话历史
- `mistakes.json`：错题记录
- `learning_profile.json`：学习画像数据
- `outputs/`：导出的 Markdown 或 PDF 报告

## 适用场景

- C++ 课程学习和作业调试
- OJ 刷题后的复盘分析
- 常见语法、指针、数组、函数、类和 STL 等知识点练习
- 错题整理、阶段复习和学习报告生成
