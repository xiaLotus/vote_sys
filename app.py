from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
import json
import os
import csv
import configparser
from pathlib import Path
from ldap3 import Server, Connection, ALL, NTLM # type: ignore
from ldap3.core.exceptions import LDAPException, LDAPBindError # type: ignore
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
    """取得指定年月的資料目錄,預設為當前月份"""
    if year is None or month is None:
        now = datetime.now()  # 👈 每次調用都動態取得當前時間
        year = now.year
        month = now.month
    
    month_dir = DATA_ROOT / str(year) / f"{month:02d}"
    month_dir.mkdir(parents=True, exist_ok=True)  # 👈 自動建立目錄!
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
    """從 INI 文件讀取配額設定（2000/3000 班別）"""
    config.read('config.ini', encoding='utf-8')
    quota_2000 = config.getint('VOTE_QUOTAS', 'quota_2000', fallback=3)
    quota_3000 = config.getint('VOTE_QUOTAS', 'quota_3000', fallback=2)
    return {
        '2000': quota_2000,   # ← key 改用 '2000'
        '3000': quota_3000    # ← key 改用 '3000'
    }

# 更新配額設定
def update_quota(quota_2000, quota_3000):
    """更新 INI 中的配額設定"""
    config.read('config.ini', encoding='utf-8')
    config.set('VOTE_QUOTAS', 'quota_2000', str(quota_2000))
    config.set('VOTE_QUOTAS', 'quota_3000', str(quota_3000))
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
    
    # ✅ 新增: 如果檔案不存在,嘗試從投票記錄重建
    if not monthly_votes_file.exists():
        logger.warning(f"⚠️ monthly_votes.csv 不存在於 {year}/{month},嘗試重建...")
        rebuild_monthly_votes_from_records(year, month)
        logger.info(f"✅ 重建完成，直接返回避免重複計數")
        return  # ← ⭐ 關鍵修改：重建後直接返回
    
    monthly_votes = read_csv(monthly_votes_file)
    found = False
    old_votes = 0
    
    for record in monthly_votes:
        if record['emp_id'] == emp_id:
            old_votes = int(record['votes_used'])
            record['votes_used'] = str(old_votes + 1)
            found = True
            logger.info(f"📊 更新票數：{emp_id} 從 {old_votes} → {record['votes_used']}")
            break
    
    if not found:
        monthly_votes.append({
            'emp_id': emp_id,
            'year_month': f"{year}{month:02d}",
            'shift_type': shift_type,
            'votes_used': '1'
        })
        logger.info(f"🆕 新增投票記錄：{emp_id} 始票數 1")
    
    write_csv(monthly_votes_file, monthly_votes, ['emp_id', 'year_month', 'shift_type', 'votes_used'])


def rebuild_monthly_votes_from_records(year=None, month=None):
    """
    從投票記錄重建月度統計
    用於 monthly_votes.csv 遺失或損壞時的恢復
    """
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month
    
    vote_file = get_month_file(year, month)
    votes = read_csv(vote_file)
    
    if not votes:
        logger.info(f"📊 {year}/{month} 無投票記錄,無需重建")
        return True
    
    # 統計每位員工的投票數
    vote_counts = {}
    employee_shifts = {}
    
    for vote in votes:
        voter_id = vote['voter_emp_id']
        voter_shift = vote.get('voter_shift', '2000')
        
        vote_counts[voter_id] = vote_counts.get(voter_id, 0) + 1
        employee_shifts[voter_id] = voter_shift
    
    # 重建 monthly_votes.csv
    monthly_votes = []
    for emp_id, count in vote_counts.items():
        monthly_votes.append({
            'emp_id': emp_id,
            'year_month': f"{year}{month:02d}",
            'shift_type': employee_shifts.get(emp_id, '2000'),
            'votes_used': str(count)
        })
    
    monthly_votes_file = get_monthly_votes_file(year, month)
    write_csv(monthly_votes_file, monthly_votes, 
              ['emp_id', 'year_month', 'shift_type', 'votes_used'])
    
    logger.info(f"✅ 成功重建 {year}/{month} 月度統計,共 {len(monthly_votes)} 筆記錄")
    return True




