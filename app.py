from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
from datetime import datetime, timedelta
import json
import os

app = Flask(__name__)
CORS(app)

# 初始化資料庫
def init_db():
    conn = sqlite3.connect('voting.db')
    c = conn.cursor()
    
    # 員工表(加入最後投票時間)
    c.execute('''CREATE TABLE IF NOT EXISTS employees
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  emp_id TEXT UNIQUE NOT NULL,
                  name TEXT NOT NULL,
                  shift_type TEXT NOT NULL,
                  has_voted INTEGER DEFAULT 0,
                  last_vote_time TEXT)''')
    
    # 投票記錄表
    c.execute('''CREATE TABLE IF NOT EXISTS votes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  voter_emp_id TEXT NOT NULL,
                  voter_name TEXT NOT NULL,
                  voter_shift TEXT NOT NULL,
                  voted_for_emp_id TEXT NOT NULL,
                  voted_for_name TEXT NOT NULL,
                  voted_for_shift TEXT NOT NULL,
                  timestamp TEXT NOT NULL)''')
    
    # 檢查 votes 表是否有 week_start 欄位,沒有就添加
    c.execute("PRAGMA table_info(votes)")
    columns = [col[1] for col in c.fetchall()]
    
    if 'week_start' not in columns:
        print("⚠️  偵測到舊版資料庫,正在自動升級...")
        # 添加 week_start 欄位
        c.execute("ALTER TABLE votes ADD COLUMN week_start TEXT")
        
        # 更新現有記錄的 week_start
        c.execute("SELECT id, timestamp FROM votes")
        votes_to_update = c.fetchall()
        
        for vote_id, timestamp in votes_to_update:
            try:
                date = datetime.fromisoformat(timestamp)
                week_start = get_week_start(date)
            except:
                week_start = get_week_start()
            c.execute("UPDATE votes SET week_start = ? WHERE id = ?", (week_start, vote_id))
        
        print(f"✅ 已更新 {len(votes_to_update)} 筆舊投票記錄")
    
    # 投票配額設定表(每週設定)
    c.execute('''CREATE TABLE IF NOT EXISTS vote_quotas
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  week_start TEXT NOT NULL UNIQUE,
                  rr_quota INTEGER DEFAULT 1,
                  shift_quota INTEGER DEFAULT 1,
                  created_at TEXT NOT NULL)''')
    
    # 員工每週投票記錄表
    c.execute('''CREATE TABLE IF NOT EXISTS weekly_votes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  emp_id TEXT NOT NULL,
                  week_start TEXT NOT NULL,
                  shift_type TEXT NOT NULL,
                  votes_used INTEGER DEFAULT 0,
                  UNIQUE(emp_id, week_start))''')
    
    # 初始化 weekly_votes (如果是第一次升級)
    c.execute("SELECT COUNT(*) FROM weekly_votes")
    if c.fetchone()[0] == 0:
        c.execute("""
            INSERT OR IGNORE INTO weekly_votes (emp_id, week_start, shift_type, votes_used)
            SELECT 
                v.voter_emp_id,
                v.week_start,
                v.voter_shift,
                COUNT(*) as votes_used
            FROM votes v
            WHERE v.week_start IS NOT NULL
            GROUP BY v.voter_emp_id, v.week_start, v.voter_shift
        """)
        if c.rowcount > 0:
            print(f"✅ 初始化了 {c.rowcount} 筆週投票記錄")
    
    conn.commit()
    conn.close()

# 獲取週的開始日期(週一)
def get_week_start(date=None):
    if date is None:
        date = datetime.now()
    # 找到本週一
    week_start = date - timedelta(days=date.weekday())
    return week_start.strftime('%Y-%m-%d')

# 獲取週的結束日期(週日)
def get_week_end(week_start_str):
    week_start = datetime.strptime(week_start_str, '%Y-%m-%d')
    week_end = week_start + timedelta(days=6)
    return week_end.strftime('%Y-%m-%d')

