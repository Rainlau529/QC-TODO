# -*- coding: utf-8 -*-
"""
钉钉待办备忘录推送脚本 v2
功能：
1. 标记已完成
2. 优先级标记（紧急/重要/普通）
3. 截止日期提醒
"""

from flask import Flask, request, jsonify, render_template_string, redirect
import os
import json
import requests
from datetime import datetime, timedelta

app = Flask(__name__)

# 钉钉 Webhook URL
DINGTALK_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK", "")

# 数据文件路径
TODO_FILE = os.path.join(os.path.dirname(__file__), "todo.json")


def read_todos():
    """读取待办列表"""
    if not os.path.exists(TODO_FILE):
        return []
    try:
        with open(TODO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def write_todos(todos):
    """写入待办列表"""
    with open(TODO_FILE, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)


def get_next_id(todos):
    """获取下一个ID"""
    if not todos:
        return 1
    return max(t["id"] for t in todos) + 1


def parse_deadline(deadline_str):
    """解析截止日期字符串"""
    if not deadline_str:
        return None
    try:
        # 尝试解析 "4月25日" 格式
        import re
        match = re.match(r'(\d+)月(\d+)日', deadline_str)
        if match:
            month, day = int(match.group(1)), int(match.group(2))
            year = datetime.now().year
            return datetime(year, month, day)
    except:
        pass
    return None


def get_deadline_status(deadline_str):
    """获取截止日期状态"""
    deadline = parse_deadline(deadline_str)
    if not deadline:
        return "none"

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    days_left = (deadline - today).days

    if days_left < 0:
        return "overdue"  # 已过期
    elif days_left == 0:
        return "today"  # 今天到期
    elif days_left == 1:
        return "tomorrow"  # 明天到期
    elif days_left <= 3:
        return "soon"  # 3天内到期
    else:
        return "normal"


def build_dingtalk_message(todos):
    """构建钉钉消息"""
    if not todos:
        return {
            "msgtype": "text",
            "text": {"content": "📋 汽二待办备忘录：\n暂无待办事项！"}
        }

    # 分离已完成和未完成
    undone = [t for t in todos if not t.get("done", False)]
    done = [t for t in todos if t.get("done", False)]

    # 按优先级排序：紧急 > 重要 > 普通
    priority_order = {"high": 0, "important": 1, "normal": 2}
    undone.sort(key=lambda x: (priority_order.get(x.get("priority", "normal"), 2), x.get("deadline", "")))

    content = "📋 汽二待办备忘录\n\n"

    # 截止日期提醒
    today = datetime.now().strftime("%m月%d日")
    urgent_items = [t for t in undone if get_deadline_status(t.get("deadline", "")) in ["overdue", "today", "tomorrow", "soon"]]

    if urgent_items:
        content += "⏰ 截止提醒\n"
        for t in urgent_items:
            status = get_deadline_status(t.get("deadline", ""))
            deadline = t.get("deadline", "无截止")
            if status == "overdue":
                content += f"🚨 已过期！{deadline} {t['content']}\n"
            elif status == "today":
                content += f"🚨 今天截止！{t['content']}\n"
            elif status == "tomorrow":
                content += f"⚠️ 明天截止：{t['content']}\n"
            elif status == "soon":
                content += f"⚠️ {deadline} 截止：{t['content']}\n"
        content += "\n"

    # 未完成事项
    if undone:
        content += "📌 待办事项\n"
        for t in undone:
            priority = t.get("priority", "normal")
            deadline = t.get("deadline", "无截止")
            priority_icon = {"high": "🚨", "important": "📌", "normal": "📝"}.get(priority, "📝")
            priority_tag = {"high": "[紧急]", "important": "[重要]", "normal": ""}.get(priority, "")

            if priority == "high":
                content += f"{priority_icon} {priority_tag}{deadline} {t['content']}\n"
            elif priority == "important":
                content += f"{priority_icon} {priority_tag}{deadline} {t['content']}\n"
            else:
                content += f"{priority_icon} {deadline} {t['content']}\n"
        content += "\n"

    # 已完成事项
    if done:
        content += "✅ 已完成\n"
        for t in done:
            content += f"☑️ {t.get('deadline', '')} {t['content']}\n"

    return {
        "msgtype": "text",
        "text": {"content": content}
    }


def send_to_dingtalk(message):
    """发送消息到钉钉"""
    if not DINGTALK_WEBHOOK:
        return False, "钉钉 Webhook 未配置"

    try:
        response = requests.post(
            DINGTALK_WEBHOOK,
            json=message,
            timeout=10
        )
        result = response.json()
        if result.get("errcode") == 0:
            return True, "发送成功"
        else:
            return False, f"发送失败：{result.get('errmsg', '未知错误')}"
    except Exception as e:
        return False, f"请求异常：{str(e)}"


# HTML 模板
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>待办备忘录</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f0f2f5; padding: 20px; }
        .container { max-width: 700px; margin: 0 auto; }
        h1 { text-align: center; color: #333; margin-bottom: 20px; }
        .card { background: white; border-radius: 12px; padding: 20px; margin-bottom: 15px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
        .section-title { font-size: 14px; color: #666; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #eee; }
        .todo-item { display: flex; align-items: flex-start; padding: 12px 0; border-bottom: 1px solid #f5f5f5; gap: 10px; }
        .todo-item:last-child { border-bottom: none; }
        .todo-item.done { opacity: 0.6; }
        .todo-item.done .todo-content { text-decoration: line-through; }
        .todo-checkbox { width: 20px; height: 20px; cursor: pointer; flex-shrink: 0; margin-top: 2px; }
        .priority-tag { font-size: 12px; padding: 2px 8px; border-radius: 4px; flex-shrink: 0; }
        .priority-high { background: #fff1f0; color: #ff4d4f; }
        .priority-important { background: #fff7e6; color: #fa8c16; }
        .priority-normal { background: #f0f5ff; color: #1890ff; }
        .todo-content { flex: 1; color: #333; line-height: 1.5; }
        .todo-deadline { font-size: 13px; color: #999; margin-top: 4px; }
        .deadline-overdue { color: #ff4d4f; font-weight: bold; }
        .deadline-today { color: #ff4d4f; font-weight: bold; }
        .deadline-tomorrow { color: #fa8c16; }
        .deadline-soon { color: #fa8c16; }
        .todo-actions { display: flex; gap: 8px; flex-shrink: 0; }
        .btn-small { padding: 4px 10px; font-size: 12px; border-radius: 4px; border: none; cursor: pointer; }
        .btn-done { background: #52c41a; color: white; }
        .btn-delete { background: #ff4d4f; color: white; text-decoration: none; font-size: 12px; padding: 4px 10px; border-radius: 4px; }
        .btn-delete:hover { background: #ff7875; }
        .empty { text-align: center; color: #999; padding: 30px; }
        .form-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
        .form-group { display: flex; gap: 10px; flex-wrap: wrap; }
        .form-group input, .form-group select { padding: 10px; border: none; border-radius: 6px; font-size: 14px; }
        .form-group input[type="text"] { flex: 1; min-width: 200px; }
        .form-group select { background: white; min-width: 100px; }
        .form-group .btn-add { padding: 10px 24px; background: white; color: #667eea; border: none; border-radius: 6px; font-size: 14px; font-weight: bold; cursor: pointer; }
        .form-hint { font-size: 12px; opacity: 0.8; margin-top: 8px; }
        .actions { display: flex; gap: 10px; margin-top: 20px; }
        .btn { display: inline-block; padding: 12px 24px; background: #667eea; color: white; text-decoration: none; border-radius: 6px; border: none; cursor: pointer; font-size: 14px; }
        .btn:hover { background: #5a6fd6; }
        .btn-send { background: #52c41a; }
        .btn-send:hover { background: #73d13d; }
        .btn-danger { background: #ff4d4f; }
        .btn-danger:hover { background: #ff7875; }
        .message { padding: 12px; border-radius: 6px; margin-top: 10px; }
        .message.success { background: #f6ffed; border: 1px solid #b7eb8f; color: #52c41a; }
        .message.error { background: #fff2f0; border: 1px solid #ffccc7; color: #ff4d4f; }
        .stats { display: flex; gap: 20px; margin-bottom: 15px; }
        .stat { text-align: center; flex: 1; }
        .stat-num { font-size: 24px; font-weight: bold; color: #667eea; }
        .stat-label { font-size: 12px; color: #999; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📋 待办备忘录</h1>

        <div class="card form-card">
            <form action="/add" method="get">
                <div class="form-group">
                    <input type="text" name="content" placeholder="输入待办内容" required>
                    <input type="text" name="deadline" placeholder="如：4月25日">
                    <select name="priority">
                        <option value="normal">📝 普通</option>
                        <option value="important">📌 重要</option>
                        <option value="high">🚨 紧急</option>
                    </select>
                    <button type="submit" class="btn-add">添加</button>
                </div>
                <div class="form-hint">截止日期格式：如 4月25日</div>
            </form>
        </div>

        {% if message %}
        <div class="card">
            <div class="message {{ message_type }}">{{ message }}</div>
        </div>
        {% endif %}

        {% if todos %}
        <div class="stats card">
            <div class="stat">
                <div class="stat-num">{{ stats.total }}</div>
                <div class="stat-label">总待办</div>
            </div>
            <div class="stat">
                <div class="stat-num">{{ stats.undone }}</div>
                <div class="stat-label">待完成</div>
            </div>
            <div class="stat">
                <div class="stat-num">{{ stats.done }}</div>
                <div class="stat-label">已完成</div>
            </div>
            <div class="stat">
                <div class="stat-num">{{ stats.urgent }}</div>
                <div class="stat-label">紧急事项</div>
            </div>
        </div>
        {% endif %}

        {% if undone_todos %}
        <div class="card">
            <div class="section-title">📌 待办事项 ({{ undone_todos|length }})</div>
            {% for todo in undone_todos %}
            <div class="todo-item">
                <input type="checkbox" class="todo-checkbox" onchange="location.href='/done/{{ todo.id }}'">
                <div style="flex: 1;">
                    <div class="todo-content">{{ todo.content }}</div>
                    {% if todo.deadline %}
                    <div class="todo-deadline deadline-{{ todo.deadline_status }}">{{ todo.deadline_str }}</div>
                    {% endif %}
                </div>
                {% if todo.priority != 'normal' %}
                <span class="priority-tag priority-{{ todo.priority }}">{{ {"high": "🚨 紧急", "important": "📌 重要"}[todo.priority] }}</span>
                {% endif %}
                <div class="todo-actions">
                    <a href="/delete/{{ todo.id }}" class="btn-delete" onclick="return confirm('确定删除？')">删除</a>
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}

        {% if done_todos %}
        <div class="card">
            <div class="section-title">✅ 已完成 ({{ done_todos|length }})</div>
            {% for todo in done_todos %}
            <div class="todo-item done">
                <input type="checkbox" class="todo-checkbox" checked onchange="location.href='/undone/{{ todo.id }}'">
                <div style="flex: 1;">
                    <div class="todo-content">{{ todo.content }}</div>
                    {% if todo.deadline %}
                    <div class="todo-deadline">{{ todo.deadline }}</div>
                    {% endif %}
                </div>
                <div class="todo-actions">
                    <a href="/delete/{{ todo.id }}" class="btn-delete" onclick="return confirm('确定删除？')">删除</a>
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}

        {% if not todos %}
        <div class="card">
            <div class="empty">暂无待办事项，添加一个吧！</div>
        </div>
        {% endif %}

        <div class="actions">
            <a href="/send" class="btn btn-send">📤 推送到钉钉群</a>
            <a href="/clear" class="btn btn-danger" onclick="return confirm('确定清空所有待办？')">🗑️ 清空</a>
        </div>
    </div>
</body>
</html>
'''


@app.route("/")
def index():
    """首页"""
    message = request.args.get("message", "")
    message_type = request.args.get("type", "")
    todos = read_todos()

    # 处理数据，添加截止日期状态
    for t in todos:
        t["deadline_str"] = t.get("deadline", "")
        t["deadline_status"] = get_deadline_status(t.get("deadline", ""))

    undone_todos = [t for t in todos if not t.get("done", False)]
    done_todos = [t for t in todos if t.get("done", False)]

    # 统计
    stats = {
        "total": len(todos),
        "undone": len(undone_todos),
        "done": len(done_todos),
        "urgent": len([t for t in undone_todos if t.get("priority") == "high"])
    }

    return render_template_string(
        HTML_TEMPLATE,
        todos=todos,
        undone_todos=undone_todos,
        done_todos=done_todos,
        stats=stats,
        message=message,
        message_type=message_type
    )


@app.route("/add")
def add_todo():
    """添加待办"""
    content = request.args.get("content", "").strip()
    deadline = request.args.get("deadline", "").strip()
    priority = request.args.get("priority", "normal")

    if not content:
        return redirect("/?message=内容不能为空&type=error")

    todos = read_todos()
    todos.append({
        "id": get_next_id(todos),
        "content": content,
        "deadline": deadline,
        "priority": priority,
        "done": False
    })
    write_todos(todos)

    return redirect("/?message=已添加：{}&type=success".format(content))


@app.route("/done/<int:todo_id>")
def done_todo(todo_id):
    """标记完成"""
    todos = read_todos()
    for t in todos:
        if t["id"] == todo_id:
            t["done"] = True
            write_todos(todos)
            return redirect("/?message=已标记完成：{}&type=success".format(t["content"]))
    return redirect("/?message=未找到该待办&type=error")


@app.route("/undone/<int:todo_id>")
def undone_todo(todo_id):
    """取消完成"""
    todos = read_todos()
    for t in todos:
        if t["id"] == todo_id:
            t["done"] = False
            write_todos(todos)
            return redirect("/?message=已取消完成：{}&type=success".format(t["content"]))
    return redirect("/?message=未找到该待办&type=error")


@app.route("/delete/<int:todo_id>")
def delete_todo(todo_id):
    """删除待办"""
    todos = read_todos()
    for i, t in enumerate(todos):
        if t["id"] == todo_id:
            deleted = todos.pop(i)
            write_todos(todos)
            return redirect("/?message=已删除：{}&type=success".format(deleted["content"]))
    return redirect("/?message=未找到该待办&type=error")


@app.route("/clear")
def clear_todo():
    """清空待办"""
    write_todos([])
    return redirect("/?message=已清空所有待办&type=success")


@app.route("/send")
def send():
    """推送待办到钉钉群"""
    todos = read_todos()
    message = build_dingtalk_message(todos)
    success, msg = send_to_dingtalk(message)

    if success:
        return jsonify({"code": 0, "message": msg})
    else:
        return jsonify({"code": -1, "message": msg}), 400


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