# 從 JSON 載入員工資料到當前月份
def load_employees_from_json(year=None, month=None):
    """從 emoinfo.json 載入員工資料到指定月份的 employees.csv"""
    try:
        # 讀取 JSON 檔案
        with open('emoinfo.json', 'r', encoding='utf-8-sig') as f:
            employees = json.load(f)
        
        # ✅ 新增: 驗證資料格式
        if not isinstance(employees, list):
            logger.error("❌ emoinfo.json 必須是陣列格式")
            return False
        
        if len(employees) == 0:
            logger.error("❌ emoinfo.json 為空陣列")
            return False
        
        # ✅ 新增: 驗證每筆資料的必要欄位
        required_fields = ['工號', '姓名', '班別']
        for i, emp in enumerate(employees):
            missing_fields = [f for f in required_fields if f not in emp]
            if missing_fields:
                logger.error(f"❌ 第 {i+1} 筆員工資料缺少欄位: {missing_fields}")
                return False
            
            # ✅ 新增: 驗證班別是否有效
            if emp['班別'] not in ['2000', '3000', 'RR', '輪班']:
                logger.warning(f"⚠️ 第 {i+1} 筆員工 {emp['工號']} 的班別 '{emp['班別']}' 無效,將使用預設值 2000")
        
        employees_file = get_employees_file(year, month)
        
        # 檢查是否已有資料
        existing = read_csv(employees_file)

        # 班別轉換表(統一成 2000 / 3000)
        shift_map = {
            'RR': '2000',
            '輪班': '3000',
            '2000': '2000',
            '3000': '3000'
        }
        
        if len(existing) == 0:
            # 插入員工資料
            employee_data = []
            for emp in employees:
                shift_raw = emp.get('班別', '2000')
                shift_final = shift_map.get(shift_raw, '2000')  # 預設 2000 防呆

                employee_data.append({
                    'emp_id': emp['工號'],
                    'name': emp['姓名'],
                    'shift_type': shift_final,  # 🔥 統一寫入 2000 / 3000
                    'has_voted': '0',
                    'last_vote_time': ''
                })
            
            write_csv(
                employees_file,
                employee_data,
                ['emp_id', 'name', 'shift_type', 'has_voted', 'last_vote_time']
            )
            logger.info(f'✅ 成功載入 {len(employees)} 位員工資料到 {year}/{month}')
        else:
            logger.info(f'ℹ️ {year}/{month} 已有員工資料,跳過載入')
        
        return True
        
    except FileNotFoundError:
        logger.error('❌ 找不到 emoinfo.json 檔案')
        return False
    except json.JSONDecodeError as e:
        logger.error(f'❌ JSON 格式錯誤: {e}')
        return False
    except PermissionError:
        logger.error('❌ 檔案權限不足,無法寫入')
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
    
    # ✅ 原始 shift_type ('RR'/'輪班') → 顯示名稱 ('2000'/'3000') → 取對應配額
    shift_display_map = {
        'RR': '2000',
        '輪班': '3000',
        '2000': '2000',
        '3000': '3000'
    }
    display_shift = shift_display_map.get(shift_type, '2000')
    max_votes = quota[display_shift]
    
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

# 班別統一映射
def normalize_shift(shift_type):
    """
    將所有班別轉換為一致的顯示格式：
    2000 → RR
    3000 → 輪班
    RR → RR
    輪班 → 輪班
    """
    mapping = {
        '2000': 'RR',
        '3000': '輪班',
        'RR': 'RR',
        '輪班': '輪班'
    }
    return mapping.get(shift_type, shift_type)

@app.route('/api/rebuild_monthly_votes', methods=['POST'])
def api_rebuild_monthly_votes():
    """管理員手動重建月度統計 API"""
    data = request.json
    year = data.get('year')
    month = data.get('month')
    
    if not year or not month:
        now = datetime.now()
        year = now.year
        month = now.month
    
    try:
        success = rebuild_monthly_votes_from_records(year, month)
        if success:
            return jsonify({
                'success': True,
                'message': f'成功重建 {year}年{month}月 的月度統計'
            })
        else:
            return jsonify({'error': '重建失敗'}), 500
    except Exception as e:
        logger.error(f"重建月度統計失敗: {str(e)}")
        return jsonify({'error': str(e)}), 500