# 獲取或創建本週配額
def get_or_create_quota(week_start=None):
    if week_start is None:
        week_start = get_week_start()
    
    conn = sqlite3.connect('voting.db')
    c = conn.cursor()
    
    c.execute('SELECT rr_quota, shift_quota FROM vote_quotas WHERE week_start = ?', (week_start,))
    result = c.fetchone()
    
    if result:
        quota = {'week_start': week_start, 'rr_quota': result[0], 'shift_quota': result[1]}
    else:
        # 創建預設配額
        c.execute('''INSERT INTO vote_quotas (week_start, rr_quota, shift_quota, created_at)
                    VALUES (?, 1, 1, ?)''', (week_start, datetime.now().isoformat()))
        conn.commit()
        quota = {'week_start': week_start, 'rr_quota': 1, 'shift_quota': 1}
    
    conn.close()
    return quota

# 獲取或創建員工本週投票記錄
def get_or_create_weekly_votes(emp_id, shift_type, week_start=None):
    if week_start is None:
        week_start = get_week_start()
    
    conn = sqlite3.connect('voting.db')
    c = conn.cursor()
    
    c.execute('SELECT votes_used FROM weekly_votes WHERE emp_id = ? AND week_start = ?', 
             (emp_id, week_start))
    result = c.fetchone()
    
    if result:
        votes_used = result[0]
    else:
        c.execute('''INSERT INTO weekly_votes (emp_id, week_start, shift_type, votes_used)
                    VALUES (?, ?, ?, 0)''', (emp_id, week_start, shift_type))
        conn.commit()
        votes_used = 0
    
    conn.close()
    return votes_used

# 從 JSON 載入員工資料
def load_employees_from_json():
    try:
        with open('emoinfo.json', 'r', encoding='utf-8-sig') as f:
            employees = json.load(f)
            
        conn = sqlite3.connect('voting.db')
        c = conn.cursor()
        
        # 檢查是否已有資料
        c.execute('SELECT COUNT(*) FROM employees')
        count = c.fetchone()[0]
        
        if count == 0:
            # 插入員工資料
            for emp in employees:
                c.execute('''INSERT INTO employees (emp_id, name, shift_type, has_voted, last_vote_time)
                            VALUES (?, ?, ?, 0, NULL)''',
                         (emp['工號'], emp['姓名'], emp['班別']))
            
            conn.commit()
            print(f'✅ 成功載入 {len(employees)} 位員工資料')
        
        conn.close()
        return True
    except FileNotFoundError:
        print('❌ 找不到 emoinfo.json 檔案')
        return False
    except Exception as e:
        print(f'❌ 載入員工資料失敗: {str(e)}')
        return False

# 檢查是否可以投票(檢查本週配額)
def can_vote(emp_id, shift_type):
    week_start = get_week_start()
    quota = get_or_create_quota(week_start)
    votes_used = get_or_create_weekly_votes(emp_id, shift_type, week_start)
    
    max_votes = quota['rr_quota'] if shift_type == 'RR' else quota['shift_quota']
    
    if votes_used < max_votes:
        return True, None, votes_used, max_votes
    else:
        return False, f"本週投票配額已用完 ({votes_used}/{max_votes})", votes_used, max_votes

# 獲取所有員工
@app.route('/api/employees', methods=['GET'])
def get_employees():
    conn = sqlite3.connect('voting.db')
    c = conn.cursor()
    
    week_start = get_week_start()
    quota = get_or_create_quota(week_start)
    
    c.execute('SELECT emp_id, name, shift_type, has_voted, last_vote_time FROM employees ORDER BY emp_id')
    employees = []
    for row in c.fetchall():
        emp_id = row[0]
        shift_type = row[2]
        votes_used = get_or_create_weekly_votes(emp_id, shift_type, week_start)
        max_votes = quota['rr_quota'] if shift_type == 'RR' else quota['shift_quota']
        
        can_vote_now, message, _, _ = can_vote(emp_id, shift_type)
        
        employees.append({
            'emp_id': emp_id,
            'name': row[1],
            'shift_type': shift_type,
            'has_voted': bool(row[3]),
            'last_vote_time': row[4],
            'can_vote': can_vote_now,
            'votes_used': votes_used,
            'max_votes': max_votes
        })
    
    conn.close()
    return jsonify(employees)

