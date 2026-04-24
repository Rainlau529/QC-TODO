# -*- coding: utf-8 -*-
"""
钉钉待办备忘录 v3 - 带进度追踪
功能：
1. 标记已完成
2. 优先级标记（紧急/重要/普通）
3. 截止日期提醒
4. 负责人进度追踪（百分比进度条）
"""

from flask import Flask, request, jsonify, render_template_string, redirect
import os
import json
import requests
import re
from datetime import datetime

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


def get_progress(todo):
    """计算进度"""
    members = todo.get("members", [])
    if not members:
        return 100 if todo.get("done", False) else 0
    done_count = sum(1 for m in members if m.get("done", False))
    return int(done_count / len(members) * 100)


def parse_deadline(deadline_str):
    """解析截止日期"""
    if not deadline_str:
        return None
    try:
        match = re.match(r'(\d+)月(\d+)日', deadline_str)
        if match:
            month, day = int(match.group(1)), int(match.group(2))
            return datetime(datetime.now().year, month, day)
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
        return "overdue"
    elif days_left == 0:
        return "today"
    elif days_left == 1:
        return "tomorrow"
    elif days_left <= 3:
        return "soon"
    return "normal"


def build_progress_bar(progress, width=10):
    """构建进度条文本"""
    filled = int(width * progress / 100)
    empty = width - filled
    return "█" * filled + "░" * empty


def build_dingtalk_message(todos, base_url="https://dingtalk-reminder.onrender.com"):
    """构建钉钉消息（Markdown格式，支持点击链接标记完成）"""
    if not todos:
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": "汽二待办备忘录",
                "text": "## 📋 汽二待办备忘录\n\n暂无待办事项！"
            }
        }

    undone = [t for t in todos if not t.get("done", False)]
    priority_order = {"high": 0, "important": 1, "normal": 2}
    undone.sort(key=lambda x: (priority_order.get(x.get("priority", "normal"), 2), x.get("deadline", "")))

    content = "## 📋 汽二待办备忘录\n\n"

    # 截止日期提醒
    urgent_items = [t for t in undone if get_deadline_status(t.get("deadline", "")) in ["overdue", "today", "tomorrow", "soon"]]
    if urgent_items:
        content += "### ⏰ 截止提醒\n"
        for t in urgent_items:
            status = get_deadline_status(t.get("deadline", ""))
            deadline = t.get("deadline", "无截止")
            if status == "overdue":
                content += f"- 🚨 **已过期！** {deadline} {t['content']}\n"
            elif status == "today":
                content += f"- 🚨 **今天截止！** {t['content']}\n"
            elif status == "tomorrow":
                content += f"- ⚠️ **明天截止：** {t['content']}\n"
            elif status == "soon":
                content += f"- ⚠️ **{deadline} 截止：** {t['content']}\n"
        content += "\n"

    # 待办事项（带进度和可点击负责人）
    if undone:
        content += "### 📌 待办事项\n"
        for t in undone:
            todo_id = t["id"]
            priority = t.get("priority", "normal")
            deadline = t.get("deadline", "")
            members = t.get("members", [])
            progress = get_progress(t)
            progress_bar = build_progress_bar(progress)

            priority_icon = {"high": "🚨", "important": "📌", "normal": "📝"}.get(priority, "📝")
            priority_tag = {"high": "**[紧急]**", "important": "**[重要]**", "normal": ""}.get(priority, "")

            # 构建待办项标题
            if priority_tag:
                content += f"- {priority_icon} {priority_tag} {deadline} {t['content']}\n"
            else:
                content += f"- {priority_icon} {deadline} {t['content']}\n"

            # 添加进度条
            if members:
                done_count = sum(1 for m in members if m.get("done", False))
                total_count = len(members)
                content += f"    - 进度：**{progress}%** ▓▓▓▓▓▓░░░░ ({done_count}/{total_count}完成)\n"

                # 添加可点击的负责人列表
                content += "    - 👥 负责人："
                member_links = []
                for i, member in enumerate(members):
                    member_url = f"{base_url}/member/{todo_id}/{i}"
                    if member.get("done", False):
                        member_links.append(f"`☑️ {member['name']}`")
                    else:
                        member_links.append(f"[**☐ {member['name']}**]({member_url})")
                content += " ".join(member_links) + "\n"

        content += "\n"

    return {
        "msgtype": "markdown",
        "markdown": {
            "title": "汽二待办备忘录",
            "text": content
        }
    }


