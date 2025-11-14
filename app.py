from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
import json
import os
import csv
import configparser
from pathlib import Path

from loguru import logger

app = Flask(__name__)
CORS(app)

# 讀取配置文件
config = configparser.ConfigParser()
config.read('config.ini', encoding='utf-8')

# 數據根目錄
DATA_ROOT = Path(config.get('SYSTEM', 'data_directory', fallback='./data'))
DATA_ROOT.mkdir(exist_ok=True)

# 獲取當前月份的資料目錄
def get_month_dir(year=None, month=None):
    """獲取指定年月的資料目錄，預設為當前月份"""
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month
    
    month_dir = DATA_ROOT / str(year) / f"{month:02d}"
    month_dir.mkdir(parents=True, exist_ok=True)
    return month_dir

# 獲取月份資料檔案路徑
def get_month_file(year=None, month=None):
    """獲取指定月份的投票記錄文件名 (格式: yyyymm.csv)"""
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month
    
    month_dir = get_month_dir(year, month)
    return month_dir / f"{year}{month:02d}.csv"

def get_monthly_votes_file(year=None, month=None):
    """獲取月度投票統計文件"""
    month_dir = get_month_dir(year, month)
    return month_dir / 'monthly_votes.csv'

def get_employees_file(year=None, month=None):
    """獲取員工資料文件"""
    month_dir = get_month_dir(year, month)
    return month_dir / 'employees.csv'

# CSV 操作輔助函數
def read_csv(filepath, key_field=None):
    """讀取 CSV 文件，返回列表或字典"""
    if not filepath.exists():
        return [] if key_field is None else {}
    
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            data = list(reader)
        
        if key_field:
            return {row[key_field]: row for row in data}
        return data
    except Exception as e:
        logger.error(f"讀取 CSV 失敗 {filepath}: {str(e)}")
        return [] if key_field is None else {}

def write_csv(filepath, data, fieldnames):
    """寫入 CSV 文件"""
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        logger.info(f"成功寫入 CSV: {filepath}")
    except Exception as e:
        logger.error(f"寫入 CSV 失敗 {filepath}: {str(e)}")
        raise