# API 端點
@app.route('/api/employees', methods=['GET'])
def get_employees():
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)

    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month

    employees_file = get_employees_file(year, month)

    # 若無檔案，自動載入
    if not employees_file.exists():
        load_employees_from_json(year, month)

    employees = read_csv(employees_file)
    quota = get_quota()

    # ★ 班別防呆表
    shift_fix = {
        "RR": "2000",
        "輪班": "3000",
        "2000": "2000",
        "3000": "3000",
        "": "2000"   # 空值也給預設
    }

    result = []
    for emp in employees:
        emp_id = emp['emp_id']

        # ★ 修正後 shift_raw 永遠是 2000 / 3000
        shift_raw = shift_fix.get(emp['shift_type'], "2000")

        votes_used = get_or_create_monthly_votes(
            emp_id, shift_raw, year, month
        )

        max_votes = quota[shift_raw]

        result.append({
            'emp_id': emp_id,
            'name': emp['name'],
            'shift_type': shift_raw,      # 直接回傳 2000 / 3000
            'has_voted': emp['has_voted'] == '1',
            'last_vote_time': emp['last_vote_time'] or None,
            'votes_used': votes_used,
            'max_votes': max_votes
        })

    return jsonify(result)



@app.route('/api/vote', methods=['POST'])
def submit_vote():
    data = request.json
    voter_emp_id = data.get('voter_emp_id')
    voted_for_emp_ids = data.get('voted_for_emp_ids', [])

    year = data.get('year')
    month = data.get('month')

    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month

    employees_file = get_employees_file(year, month)
    employees = read_csv(employees_file, key_field='emp_id')

    if voter_emp_id not in employees:
        return jsonify({'error': '投票者工號不存在'}), 404

    voter = employees[voter_emp_id]
    voter_shift = voter['shift_type']  # 保留數字 2000 / 3000

    # 檢查配額
    can_vote_now, message, votes_used, max_votes = can_vote(voter_emp_id, voter_shift, year, month)
    if not can_vote_now:
        return jsonify({'error': message}), 403

    remaining = max_votes - votes_used
    if len(voted_for_emp_ids) > remaining:
        return jsonify({'error': f'投票數量超過配額，剩餘 {remaining}'}), 403

    voted_for_list = []
    for vid in voted_for_emp_ids:
        if vid not in employees:
            return jsonify({'error': f'候選人工號不存在: {vid}'}), 404
        
        target = employees[vid]
        target_shift = target['shift_type']  # 保留數字
        voted_for_list.append(target)

    vote_file = get_month_file(year, month)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 寫入記錄
    for target in voted_for_list:
        append_csv(
            vote_file,
            {
                'timestamp': timestamp,
                'year_month': f"{year}{month:02d}",
                'voter_emp_id': voter_emp_id,
                'voter_name': voter['name'],
                'voter_shift': voter_shift,  # ★ 保留 2000 / 3000
                'voted_for_emp_id': target['emp_id'],
                'voted_for_name': target['name'],
                'voted_for_shift': target['shift_type']  # ★ 保留 2000 / 3000
            },
            [
                'timestamp', 'year_month',
                'voter_emp_id', 'voter_name', 'voter_shift',
                'voted_for_emp_id', 'voted_for_name', 'voted_for_shift'
            ]
        )

        update_monthly_votes(voter_emp_id, voter_shift, year, month)

    voter['has_voted'] = '1'
    voter['last_vote_time'] = timestamp

    write_csv(
        employees_file,
        list(employees.values()),
        ['emp_id', 'name', 'shift_type', 'has_voted', 'last_vote_time']
    )

    new_used = votes_used + len(voted_for_emp_ids)

    return jsonify({
        'success': True,
        'message': f'投票成功 ({new_used}/{max_votes})',
        'votes_used': new_used,
        'max_votes': max_votes
    })