def send_to_dingtalk(message):
    """发送消息到钉钉"""
    if not DINGTALK_WEBHOOK:
        return False, "钉钉 Webhook 未配置"
    try:
        response = requests.post(DINGTALK_WEBHOOK, json=message, timeout=10)
        result = response.json()
        if result.get("errcode") == 0:
            return True, "发送成功"
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
        .container { max-width: 800px; margin: 0 auto; }
        h1 { text-align: center; color: #333; margin-bottom: 20px; }
        .card { background: white; border-radius: 12px; padding: 20px; margin-bottom: 15px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
        .section-title { font-size: 14px; color: #666; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #eee; }
        .todo-item { padding: 15px 0; border-bottom: 1px solid #f5f5f5; }
        .todo-item:last-child { border-bottom: none; }
        .todo-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
        .todo-checkbox { width: 20px; height: 20px; cursor: pointer; }
        .priority-tag { font-size: 12px; padding: 2px 8px; border-radius: 4px; }
        .priority-high { background: #fff1f0; color: #ff4d4f; }
        .priority-important { background: #fff7e6; color: #fa8c16; }
        .priority-normal { background: #f0f5ff; color: #1890ff; }
        .todo-content { flex: 1; color: #333; font-size: 15px; }
        .todo-deadline { font-size: 13px; color: #999; }
        .deadline-overdue { color: #ff4d4f; font-weight: bold; }
        .deadline-today { color: #ff4d4f; font-weight: bold; }
        .deadline-tomorrow { color: #fa8c16; }
        .deadline-soon { color: #fa8c16; }
        .progress-section { margin-top: 10px; }
        .progress-bar { display: flex; align-items: center; gap: 10px; }
        .progress-track { flex: 1; height: 8px; background: #f0f0f0; border-radius: 4px; overflow: hidden; }
        .progress-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
        .progress-fill.high { background: #52c41a; }
        .progress-fill.medium { background: #faad14; }
        .progress-fill.low { background: #ff4d4f; }
        .progress-text { font-size: 13px; color: #666; min-width: 50px; }
        .member-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
        .member-chip { display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 12px; font-size: 12px; cursor: pointer; transition: all 0.2s; }
        .member-chip.done { background: #f6ffed; color: #52c41a; border: 1px solid #b7eb8f; }
        .member-chip.undone { background: #f5f5f5; color: #666; border: 1px solid #d9d9d9; }
        .member-chip:hover { opacity: 0.8; }
        .member-check { font-size: 10px; }
        .todo-actions { display: flex; gap: 8px; margin-top: 10px; }
        .btn-small { padding: 4px 10px; font-size: 12px; border-radius: 4px; border: none; cursor: pointer; text-decoration: none; }
        .btn-delete { background: #ff4d4f; color: white; }
        .btn-delete:hover { background: #ff7875; }
        .empty { text-align: center; color: #999; padding: 30px; }
        .form-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
        .form-group { display: flex; gap: 10px; flex-wrap: wrap; }
        .form-group input, .form-group select { padding: 10px; border: none; border-radius: 6px; font-size: 14px; }
        .form-group input[type="text"] { flex: 1; min-width: 150px; }
        .form-group input[type="text"].wide { min-width: 250px; }
        .form-group select { background: white; min-width: 90px; }
        .form-group .btn-add { padding: 10px 24px; background: white; color: #667eea; border: none; border-radius: 6px; font-size: 14px; font-weight: bold; cursor: pointer; }
        .form-hint { font-size: 12px; opacity: 0.8; margin-top: 8px; }
        .stats { display: flex; gap: 15px; margin-bottom: 15px; }
        .stat { text-align: center; flex: 1; background: white; padding: 15px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
        .stat-num { font-size: 24px; font-weight: bold; color: #667eea; }
        .stat-label { font-size: 12px; color: #999; }
        .actions { display: flex; gap: 10px; margin-top: 20px; }
        .btn { display: inline-block; padding: 12px 24px; background: #667eea; color: white; text-decoration: none; border-radius: 6px; border: none; cursor: pointer; font-size: 14px; }
        .btn:hover { background: #5a6fd6; }
        .btn-send { background: #52c41a; }
        .btn-send:hover { background: #73d13d; }
        .btn-danger { background: #ff4d4f; }
        .btn-danger:hover { background: #ff7875; }
        .message { padding: 12px; border-radius: 6px; margin-bottom: 15px; }
        .message.success { background: #f6ffed; border: 1px solid #b7eb8f; color: #52c41a; }
        .message.error { background: #fff2f0; border: 1px solid #ffccc7; color: #ff4d4f; }
        .form-row { display: flex; gap: 10px; margin-bottom: 10px; }
        .form-label { font-size: 13px; color: rgba(255,255,255,0.9); min-width: 70px; line-height: 36px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📋 待办备忘录</h1>

        {% if message %}
        <div class="message {{ message_type }}">{{ message }}</div>
        {% endif %}

        <div class="card form-card">
            <form action="/add" method="get">
                <div class="form-row">
                    <span class="form-label">待办内容</span>
                    <input type="text" name="content" placeholder="输入待办内容" required style="flex:1;padding:10px;border:none;border-radius:6px;font-size:14px;">
                </div>
                <div class="form-row">
                    <span class="form-label">截止日期</span>
                    <input type="text" name="deadline" placeholder="如：4月25日" style="flex:1;padding:10px;border:none;border-radius:6px;font-size:14px;">
                </div>
                <div class="form-row">
                    <span class="form-label">优先级</span>
                    <select name="priority" style="padding:10px;border:none;border-radius:6px;font-size:14px;">
                        <option value="normal">📝 普通</option>
                        <option value="important">📌 重要</option>
                        <option value="high">🚨 紧急</option>
                    </select>
                </div>
                <div class="form-row">
                    <span class="form-label">负责人</span>
                    <input type="text" name="members" placeholder="多人用逗号分隔，如：张三,李四,王五" class="wide" style="flex:1;padding:10px;border:none;border-radius:6px;font-size:14px;">
                </div>
                <div style="margin-top: 15px;">
                    <button type="submit" class="btn-add" style="padding:10px 24px;background:white;color:#667eea;border:none;border-radius:6px;font-size:14px;font-weight:bold;cursor:pointer;">添加待办</button>
                </div>
                <div class="form-hint">截止日期格式：如 4月25日</div>
            </form>
        </div>

        {% if stats.total > 0 %}
        <div class="stats">
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
                <div class="stat-label">紧急</div>
            </div>
        </div>
        {% endif %}

        {% if undone_todos %}
        <div class="card">
            <div class="section-title">📌 待办事项 ({{ undone_todos|length }})</div>
            {% for todo in undone_todos %}
            <div class="todo-item">
                <div class="todo-header">
                    <input type="checkbox" class="todo-checkbox" onchange="location.href='/done/{{ todo.id }}'">
                    <span class="priority-tag priority-{{ todo.priority }}">{{ {"high": "🚨 紧急", "important": "📌 重要", "normal": "📝 普通"}[todo.priority] }}</span>
                    <span class="todo-content">{{ todo.content }}</span>
                    {% if todo.deadline %}
                    <span class="todo-deadline deadline-{{ todo.deadline_status }}">{{ todo.deadline_str }}</span>
                    {% endif %}
                </div>

                {% if todo.members %}
                <div class="progress-section">
                    <div class="progress-bar">
                        <div class="progress-track">
                            <div class="progress-fill {{ todo.progress_class }}" style="width: {{ todo.progress }}%"></div>
                        </div>
                        <span class="progress-text">{{ todo.progress }}%</span>
                    </div>
                    <div class="member-list">
                        {% for member in todo.members %}
                        <span class="member-chip {{ 'done' if member.done else 'undone' }}" onclick="location.href='/member/{{ todo.id }}/{{ loop.index0 }}'">
                            <span class="member-check">{{ '☑' if member.done else '☐' }}</span>
                            {{ member.name }}
                        </span>
                        {% endfor %}
                    </div>
                </div>
                {% endif %}

                <div class="todo-actions">
                    <a href="/edit/{{ todo.id }}" class="btn-small" style="background:#1890ff;color:white;text-decoration:none;padding:4px 10px;border-radius:4px;font-size:12px;">编辑</a>
                    <a href="/delete/{{ todo.id }}" class="btn-small btn-delete" onclick="return confirm('确定删除？')">删除</a>
                </div>
            </div>
            {% endfor %}
        </div>
        {% endif %}

        {% if done_todos %}
        <div class="card">
            <div class="section-title">✅ 已完成 ({{ done_todos|length }})</div>
            {% for todo in done_todos %}
            <div class="todo-item" style="opacity: 0.6;">
                <div class="todo-header">
                    <input type="checkbox" class="todo-checkbox" checked onchange="location.href='/undone/{{ todo.id }}'">
                    <span class="todo-content" style="text-decoration: line-through;">{{ todo.content }}</span>
                </div>
                <div class="todo-actions">
                    <a href="/delete/{{ todo.id }}" class="btn-small btn-delete" onclick="return confirm('确定删除？')">删除</a>
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

    for t in todos:
        t["deadline_str"] = t.get("deadline", "")
        t["deadline_status"] = get_deadline_status(t.get("deadline", ""))
        t["progress"] = get_progress(t)
        t["progress_class"] = "high" if t["progress"] >= 80 else "medium" if t["progress"] >= 30 else "low"

    undone_todos = [t for t in todos if not t.get("done", False)]
    done_todos = [t for t in todos if t.get("done", False)]

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
    members_str = request.args.get("members", "").strip()

    if not content:
        return redirect("/?message=内容不能为空&type=error")

    members = []
    if members_str:
        for name in members_str.split(","):
            name = name.strip()
            if name:
                members.append({"name": name, "done": False})

    todos = read_todos()
    todos.append({
        "id": get_next_id(todos),
        "content": content,
        "deadline": deadline,
        "priority": priority,
        "done": False,
        "members": members
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


@app.route("/member/<int:todo_id>/<int:member_index>")
def toggle_member(todo_id, member_index):
    """切换成员完成状态"""
    todos = read_todos()
    print(f"[DEBUG] toggle_member: todo_id={todo_id}, member_index={member_index}")

    for t in todos:
        if t["id"] == todo_id:
            members = t.get("members", [])
            print(f"[DEBUG] Found todo, members={members}")
            print(f"[DEBUG] Member at index {member_index}: {members[member_index] if member_index < len(members) else 'OUT OF RANGE'}")

            if 0 <= member_index < len(members):
                members[member_index]["done"] = not members[member_index]["done"]
                write_todos(todos)
                name = members[member_index]["name"]
                done_status = "已完成" if members[member_index]["done"] else "未完成"
                print(f"[DEBUG] Toggled member '{name}' to done={members[member_index]['done']}")

                # 如果有人标记为完成，检查是否全员完成
                if members[member_index]["done"]:
                    all_done = all(m.get("done", False) for m in members)
                    print(f"[DEBUG] All done check: {all_done}, members status={[m.get('done') for m in members]}")
                    if all_done:
                        # 全员完成，自动推送钉钉
                        t["done"] = True
                        write_todos(todos)
                        message = build_dingtalk_message(todos)
                        send_to_dingtalk(message)
                        print(f"[DEBUG] All members done, sending notification")
                        return redirect("/?message={}：{}！全员完成，已推送钉钉群！&type=success".format(name, done_status))

                return redirect("/?message={}：{}&type=success".format(name, done_status))

    print(f"[DEBUG] Member not found")
    return redirect("/?message=未找到该成员&type=error")


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
    return jsonify({"code": -1, "message": msg}), 400


@app.route("/edit/<int:todo_id>")
def edit_todo(todo_id):
    """编辑待办页面"""
    todos = read_todos()
    todo = None
    for t in todos:
        if t["id"] == todo_id:
            todo = t
            break

    if not todo:
        return redirect("/?message=未找到该待办&type=error")

    # 构建编辑表单页面
    members_str = ",".join([m["name"] for m in todo.get("members", [])])

    html = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>编辑待办</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f0f2f5; padding: 20px; }
        .container { max-width: 600px; margin: 0 auto; }
        h1 { text-align: center; color: #333; margin-bottom: 20px; }
        .card { background: white; border-radius: 12px; padding: 25px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; font-size: 14px; color: #666; margin-bottom: 5px; }
        .form-group input, .form-group select { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; }
        .btn { display: inline-block; padding: 12px 24px; background: #667eea; color: white; text-decoration: none; border-radius: 6px; border: none; cursor: pointer; font-size: 14px; }
        .btn:hover { background: #5a6fd6; }
        .btn-cancel { background: #999; margin-left: 10px; }
        .btn-cancel:hover { background: #888; }
        .btn-delete { background: #ff4d4f; }
    </style>
</head>
<body>
    <div class="container">
        <h1>✏️ 编辑待办</h1>
        <div class="card">
            <form action="/update/''' + str(todo_id) + '''" method="post">
                <div class="form-group">
                    <label>待办内容</label>
                    <input type="text" name="content" value="''' + todo["content"] + '''" required>
                </div>
                <div class="form-group">
                    <label>截止日期</label>
                    <input type="text" name="deadline" value="''' + (todo.get("deadline") or "") + '''" placeholder="如：4月25日">
                </div>
                <div class="form-group">
                    <label>优先级</label>
                    <select name="priority">
                        <option value="normal" ''' + ("selected" if todo.get("priority") == "normal" else "") + '''>📝 普通</option>
                        <option value="important" ''' + ("selected" if todo.get("priority") == "important" else "") + '''>📌 重要</option>
                        <option value="high" ''' + ("selected" if todo.get("priority") == "high" else "") + '''>🚨 紧急</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>负责人（多人用逗号分隔）</label>
                    <input type="text" name="members" value="''' + members_str + '''" placeholder="张三,李四,王五">
                </div>
                <div style="margin-top: 20px;">
                    <button type="submit" class="btn">保存修改</button>
                    <a href="/" class="btn btn-cancel">取消</a>
                    <a href="/delete/''' + str(todo_id) + '''" class="btn btn-delete" style="float:right;" onclick="return confirm('确定删除？')">删除</a>
                </div>
            </form>
        </div>
    </div>
</body>
</html>
'''
    return html


@app.route("/update/<int:todo_id>", methods=["POST"])
def update_todo(todo_id):
    """更新待办"""
    content = request.form.get("content", "").strip()
    deadline = request.form.get("deadline", "").strip()
    priority = request.form.get("priority", "normal")
    members_str = request.form.get("members", "").strip()

    if not content:
        return redirect("/?message=内容不能为空&type=error")

    todos = read_todos()
    for t in todos:
        if t["id"] == todo_id:
            t["content"] = content
            t["deadline"] = deadline
            t["priority"] = priority

            # 更新负责人
            members = []
            if members_str:
                for name in members_str.split(","):
                    name = name.strip()
                    if name:
                        # 保留原有完成状态
                        old_done = False
                        for old_m in t.get("members", []):
                            if old_m["name"] == name:
                                old_done = old_m.get("done", False)
                                break
                        members.append({"name": name, "done": old_done})
            t["members"] = members

            write_todos(todos)
            return redirect("/?message=已更新：{}&type=success".format(content))

    return redirect("/?message=未找到该待办&type=error")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