def append_csv(filepath, row, fieldnames):
    """追加一行到 CSV 文件"""
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        file_exists = filepath.exists()
        with open(filepath, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
        logger.info(f"成功追加到 CSV: {filepath}")
    except Exception as e:
        logger.error(f"追加 CSV 失敗 {filepath}: {str(e)}")
        raise

# 獲取配額
def get_quota():
    """從 INI 文件讀取配額設定"""
    config.read('config.ini', encoding='utf-8')
    rr_quota = config.getint('VOTE_QUOTAS', 'rr_quota', fallback=3)
    shift_quota = config.getint('VOTE_QUOTAS', 'shift_quota', fallback=3)
    return {
        'rr_quota': rr_quota,
        'shift_quota': shift_quota
    }

# 更新配額設定
def update_quota(rr_quota, shift_quota):
    """更新 INI 文件中的配額設定"""
    config.read('config.ini', encoding='utf-8')
    config.set('VOTE_QUOTAS', 'rr_quota', str(rr_quota))
    config.set('VOTE_QUOTAS', 'shift_quota', str(shift_quota))
    with open('config.ini', 'w', encoding='utf-8') as f:
        config.write(f)

# 獲取或創建員工本月投票記錄
def get_or_create_monthly_votes(emp_id, shift_type, year=None, month=None):
    """獲取員工本月已使用的票數"""
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month
    
    monthly_votes_file = get_monthly_votes_file(year, month)
    monthly_votes = read_csv(monthly_votes_file)
    
    for record in monthly_votes:
        if record['emp_id'] == emp_id:
            return int(record['votes_used'])
    
    return 0  # 如果不存在，返回 0

# 更新每月投票計數
def update_monthly_votes(emp_id, shift_type, year=None, month=None):
    """更新員工本月投票計數"""
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month
    
    monthly_votes_file = get_monthly_votes_file(year, month)
    monthly_votes = read_csv(monthly_votes_file)
    found = False
    
    for record in monthly_votes:
        if record['emp_id'] == emp_id:
            record['votes_used'] = str(int(record['votes_used']) + 1)
            found = True
            break
    
    if not found:
        monthly_votes.append({
            'emp_id': emp_id,
            'year_month': f"{year}{month:02d}",
            'shift_type': shift_type,
            'votes_used': '1'
        })
    
    write_csv(monthly_votes_file, monthly_votes, ['emp_id', 'year_month', 'shift_type', 'votes_used'])

# 從 JSON 載入員工資料到當前月份
def load_employees_from_json(year=None, month=None):
    """從 emoinfo.json 載入員工資料到指定月份的 employees.csv"""
    try:
        with open('emoinfo.json', 'r', encoding='utf-8-sig') as f:
            employees = json.load(f)
        
        employees_file = get_employees_file(year, month)
        
        # 檢查是否已有資料
        existing = read_csv(employees_file)
        
        if len(existing) == 0:
            # 插入員工資料
            employee_data = []
            for emp in employees:
                employee_data.append({
                    'emp_id': emp['工號'],
                    'name': emp['姓名'],
                    'shift_type': emp['班別'],
                    'has_voted': '0',
                    'last_vote_time': ''
                })
            
            write_csv(employees_file, employee_data, 
                     ['emp_id', 'name', 'shift_type', 'has_voted', 'last_vote_time'])
            logger.info(f'✅ 成功載入 {len(employees)} 位員工資料到 {year}/{month}')
        
        return True
    except FileNotFoundError:
        logger.error('❌ 找不到 emoinfo.json 檔案')
        return False
    except Exception as e:
        logger.error(f'❌ 載入員工資料失敗: {str(e)}')
        return False

# 檢查是否可以投票
def can_vote(emp_id, shift_type, year=None, month=None):
    """檢查員工本月是否還可以投票"""
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month
    
    quota = get_quota()
    votes_used = get_or_create_monthly_votes(emp_id, shift_type, year, month)
    
    max_votes = quota['rr_quota'] if shift_type == 'RR' else quota['shift_quota']
    
    if votes_used < max_votes:
        return True, None, votes_used, max_votes
    else:
        return False, f"本月投票配額已用完 ({votes_used}/{max_votes})", votes_used, max_votes

# 讀取投票記錄（可跨月）
def read_votes_by_months(months_list):
    """
    讀取指定月份的投票記錄
    months_list: [(year, month), ...] 列表
    """
    all_votes = []
    
    for year, month in months_list:
        file = get_month_file(year, month)
        votes = read_csv(file)
        all_votes.extend(votes)
    
    return all_votes

# 讀取本月投票記錄
def read_current_month_votes():
    """讀取當前月份的投票記錄"""
    now = datetime.now()
    return read_csv(get_month_file(now.year, now.month))

# 獲取可用的歷史月份列表
def get_available_months():
    """獲取所有有資料的年月列表"""
    months = []
    
    if not DATA_ROOT.exists():
        return months
    
    for year_dir in sorted(DATA_ROOT.iterdir()):
        if year_dir.is_dir() and year_dir.name.isdigit():
            year = int(year_dir.name)
            for month_dir in sorted(year_dir.iterdir()):
                if month_dir.is_dir() and month_dir.name.isdigit():
                    month = int(month_dir.name)
                    # 檢查是否有投票資料檔案
                    vote_file = month_dir / f"{year}{month:02d}.csv"
                    if vote_file.exists():
                        months.append({
                            'year': year,
                            'month': month,
                            'label': f"{year}年{month}月"
                        })
    
    return months

# API 端點
@app.route('/api/employees', methods=['GET'])
def get_employees():
    """獲取所有員工"""
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month
    
    quota = get_quota()
    employees_file = get_employees_file(year, month)
    employees = read_csv(employees_file)
    
    result = []
    for emp in employees:
        emp_id = emp['emp_id']
        shift_type = emp['shift_type']
        votes_used = get_or_create_monthly_votes(emp_id, shift_type, year, month)
        max_votes = quota['rr_quota'] if shift_type == 'RR' else quota['shift_quota']
        
        result.append({
            'emp_id': emp_id,
            'name': emp['name'],
            'shift_type': shift_type,
            'has_voted': emp['has_voted'] == '1',
            'last_vote_time': emp['last_vote_time'] if emp['last_vote_time'] else None,
            'votes_used': votes_used,
            'max_votes': max_votes
        })
    
    return jsonify(result)


@app.route('/api/vote', methods=['POST'])
def submit_vote():
    """提交投票 - 支援批量投票"""
    data = request.json
    voter_emp_id = data.get('voter_emp_id')
    voted_for_emp_ids = data.get('voted_for_emp_ids', [])
    
    year = data.get('year')
    month = data.get('month')
    
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month
    
    # 驗證參數
    if not voter_emp_id:
        return jsonify({'error': '缺少投票者工號'}), 400
    
    if not voted_for_emp_ids or not isinstance(voted_for_emp_ids, list):
        return jsonify({'error': '請選擇至少一位候選人'}), 400
    
    employees_file = get_employees_file(year, month)
    employees = read_csv(employees_file, key_field='emp_id')
    
    # 驗證投票者
    if voter_emp_id not in employees:
        return jsonify({'error': f'投票者工號不存在: {voter_emp_id}'}), 404
    
    voter = employees[voter_emp_id]
    voter_shift = voter['shift_type']
    
    # 檢查配額
    can_vote_now, message, votes_used, max_votes = can_vote(voter_emp_id, voter_shift, year, month)
    
    if not can_vote_now:
        return jsonify({'error': message}), 403
    
    # 檢查是否有足夠配額
    remaining_votes = max_votes - votes_used
    if len(voted_for_emp_ids) > remaining_votes:
        return jsonify({'error': f'投票數量超過配額!剩餘 {remaining_votes} 票,但嘗試投 {len(voted_for_emp_ids)} 票'}), 403
    
    # 驗證所有被投票者
    voted_for_list = []
    for voted_for_id in voted_for_emp_ids:
        if voted_for_id not in employees:
            return jsonify({'error': f'候選人工號不存在: {voted_for_id}'}), 404
        
        voted_for = employees[voted_for_id]
        voted_for_shift = voted_for['shift_type']
        
        # 同班別不能互投
        if voter_shift == voted_for_shift:
            return jsonify({'error': f'{voter_shift} 不能投給 {voted_for_shift}'}), 400
        
        voted_for_list.append(voted_for)
    
    # 批量記錄投票
    vote_file = get_month_file(year, month)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    for voted_for in voted_for_list:
        vote_record = {
            'timestamp': timestamp,
            'year_month': f"{year}{month:02d}",
            'voter_emp_id': voter_emp_id,
            'voter_name': voter['name'],
            'voter_shift': voter_shift,
            'voted_for_emp_id': voted_for['emp_id'],
            'voted_for_name': voted_for['name'],
            'voted_for_shift': voted_for['shift_type']
        }
        
        append_csv(vote_file, vote_record, 
                  ['timestamp', 'year_month', 'voter_emp_id', 'voter_name', 'voter_shift',
                   'voted_for_emp_id', 'voted_for_name', 'voted_for_shift'])
        
        # 每投一票就更新一次月度計數
        update_monthly_votes(voter_emp_id, voter_shift, year, month)
    
    # 更新員工投票狀態
    voter['has_voted'] = '1'
    voter['last_vote_time'] = timestamp
    
    write_csv(employees_file, list(employees.values()),
             ['emp_id', 'name', 'shift_type', 'has_voted', 'last_vote_time'])
    
    # 計算新的使用票數
    new_votes_used = votes_used + len(voted_for_emp_ids)
    
    return jsonify({
        'success': True,
        'message': f'投票成功!已投給 {len(voted_for_emp_ids)} 位候選人 ({new_votes_used}/{max_votes})',
        'votes_used': new_votes_used,
        'max_votes': max_votes,
        'voted_count': len(voted_for_emp_ids)
    })



@app.route('/api/vote_stats', methods=['GET'])
def get_vote_stats():
    """獲取投票統計（可指定月份）"""
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month
    
    vote_file = get_month_file(year, month)
    all_votes = read_csv(vote_file)
    
    # RR 投票統計
    rr_votes = {}
    for vote in all_votes:
        if vote.get('voted_for_shift') == 'RR':
            voted_for_id = vote['voted_for_emp_id']
            if voted_for_id not in rr_votes:
                rr_votes[voted_for_id] = {
                    'emp_id': voted_for_id,
                    'name': vote['voted_for_name'],
                    'vote_count': 0
                }
            rr_votes[voted_for_id]['vote_count'] += 1
    
    rr_ranking = sorted(rr_votes.values(), key=lambda x: x['vote_count'], reverse=True)
    
    # 輪班投票統計
    shift_votes = {}
    for vote in all_votes:
        if vote.get('voted_for_shift') == '輪班':
            voted_for_id = vote['voted_for_emp_id']
            if voted_for_id not in shift_votes:
                shift_votes[voted_for_id] = {
                    'emp_id': voted_for_id,
                    'name': vote['voted_for_name'],
                    'vote_count': 0
                }
            shift_votes[voted_for_id]['vote_count'] += 1
    
    shift_ranking = sorted(shift_votes.values(), key=lambda x: x['vote_count'], reverse=True)[:10]
    
    # 投票者統計
    monthly_votes_file = get_monthly_votes_file(year, month)
    monthly_votes_data = read_csv(monthly_votes_file)
    
    rr_voters = len([r for r in monthly_votes_data 
                     if r['shift_type'] == 'RR' and int(r['votes_used']) > 0])
    shift_voters = len([r for r in monthly_votes_data 
                        if r['shift_type'] == '輪班' and int(r['votes_used']) > 0])
    
    total_votes = len(all_votes)
    
    return jsonify({
        'year': year,
        'month': month,
        'rr_ranking': rr_ranking,
        'shift_ranking': shift_ranking,
        'rr_voters': rr_voters,
        'shift_voters': shift_voters,
        'total_votes': total_votes
    })

@app.route('/api/monthly_participation', methods=['GET'])
def get_monthly_participation():
    """獲取最近幾個月的參與率統計"""
    months_count = int(request.args.get('months', 6))
    
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    
    # 計算要查詢的月份列表
    months_to_query = []
    for i in range(months_count):
        month = current_month - i
        year = current_year
        
        while month < 1:
            month += 12
            year -= 1
        
        months_to_query.append((year, month))
    
    months_to_query.reverse()  # 從舊到新排序
    
    # 獲取第一個月的員工資料來計算總人數
    first_year, first_month = months_to_query[0]
    employees_file = get_employees_file(first_year, first_month)
    employees = read_csv(employees_file)
    
    total_rr = sum(1 for emp in employees if emp['shift_type'] == 'RR')
    total_shift = sum(1 for emp in employees if emp['shift_type'] == '輪班')
    total_employees = total_rr + total_shift

    if total_rr == 0:
        total_rr = 1
    if total_shift == 0:
        total_shift = 1
    if total_employees == 0:
        total_employees = 1
    
    # 準備數據數組
    labels = []
    rr_rates = []
    shift_rates = []
    total_rates = []
    rr_votes_list = []
    shift_votes_list = []
    total_votes_list = []
    
    for year, month in months_to_query:
        label = f"{year}-{month:02d}"
        labels.append(label)
        
        monthly_votes_file = get_monthly_votes_file(year, month)
        monthly_votes_data = read_csv(monthly_votes_file)
        
        # 獲取該月 RR 投票人數
        rr_count = len([r for r in monthly_votes_data 
                       if r['shift_type'] == 'RR' and int(r['votes_used']) > 0])
        
        # 獲取該月輪班投票人數
        shift_count = len([r for r in monthly_votes_data 
                          if r['shift_type'] == '輪班' and int(r['votes_used']) > 0])
        
        # 獲取該月 RR 票數
        vote_file = get_month_file(year, month)
        all_votes = read_csv(vote_file)
        
        rr_vote_count = sum(1 for vote in all_votes if vote.get('voter_shift') == 'RR')
        shift_vote_count = sum(1 for vote in all_votes if vote.get('voter_shift') == '輪班')
        
        # 計算參與率
        rr_rate = round((rr_count / total_rr) * 100, 1)
        shift_rate = round((shift_count / total_shift) * 100, 1)
        total_rate = round(((rr_count + shift_count) / total_employees) * 100, 1)
        
        rr_rates.append(rr_rate)
        shift_rates.append(shift_rate)
        total_rates.append(total_rate)
        rr_votes_list.append(rr_vote_count)
        shift_votes_list.append(shift_vote_count)
        total_votes_list.append(rr_vote_count + shift_vote_count)
    
    return jsonify({
        'labels': labels,
        'rr_rates': rr_rates,
        'shift_rates': shift_rates,
        'total_rates': total_rates,
        'rr_votes': rr_votes_list,
        'shift_votes': shift_votes_list,
        'total_votes': total_votes_list
    })

@app.route('/api/available_months', methods=['GET'])
def get_months_list():
    """獲取所有可用的月份列表"""
    months = get_available_months()
    return jsonify(months)

@app.route('/api/reset', methods=['POST'])
def reset_votes():
    """重置本月投票（僅管理員）"""
    data = request.json
    admin_id = data.get('admin_id')
    year = data.get('year')
    month = data.get('month')
    
    if admin_id not in ['K18251', 'G9745']:
        return jsonify({'error': '無權限'}), 403
    
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month
    
    try:
        # 刪除投票記錄
        vote_file = get_month_file(year, month)
        if vote_file.exists():
            vote_file.unlink()
        
        # 刪除月度統計
        monthly_votes_file = get_monthly_votes_file(year, month)
        if monthly_votes_file.exists():
            monthly_votes_file.unlink()
        
        # 重置員工投票狀態
        employees_file = get_employees_file(year, month)
        employees = read_csv(employees_file)
        
        for emp in employees:
            emp['has_voted'] = '0'
            emp['last_vote_time'] = ''
        
        write_csv(employees_file, employees,
                 ['emp_id', 'name', 'shift_type', 'has_voted', 'last_vote_time'])
        
        return jsonify({'success': True, 'message': f'{year}年{month}月投票已重置'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/load_employees', methods=['POST'])
def load_employees():
    """從 JSON 載入員工資料"""
    data = request.json
    year = data.get('year')
    month = data.get('month')
    
    try:
        if load_employees_from_json(year, month):
            return jsonify({'success': True, 'message': f'員工資料已載入到 {year}/{month}'})
        else:
            return jsonify({'error': '載入失敗'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/check_status/<emp_id>', methods=['GET'])
def check_status(emp_id):
    """檢查員工投票狀態"""
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month
    
    employees_file = get_employees_file(year, month)
    employees = read_csv(employees_file, key_field='emp_id')
    
    if emp_id not in employees:
        return jsonify({'error': '工號不存在'}), 404
    
    emp = employees[emp_id]
    shift_type = emp['shift_type']
    
    can_vote_now, message, votes_used, max_votes = can_vote(emp_id, shift_type, year, month)
    
    response = {
        'name': emp['name'],
        'shift_type': shift_type,
        'has_voted': emp['has_voted'] == '1',
        'last_vote_time': emp['last_vote_time'] if emp['last_vote_time'] else None,
        'can_vote': can_vote_now,
        'message': message if not can_vote_now else f'可以投票 (已用 {votes_used}/{max_votes} 票)',
        'votes_used': votes_used,
        'max_votes': max_votes,
        'year': year,
        'month': month
    }
    
    return jsonify(response)

# 用戶認證函數
def authenticate_user(username, password):
    """驗證用戶登入"""
    try:
        # ✅ 測試模式：所有登入都允許
        logger.info(f"{username} 成功登入")
        return True
    except Exception as e:
        logger.error(f"拋出異常的使用者: {username}, 異常為: {str(e)}")
        return False

@app.route('/api/login', methods=['POST'])
def login():
    """用戶登入 API"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    logger.info(f"收到用戶名為 {username} 的登錄請求")
    
    if authenticate_user(username, password):
        logger.info(f"用戶名為 {username} 的登錄成功")
        return jsonify({"success": True, "message": "登入成功!"})
    else:
        logger.warning(f"用戶名為 {username} 的登錄失敗")
        return jsonify({"success": False, "message": "帳號或密碼錯誤,請重新輸入"})

@app.route('/api/candidates/<emp_id>', methods=['GET'])
def get_candidates(emp_id):
    """獲取候選人列表"""
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month
    
    employees_file = get_employees_file(year, month)
    employees = read_csv(employees_file, key_field='emp_id')
    
    if emp_id not in employees:
        return jsonify({'error': '工號不存在,請確認您的工號'}), 404
    
    voter = employees[emp_id]
    voter_shift = voter['shift_type']
    
    # 檢查是否可以投票
    can_vote_now, error_message, votes_used, max_votes = can_vote(emp_id, voter_shift, year, month)
    
    if not can_vote_now:
        return jsonify({'error': error_message}), 400
    
    # 根據班別返回候選人
    target_shift = 'RR' if voter_shift == '輪班' else '輪班'
    
    candidates = []
    for e_id, emp in employees.items():
        if emp['shift_type'] == target_shift:
            candidates.append({
                'emp_id': emp['emp_id'],
                'name': emp['name'],
                'shift_type': emp['shift_type']
            })
    
    return jsonify({
        'candidates': candidates,
        'voter_info': {
            'emp_id': emp_id,
            'name': voter['name'],
            'shift_type': voter_shift,
            'votes_used': votes_used,
            'max_votes': max_votes
        }
    })

@app.route('/api/check_admin/<emp_id>', methods=['GET'])
def check_admin(emp_id):
    """檢查是否為管理員"""
    is_admin = emp_id in ['K18251', 'G9745']
    return jsonify({'is_admin': is_admin})

@app.route('/api/quotas', methods=['GET'])
def get_quotas():
    """獲取配額設定"""
    quota = get_quota()
    return jsonify(quota)

@app.route('/api/quotas', methods=['POST'])
def update_quotas():
    """更新配額設定"""
    data = request.json
    rr_quota = data.get('rr_quota', 3)
    shift_quota = data.get('shift_quota', 3)
    
    # 驗證配額範圍
    if rr_quota < 1 or shift_quota < 1:
        return jsonify({'error': '配額必須至少為 1'}), 400
    
    if rr_quota > 20 or shift_quota > 20:
        return jsonify({'error': '配額不能超過 20'}), 400
    
    try:
        update_quota(rr_quota, shift_quota)
        return jsonify({
            'success': True, 
            'message': f'配額已更新: RR={rr_quota}票/月, 輪班={shift_quota}票/月',
            'rr_quota': rr_quota,
            'shift_quota': shift_quota
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/votes', methods=['GET'])
def get_votes():
    """獲取投票記錄"""
    try:
        year = request.args.get('year', type=int)
        month = request.args.get('month', type=int)
        
        if year is None or month is None:
            now = datetime.now()
            year = now.year
            month = now.month
        
        vote_file = get_month_file(year, month)
        votes = read_csv(vote_file)
        
        return jsonify({
            'votes': votes,
            'year': year,
            'month': month
        })
    except Exception as e:
        logger.error(f'獲取投票記錄失敗: {str(e)}')
        return jsonify({'votes': [], 'year': year, 'month': month})
    

@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    """獲取投票統計 - 用於前端排行榜"""
    try:
        now = datetime.now()
        year = now.year
        month = now.month
        
        vote_file = get_month_file(year, month)
        all_votes = read_csv(vote_file)
        
        # 統計所有候選人的得票數
        vote_counts = {}
        for vote in all_votes:
            voted_for_id = vote['voted_for_emp_id']
            if voted_for_id not in vote_counts:
                vote_counts[voted_for_id] = {
                    'emp_id': voted_for_id,
                    'name': vote['voted_for_name'],
                    'shift_type': vote['voted_for_shift'],
                    'vote_count': 0
                }
            vote_counts[voted_for_id]['vote_count'] += 1
        
        # 轉換為列表並排序
        vote_stats = sorted(vote_counts.values(), key=lambda x: x['vote_count'], reverse=True)
        
        return jsonify({
            'vote_stats': vote_stats
        })
    except Exception as e:
        logger.error(f'獲取統計數據失敗: {str(e)}')
        return jsonify({'vote_stats': []})



if __name__ == '__main__':
    # 啟動時載入員工資料到當前月份（如果不存在）
    load_employees_from_json()
    
    # 顯示當前月份的資料目錄
    now = datetime.now()
    current_dir = get_month_dir()
    logger.info(f"📁 當前資料目錄: {current_dir}")
    logger.info(f"📅 當前月份: {now.year}年{now.month}月")
    
    app.run(debug=True, host='127.0.0.1', port=5000)