# 獲取候選人列表(根據投票者的班別)
@app.route('/api/candidates/<emp_id>', methods=['GET'])
def get_candidates(emp_id):
    conn = sqlite3.connect('voting.db')
    c = conn.cursor()
    
    # 查詢投票者的資訊
    c.execute('SELECT name, shift_type, has_voted, last_vote_time FROM employees WHERE emp_id = ?', (emp_id,))
    result = c.fetchone()
    
    if not result:
        conn.close()
        return jsonify({'error': '工號不存在,請確認您的工號'}), 404
    
    voter_name = result[0]
    voter_shift = result[1]
    has_voted = result[2]
    last_vote_time = result[3]
    
    # 檢查是否可以投票(檢查本週配額)
    can_vote_now, error_message, votes_used, max_votes = can_vote(emp_id, voter_shift)
    
    if not can_vote_now:
        conn.close()
        return jsonify({'error': error_message}), 400
    
    # 根據班別返回候選人(輪班投RR,RR投輪班)
    target_shift = 'RR' if voter_shift == '輪班' else '輪班'
    
    c.execute('SELECT emp_id, name, shift_type FROM employees WHERE shift_type = ? ORDER BY emp_id',
             (target_shift,))
    
    candidates = []
    for row in c.fetchall():
        candidates.append({
            'emp_id': row[0],
            'name': row[1],
            'shift_type': row[2]
        })
    
    conn.close()
    return jsonify({
        'voter_name': voter_name,
        'voter_shift': voter_shift,
        'target_shift': target_shift,
        'candidates': candidates,
        'votes_used': votes_used,
        'max_votes': max_votes
    })