@app.route('/api/vote_stats', methods=['GET'])
def get_vote_stats():
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)

    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month

    vote_file = get_month_file(year, month)
    all_votes = read_csv(vote_file)

    rr_votes = {}
    shift_votes = {}

    for vote in all_votes:
        shift = vote.get('voted_for_shift')  # 2000 or 3000

        target_dict = rr_votes if shift == '2000' else shift_votes

        vid = vote['voted_for_emp_id']
        if vid not in target_dict:
            target_dict[vid] = {
                'emp_id': vid,
                'name': vote['voted_for_name'],
                'vote_count': 0,
                'shift_type': shift  # ★ 回傳數字
            }

        target_dict[vid]['vote_count'] += 1

    rr_ranking = sorted(rr_votes.values(), key=lambda x: x['vote_count'], reverse=True)
    shift_ranking = sorted(shift_votes.values(), key=lambda x: x['vote_count'], reverse=True)

    return jsonify({
        'year': year,
        'month': month,
        'rr_ranking': rr_ranking,
        'shift_ranking': shift_ranking
    })



@app.route('/api/monthly_participation', methods=['GET'])
def get_monthly_participation():
    months_count = int(request.args.get('months', 6))
    
    now = datetime.now()
    current_year = now.year
    current_month = now.month

    months_to_query = []
    for i in range(months_count - 1, -1, -1):
        month = current_month - i
        year = current_year
        while month < 1:
            month += 12
            year -= 1
        months_to_query.append((year, month))

    # fallback 最新月份
    fallback_employees = read_csv(get_employees_file(now.year, now.month))
    fallback_total_rr = sum(1 for emp in fallback_employees if normalize_shift(emp.get('shift_type')) == 'RR')
    fallback_total_shift = sum(1 for emp in fallback_employees if normalize_shift(emp.get('shift_type')) == '輪班')

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

        employees = read_csv(get_employees_file(year, month))

        total_rr = sum(1 for emp in employees if normalize_shift(emp.get('shift_type')) == 'RR')
        total_shift = sum(1 for emp in employees if normalize_shift(emp.get('shift_type')) == '輪班')
        total_employees = total_rr + total_shift

        if total_rr == 0:
            total_rr = max(1, fallback_total_rr)
        if total_shift == 0:
            total_shift = max(1, fallback_total_shift)
        if total_employees == 0:
            total_employees = fallback_total_rr + fallback_total_shift

        monthly_votes = read_csv(get_monthly_votes_file(year, month))

        rr_count = len([r for r in monthly_votes if normalize_shift(r.get('shift_type')) == 'RR' and int(r.get('votes_used', 0)) > 0])
        shift_count = len([r for r in monthly_votes if normalize_shift(r.get('shift_type')) == '輪班' and int(r.get('votes_used', 0)) > 0])

        all_votes = read_csv(get_month_file(year, month))
        rr_vote_count = sum(1 for v in all_votes if normalize_shift(v.get('voter_shift')) == 'RR')
        shift_vote_count = sum(1 for v in all_votes if normalize_shift(v.get('voter_shift')) == '輪班')

        rr_rates.append(min(100, round((rr_count / total_rr) * 100, 1)))
        shift_rates.append(min(100, round((shift_count / total_shift) * 100, 1)))
        total_rates.append(min(100, round(((rr_count + shift_count) / total_employees) * 100, 1)))

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
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)

    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month

    employees_file = get_employees_file(year, month)
    
    # ✅ 新增: 若檔案不存在,自動從 JSON 載入
    if not employees_file.exists():
        logger.warning(f"⚠️ employees.csv 不存在於 {year}/{month},自動載入...")
        load_employees_from_json(year, month)
    
    employees = read_csv(employees_file, key_field='emp_id')

    if emp_id not in employees:
        return jsonify({'error': '工號不存在'}), 404

    emp = employees[emp_id]

    # ✅ 關鍵修正:原始值 → 統一轉 2000/3000 再回傳
    shift_raw = emp['shift_type']
    shift_display_map = {'RR': '2000', '輪班': '3000', '2000': '2000', '3000': '3000'}
    display_shift = shift_display_map.get(shift_raw, '2000')

    can_vote_now, msg, votes_used, max_votes = can_vote(emp_id, shift_raw, year, month)

    return jsonify({
        'name': emp['name'],
        'shift_type': display_shift,      # ← 改為 2000 / 3000
        'has_voted': emp['has_voted'] == '1',
        'last_vote_time': emp['last_vote_time'] or None,
        'can_vote': can_vote_now,
        'message': msg if not can_vote_now else f"可以投票 (已用 {votes_used}/{max_votes})",
        'votes_used': votes_used,
        'max_votes': max_votes,
        'year': year,
        'month': month
    })


