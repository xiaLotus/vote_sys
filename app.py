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
    
    # 員工表（加入最後投票時間）
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
    
    conn.commit()
    conn.close()

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

# 檢查是否可以投票（七天限制）
def can_vote(last_vote_time):
    if not last_vote_time:
        return True, None
    
    last_vote = datetime.fromisoformat(last_vote_time)
    now = datetime.now()
    time_diff = now - last_vote
    
    if time_diff >= timedelta(days=7):
        return True, None
    else:
        # 計算還需要等待多久
        remaining = timedelta(days=7) - time_diff
        days = remaining.days
        hours = remaining.seconds // 3600
        return False, f"您在 {days} 天 {hours} 小時前已投票，需等待 7 天後才能再次投票"

# 獲取所有員工
@app.route('/api/employees', methods=['GET'])
def get_employees():
    conn = sqlite3.connect('voting.db')
    c = conn.cursor()
    
    c.execute('SELECT emp_id, name, shift_type, has_voted, last_vote_time FROM employees ORDER BY emp_id')
    employees = []
    for row in c.fetchall():
        can_vote_now, message = can_vote(row[4])
        employees.append({
            'emp_id': row[0],
            'name': row[1],
            'shift_type': row[2],
            'has_voted': bool(row[3]),
            'last_vote_time': row[4],
            'can_vote': can_vote_now
        })
    
    conn.close()
    return jsonify(employees)

# 獲取候選人列表（根據投票者的班別）
@app.route('/api/candidates/<emp_id>', methods=['GET'])
def get_candidates(emp_id):
    conn = sqlite3.connect('voting.db')
    c = conn.cursor()
    
    # 查詢投票者的資訊
    c.execute('SELECT name, shift_type, has_voted, last_vote_time FROM employees WHERE emp_id = ?', (emp_id,))
    result = c.fetchone()
    
    if not result:
        conn.close()
        return jsonify({'error': '工號不存在，請確認您的工號'}), 404
    
    voter_name = result[0]
    voter_shift = result[1]
    has_voted = result[2]
    last_vote_time = result[3]
    
    # 檢查是否可以投票（七天限制）
    can_vote_now, error_message = can_vote(last_vote_time)
    
    if not can_vote_now:
        conn.close()
        return jsonify({'error': error_message}), 400
    
    # 根據班別返回候選人（輪班投RR，RR投輪班）
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
        'candidates': candidates
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
        
        # 檢查七天限制
        can_vote_now, error_message = can_vote(last_vote_time)
        if not can_vote_now:
            return jsonify({'error': error_message}), 400
        
        # 獲取被投票者資訊
        c.execute('SELECT name, shift_type FROM employees WHERE emp_id = ?', (voted_for_emp_id,))
        voted_for_info = c.fetchone()
        
        if not voted_for_info:
            return jsonify({'error': '候選人不存在'}), 404
        
        voted_for_name = voted_for_info[0]
        voted_for_shift = voted_for_info[1]
        
        # 驗證投票規則（輪班投RR，RR投輪班）
        if voter_shift == '輪班' and voted_for_shift != 'RR':
            return jsonify({'error': '輪班只能投給RR'}), 400
        if voter_shift == 'RR' and voted_for_shift != '輪班':
            return jsonify({'error': 'RR只能投給輪班'}), 400
        
        # 記錄投票
        timestamp = datetime.now().isoformat()
        c.execute('''INSERT INTO votes 
                    (voter_emp_id, voter_name, voter_shift, 
                     voted_for_emp_id, voted_for_name, voted_for_shift, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                 (voter_emp_id, voter_name, voter_shift,
                  voted_for_emp_id, voted_for_name, voted_for_shift, timestamp))
        
        # 更新投票者狀態（記錄投票時間）
        c.execute('UPDATE employees SET has_voted = 1, last_vote_time = ? WHERE emp_id = ?', 
                 (timestamp, voter_emp_id))
        
        conn.commit()
        return jsonify({'success': True, 'message': '投票成功！下次可投票時間：7 天後'})
        
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

# 獲取所有投票記錄（後台用）
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

# 重置系統（清除所有投票，但保留7天限制）
@app.route('/api/reset', methods=['POST'])
def reset_system():
    reset_type = request.json.get('reset_type', 'votes_only')
    
    conn = sqlite3.connect('voting.db')
    c = conn.cursor()
    
    try:
        if reset_type == 'votes_only':
            # 只清除投票記錄，保留投票時間（維持7天限制）
            c.execute('DELETE FROM votes')
        elif reset_type == 'full_reset':
            # 完全重置（清除投票記錄和投票時間）
            c.execute('DELETE FROM votes')
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
    
    can_vote_now, message = can_vote(result[3])
    
    response = {
        'name': result[0],
        'shift_type': result[1],
        'has_voted': bool(result[2]),
        'last_vote_time': result[3],
        'can_vote': can_vote_now,
        'message': message if not can_vote_now else '可以投票'
    }
    
    if result[3]:
        last_vote = datetime.fromisoformat(result[3])
        next_vote = last_vote + timedelta(days=7)
        response['next_vote_time'] = next_vote.strftime('%Y-%m-%d %H:%M')
    
    conn.close()
    return jsonify(response)


@app.route('/api/check_admin/<emp_id>', methods=['GET'])
def check_admin(emp_id):
    """檢查是否為管理員"""
    is_admin = emp_id == 'K18251'
    return jsonify({'is_admin': is_admin})


if __name__ == '__main__':
    init_db()
    load_employees_from_json()
    app.run(debug=True, host='127.0.0.1', port=5000)