# 提交投票
@app.route('/api/vote', methods=['POST'])
def submit_vote():
    data = request.json
    voter_emp_id = data.get('voter_emp_id')
    voted_for_emp_id = data.get('voted_for_emp_id')
    
    conn = sqlite3.connect('voting.db')
    c = conn.cursor()
    
    try:
        # 檢查投票者資訊
        c.execute('SELECT name, shift_type, has_voted, last_vote_time FROM employees WHERE emp_id = ?', (voter_emp_id,))
        voter_info = c.fetchone()
        
        if not voter_info:
            return jsonify({'error': '投票者不存在'}), 404
        
        voter_name = voter_info[0]
        voter_shift = voter_info[1]
        has_voted = voter_info[2]
        last_vote_time = voter_info[3]
        
        # 檢查本週配額
        can_vote_now, error_message, votes_used, max_votes = can_vote(voter_emp_id, voter_shift)
        if not can_vote_now:
            return jsonify({'error': error_message}), 400
        
        # 獲取被投票者資訊
        c.execute('SELECT name, shift_type FROM employees WHERE emp_id = ?', (voted_for_emp_id,))
        voted_for_info = c.fetchone()
        
        if not voted_for_info:
            return jsonify({'error': '候選人不存在'}), 404
        
        voted_for_name = voted_for_info[0]
        voted_for_shift = voted_for_info[1]
        
        # 驗證投票規則(輪班投RR,RR投輪班)
        if voter_shift == '輪班' and voted_for_shift != 'RR':
            return jsonify({'error': '輪班只能投給RR'}), 400
        if voter_shift == 'RR' and voted_for_shift != '輪班':
            return jsonify({'error': 'RR只能投給輪班'}), 400
        
        # 記錄投票
        timestamp = datetime.now().isoformat()
        week_start = get_week_start()
        
        c.execute('''INSERT INTO votes 
                    (voter_emp_id, voter_name, voter_shift, 
                     voted_for_emp_id, voted_for_name, voted_for_shift, timestamp, week_start)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                 (voter_emp_id, voter_name, voter_shift,
                  voted_for_emp_id, voted_for_name, voted_for_shift, timestamp, week_start))
        
        # 更新投票者狀態(記錄投票時間)
        c.execute('UPDATE employees SET has_voted = 1, last_vote_time = ? WHERE emp_id = ?', 
                 (timestamp, voter_emp_id))
        
        # 更新每週投票記錄
        c.execute('''INSERT INTO weekly_votes (emp_id, week_start, shift_type, votes_used)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(emp_id, week_start) 
                    DO UPDATE SET votes_used = votes_used + 1''',
                 (voter_emp_id, week_start, voter_shift))
        
        conn.commit()
        
        new_votes_used = votes_used + 1
        remaining = max_votes - new_votes_used
        
        return jsonify({
            'success': True, 
            'message': f'投票成功! 本週已用 {new_votes_used}/{max_votes} 票' + 
                      (f', 還可投 {remaining} 票' if remaining > 0 else '')
        })
        
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# 獲取投票統計
@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    conn = sqlite3.connect('voting.db')
    c = conn.cursor()
    
    # 基本統計
    c.execute('SELECT COUNT(*) FROM employees')
    total_employees = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM employees WHERE has_voted = 1')
    voted_count = c.fetchone()[0]
    
    # 統計過去7天內的投票數
    seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
    c.execute('SELECT COUNT(*) FROM votes WHERE timestamp >= ?', (seven_days_ago,))
    recent_votes = c.fetchone()[0]
    
    # 得票統計
    c.execute('''SELECT voted_for_emp_id, voted_for_name, voted_for_shift, COUNT(*) as vote_count
                FROM votes
                GROUP BY voted_for_emp_id
                ORDER BY vote_count DESC''')
    
    vote_stats = []
    for row in c.fetchall():
        vote_stats.append({
            'emp_id': row[0],
            'name': row[1],
            'shift_type': row[2],
            'vote_count': row[3]
        })
    
    conn.close()
    
    return jsonify({
        'total_employees': total_employees,
        'voted_count': voted_count,
        'pending_count': total_employees - voted_count,
        'vote_rate': round((voted_count / total_employees * 100) if total_employees > 0 else 0, 2),
        'recent_votes': recent_votes,
        'vote_stats': vote_stats
    })

# 獲取所有投票記錄(後台用)
@app.route('/api/votes', methods=['GET'])
def get_votes():
    conn = sqlite3.connect('voting.db')
    c = conn.cursor()
    
    c.execute('''SELECT voter_emp_id, voter_name, voter_shift,
                       voted_for_emp_id, voted_for_name, voted_for_shift, timestamp
                FROM votes ORDER BY timestamp DESC''')
    
    votes = []
    for row in c.fetchall():
        votes.append({
            'voter_emp_id': row[0],
            'voter_name': row[1],
            'voter_shift': row[2],
            'voted_for_emp_id': row[3],
            'voted_for_name': row[4],
            'voted_for_shift': row[5],
            'timestamp': row[6]
        })
    
    conn.close()
    return jsonify(votes)

# 重置系統(清除所有投票,但保留7天限制)
@app.route('/api/reset', methods=['POST'])
def reset_system():
    reset_type = request.json.get('reset_type', 'votes_only')
    
    conn = sqlite3.connect('voting.db')
    c = conn.cursor()
    
    try:
        if reset_type == 'votes_only':
            # 只清除投票記錄,保留投票時間(維持7天限制)
            c.execute('DELETE FROM votes')
            c.execute('DELETE FROM weekly_votes')
        elif reset_type == 'full_reset':
            # 完全重置(清除投票記錄和投票時間)
            c.execute('DELETE FROM votes')
            c.execute('DELETE FROM weekly_votes')
            c.execute('UPDATE employees SET has_voted = 0, last_vote_time = NULL')
        
        conn.commit()
        return jsonify({'success': True, 'message': '系統已重置'})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# 重新載入員工資料
@app.route('/api/reload', methods=['POST'])
def reload_employees():
    conn = sqlite3.connect('voting.db')
    c = conn.cursor()
    
    try:
        # 清空資料
        c.execute('DELETE FROM employees')
        c.execute('DELETE FROM votes')
        c.execute('DELETE FROM weekly_votes')
        conn.commit()
        conn.close()
        
        # 重新載入
        if load_employees_from_json():
            return jsonify({'success': True, 'message': '員工資料已重新載入'})
        else:
            return jsonify({'error': '載入失敗'}), 500
            
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500

# 檢查員工投票狀態
@app.route('/api/check_status/<emp_id>', methods=['GET'])
def check_status(emp_id):
    conn = sqlite3.connect('voting.db')
    c = conn.cursor()
    
    c.execute('SELECT name, shift_type, has_voted, last_vote_time FROM employees WHERE emp_id = ?', (emp_id,))
    result = c.fetchone()
    
    if not result:
        conn.close()
        return jsonify({'error': '工號不存在'}), 404
    
    name = result[0]
    shift_type = result[1]
    week_start = get_week_start()
    
    can_vote_now, message, votes_used, max_votes = can_vote(emp_id, shift_type)
    
    response = {
        'name': name,
        'shift_type': shift_type,
        'has_voted': bool(result[2]),
        'last_vote_time': result[3],
        'can_vote': can_vote_now,
        'message': message if not can_vote_now else f'可以投票 (已用 {votes_used}/{max_votes} 票)',
        'votes_used': votes_used,
        'max_votes': max_votes,
        'week_start': week_start
    }
    
    conn.close()
    return jsonify(response)

# 檢查是否為管理員
@app.route('/api/check_admin/<emp_id>', methods=['GET'])
def check_admin(emp_id):
    """檢查是否為管理員"""
    is_admin = emp_id == 'K18251'
    return jsonify({'is_admin': is_admin})

# ==================== 配額管理 API ====================

# 獲取配額設定 (前端調用 /api/quotas)
@app.route('/api/quotas', methods=['GET'])
def get_quotas():
    """獲取當前週配額設定"""
    week_start = get_week_start()
    quota = get_or_create_quota(week_start)
    return jsonify(quota)

# 更新配額設定 (前端調用 /api/quotas)
@app.route('/api/quotas', methods=['POST'])
def update_quotas():
    """更新配額設定"""
    data = request.json
    rr_quota = data.get('rr_quota', 1)
    shift_quota = data.get('shift_quota', 1)
    
    # 驗證配額範圍
    if rr_quota < 1 or shift_quota < 1:
        return jsonify({'error': '配額必須至少為 1'}), 400
    
    if rr_quota > 10 or shift_quota > 10:
        return jsonify({'error': '配額不能超過 10'}), 400
    
    week_start = get_week_start()
    
    conn = sqlite3.connect('voting.db')
    c = conn.cursor()
    
    try:
        c.execute('''INSERT OR REPLACE INTO vote_quotas (week_start, rr_quota, shift_quota, created_at)
                    VALUES (?, ?, ?, ?)''', 
                 (week_start, rr_quota, shift_quota, datetime.now().isoformat()))
        conn.commit()
        return jsonify({
            'success': True, 
            'message': f'配額已更新: RR={rr_quota}票/週, 輪班={shift_quota}票/週',
            'rr_quota': rr_quota,
            'shift_quota': shift_quota
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# ==================== 每週統計 API ====================

# 獲取每週參與率統計 (供圖表使用)
@app.route('/api/weekly_stats', methods=['GET'])
def get_weekly_stats():
    """獲取每週投票參與統計,返回適合圖表顯示的格式"""
    weeks_count = int(request.args.get('weeks', 8))  # 預設顯示 8 週
    
    conn = sqlite3.connect('voting.db')
    c = conn.cursor()
    
    # 計算開始日期
    end_date = datetime.now()
    start_date = end_date - timedelta(weeks=weeks_count)
    
    # 獲取總員工數
    c.execute("SELECT COUNT(*) FROM employees WHERE shift_type = 'RR'")
    total_rr = c.fetchone()[0] or 1  # 避免除以零
    
    c.execute("SELECT COUNT(*) FROM employees WHERE shift_type = '輪班'")
    total_shift = c.fetchone()[0] or 1
    
    total_employees = total_rr + total_shift
    
    # 準備數據數組
    weeks = []
    rr_rates = []
    shift_rates = []
    total_rates = []
    rr_votes = []
    shift_votes = []
    total_votes = []
    
    current_date = start_date
    
    while current_date <= end_date:
        week_start = get_week_start(current_date)
        week_end = get_week_end(week_start)
        
        # 格式化週次標籤 (例如: "11-04")
        week_label = f"{week_start[5:]}"  # 只顯示月-日
        weeks.append(week_label)
        
        # 獲取該週 RR 投票人數
        c.execute('''SELECT COUNT(DISTINCT emp_id) FROM weekly_votes 
                    WHERE week_start = ? AND votes_used > 0 AND shift_type = 'RR' ''', (week_start,))
        rr_count = c.fetchone()[0]
        
        # 獲取該週輪班投票人數
        c.execute('''SELECT COUNT(DISTINCT emp_id) FROM weekly_votes 
                    WHERE week_start = ? AND votes_used > 0 AND shift_type = '輪班' ''', (week_start,))
        shift_count = c.fetchone()[0]
        
        # 獲取該週 RR 票數
        c.execute('''SELECT COUNT(*) FROM votes 
                    WHERE week_start = ? AND voter_shift = 'RR' ''', (week_start,))
        rr_vote_count = c.fetchone()[0]
        
        # 獲取該週輪班票數
        c.execute('''SELECT COUNT(*) FROM votes 
                    WHERE week_start = ? AND voter_shift = '輪班' ''', (week_start,))
        shift_vote_count = c.fetchone()[0]
        
        # 計算參與率
        rr_rate = round((rr_count / total_rr) * 100, 1) if total_rr > 0 else 0
        shift_rate = round((shift_count / total_shift) * 100, 1) if total_shift > 0 else 0
        total_rate = round(((rr_count + shift_count) / total_employees) * 100, 1) if total_employees > 0 else 0
        
        rr_rates.append(rr_rate)
        shift_rates.append(shift_rate)
        total_rates.append(total_rate)
        rr_votes.append(rr_vote_count)
        shift_votes.append(shift_vote_count)
        total_votes.append(rr_vote_count + shift_vote_count)
        
        current_date += timedelta(weeks=1)
    
    conn.close()
    
    return jsonify({
        'weeks': weeks,
        'rr_rates': rr_rates,
        'shift_rates': shift_rates,
        'total_rates': total_rates,
        'rr_votes': rr_votes,
        'shift_votes': shift_votes,
        'total_votes': total_votes
    })

# 獲取特定週的詳細統計
@app.route('/api/week_detail', methods=['GET'])
def get_week_detail():
    week_start = request.args.get('week_start', get_week_start())
    
    conn = sqlite3.connect('voting.db')
    c = conn.cursor()
    
    # 基本資訊
    quota = get_or_create_quota(week_start)
    week_end = get_week_end(week_start)
    
    # RR 投票統計
    c.execute('''SELECT voted_for_emp_id, voted_for_name, COUNT(*) as vote_count
                FROM votes
                WHERE week_start = ? AND voted_for_shift = 'RR'
                GROUP BY voted_for_emp_id
                ORDER BY vote_count DESC''', (week_start,))
    rr_ranking = [{'emp_id': row[0], 'name': row[1], 'vote_count': row[2]} for row in c.fetchall()]
    
    # 輪班投票統計
    c.execute('''SELECT voted_for_emp_id, voted_for_name, COUNT(*) as vote_count
                FROM votes
                WHERE week_start = ? AND voted_for_shift = '輪班'
                GROUP BY voted_for_emp_id
                ORDER BY vote_count DESC
                LIMIT 10''', (week_start,))
    shift_ranking = [{'emp_id': row[0], 'name': row[1], 'vote_count': row[2]} for row in c.fetchall()]
    
    # 投票者統計
    c.execute('''SELECT COUNT(DISTINCT emp_id) FROM weekly_votes 
                WHERE week_start = ? AND votes_used > 0 AND shift_type = 'RR' ''', (week_start,))
    rr_voters = c.fetchone()[0]
    
    c.execute('''SELECT COUNT(DISTINCT emp_id) FROM weekly_votes 
                WHERE week_start = ? AND votes_used > 0 AND shift_type = '輪班' ''', (week_start,))
    shift_voters = c.fetchone()[0]
    
    # 總投票數
    c.execute('SELECT COUNT(*) FROM votes WHERE week_start = ?', (week_start,))
    total_votes = c.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'week_start': week_start,
        'week_end': week_end,
        'quota': quota,
        'rr_ranking': rr_ranking,
        'shift_ranking': shift_ranking,
        'rr_voters': rr_voters,
        'shift_voters': shift_voters,
        'total_votes': total_votes
    })


if __name__ == '__main__':
    init_db()
    load_employees_from_json()
    app.run(debug=True, host='127.0.0.1', port=5000)