# 用戶認證函數
def authenticate_user(username, password):
    try:
        # server = Server('ldap://KHADDC02.kh.asegroup.com', get_info = ALL)
        # # 使用 NTLM
        # user = f'kh\\{username}'
        # password = f'{password}'

        # print("帳號: ", username, " 密碼: ", password)
        # # 建立連接
        # conn = Connection(server, user = user, password = password, authentication = NTLM)

        # # 嘗試綁定
        # if conn.bind():
        #     # app.logger.info(f"User {username} login successful.")
        #     return True
        # else:
        #     # app.logger.warning(f"Login failed for user {username}: {conn.last_error}")
        #     return False
        return True
    except Exception as e:
        # app.logger.error(f"Error during authentication for user {username}: {e}")
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
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    
    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month
    
    employees_file = get_employees_file(year, month)
    
    # ✅ 新增: 若檔案不存在,自動從 JSON 載入
    if not employees_file.exists():
        logger.warning(f"⚠️ employees.csv 不存在於 {year}/{month},自動載入...")
        load_employees_from_json(year, month)
    
    employees = read_csv(employees_file, key_field='emp_id')
    
    if emp_id not in employees:
        return jsonify({'error': '工號不存在,請確認您的工號'}), 404
    
    voter = employees[emp_id]
    voter_shift = normalize_shift(voter['shift_type'])

    can_vote_now, error_message, votes_used, max_votes = can_vote(emp_id, voter['shift_type'], year, month)
    
    if not can_vote_now:
        return jsonify({'error': error_message}), 400
    
    target_shift = 'RR' if voter_shift == '輪班' else '輪班'
    
    candidates = []
    for e_id, emp in employees.items():
        if normalize_shift(emp['shift_type']) == target_shift:
            candidates.append({
                'emp_id': emp['emp_id'],
                'name': emp['name'],
                'shift_type': normalize_shift(emp['shift_type'])
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
    quota = get_quota()  # {'2000': X, '3000': Y}

    return jsonify({
        'quota_2000': quota['2000'],
        'quota_3000': quota['3000']
    })

@app.route('/api/quotas', methods=['POST'])
def update_quotas():
    data = request.json
    # ✅ 改為接收新欄位
    quota_2000 = data.get('quota_2000', 3)
    quota_3000 = data.get('quota_3000', 2)
    
    if not (1 <= quota_2000 <= 20 and 1 <= quota_3000 <= 20):
        return jsonify({'error': '配額必須在 1-20 之間'}), 400
    
    try:
        update_quota(quota_2000, quota_3000)
        return jsonify({
            'success': True,
            'message': f'配額已更新：2000班={quota_2000}票/月，3000班={quota_3000}票/月',
            'quota_2000': quota_2000,
            'quota_3000': quota_3000
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/votes', methods=['GET'])
def get_votes():
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)

    if year is None or month is None:
        now = datetime.now()
        year = now.year
        month = now.month

    vote_file = get_month_file(year, month)
    votes = read_csv(vote_file)

    # ★ 不做任何 shift 轉換，照原樣（2000 / 3000）
    return jsonify({
        'votes': votes,
        'year': year,
        'month': month
    })



@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    try:
        now = datetime.now()
        year = now.year
        month = now.month
        vote_file = get_month_file(year, month)
        all_votes = read_csv(vote_file)
        
        vote_counts = {}
        for vote in all_votes:
            voted_for_id = vote['voted_for_emp_id']
            if voted_for_id not in vote_counts:
                vote_counts[voted_for_id] = {
                    'emp_id': voted_for_id,
                    'name': vote['voted_for_name'],
                    # 統一輸出 RR / 輪班
                    'shift_type': normalize_shift(vote['voted_for_shift']),
                    'vote_count': 0
                }
            vote_counts[voted_for_id]['vote_count'] += 1
        
        vote_stats = sorted(vote_counts.values(), key=lambda x: x['vote_count'], reverse=True)
        return jsonify({'vote_stats': vote_stats})
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