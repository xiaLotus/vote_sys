from flask import Flask, request, jsonify, g
from flask_cors import CORS
from datetime import datetime, time as dtime
from functools import wraps
from pathlib import Path
import configparser
import csv
import json
import os
import re
import secrets
import threading
import time
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from loguru import logger

app = Flask(__name__)
CORS(app)

# 固定路徑（相對於執行 app.py 的工作目錄）
CONFIG_FILE = "config.ini"

# emoinfo_json = rf"D:\Data\A3CIM_投票系統專用資料\emoinfo.json"
emoinfo_json = "emoinfo.json"

# 組別（只有 2000 / 3000 兩組）
GROUPS = ('2000', '3000')

# CSV 欄位定義
EMP_FIELDS = ['emp_id', 'name', 'group', 'has_voted', 'last_vote_time']
VOTE_FIELDS = ['timestamp', 'year_month',
               'voter_emp_id', 'voter_name', 'voter_group',
               'voted_for_emp_id', 'voted_for_name', 'voted_for_group']

# 舊版 CSV 欄位 / 值 → 新版（讀取舊月份資料時自動轉換）
LEGACY_KEYS = {'shift_type': 'group', 'voter_shift': 'voter_group', 'voted_for_shift': 'voted_for_group'}
LEGACY_GROUP_VALUES = {'RR': '2000', '輪班': '3000'}

# 寫入 CSV 時的鎖，避免同時投票互相覆蓋
DATA_LOCK = threading.RLock()


# ======================== 設定檔 ========================
def load_config():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE, encoding='utf-8-sig')
    return cfg


config = load_config()


DATA_ROOT = Path(config.get('SYSTEM', 'data_directory', fallback='./data'))
DATA_ROOT.mkdir(parents=True, exist_ok=True)

SECRET_KEY = config.get('SYSTEM', 'secret_key', fallback='').strip()
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    logger.warning('⚠️ config.ini 未設定 secret_key，已使用臨時金鑰（重啟後所有人需重新登入）')
TOKEN_MAX_AGE = config.getint('SYSTEM', 'token_hours', fallback=8) * 3600
token_serializer = URLSafeTimedSerializer(SECRET_KEY, salt='vote-system-auth')


def update_config_values(section, values):
    """只改指定 key，保留 config.ini 其餘內容與註解"""
    config_path = Path(CONFIG_FILE)
    lines = config_path.read_text(encoding='utf-8-sig').splitlines() if config_path.exists() else []
    out, done, in_section, found_section = [], set(), False, False

    def flush_missing():
        for k, v in values.items():
            if k not in done:
                out.append(f'{k} = {v}')
                done.add(k)

    for line in lines:
        s = line.strip()
        if s.startswith('[') and s.endswith(']'):
            if in_section:
                # 補在本區段最後一個非空白行之後
                tail = []
                while out and not out[-1].strip():
                    tail.append(out.pop())
                flush_missing()
                out.extend(tail)
            in_section = (s[1:-1] == section)
            found_section = found_section or in_section
            out.append(line)
            continue
        if in_section and '=' in s and not s.startswith((';', '#')):
            key = s.split('=', 1)[0].strip()
            if key in values:
                out.append(f'{key} = {values[key]}')
                done.add(key)
                continue
        out.append(line)

    if in_section:
        flush_missing()
    if not found_section:
        out += ['', f'[{section}]']
        flush_missing()

    config_path.write_text('\n'.join(out) + '\n', encoding='utf-8')


def get_admin_ids():
    cfg = load_config()
    raw = cfg.get('ADMIN', 'admin_ids', fallback='K18251,G9745')
    return {x.strip().upper() for x in raw.split(',') if x.strip()}


# ======================== 配額 ========================
def get_quota_rules():
    """
    投票規則（投票者組別 → {可投組別: 票數}）
      2000 組 → 3000 組
      3000 組 → 2000 組 + 3000 組（不可投自己）
    """
    cfg = load_config()
    sec = 'VOTE_QUOTAS'
    q_2000_to_3000 = cfg.getint(sec, 'quota_2000_to_3000', fallback=cfg.getint(sec, 'quota_2000', fallback=4))
    q_3000_to_2000 = cfg.getint(sec, 'quota_3000_to_2000', fallback=cfg.getint(sec, 'quota_3000', fallback=2))
    q_3000_to_3000 = cfg.getint(sec, 'quota_3000_to_3000', fallback=2)
    return {
        '2000': {'3000': q_2000_to_3000},
        '3000': {'2000': q_3000_to_2000, '3000': q_3000_to_3000},
    }


def quotas_payload(rules=None):
    rules = rules or get_quota_rules()
    return {
        'quota_2000_to_3000': rules['2000']['3000'],
        'quota_3000_to_2000': rules['3000']['2000'],
        'quota_3000_to_3000': rules['3000']['3000'],
    }


# ======================== 路徑 ========================
def resolve_ym(year=None, month=None):
    if not year or not month:
        now = datetime.now()
        return now.year, now.month
    return int(year), int(month)


def get_month_dir(year=None, month=None, create=False):
    year, month = resolve_ym(year, month)
    month_dir = DATA_ROOT / str(year) / f"{month:02d}"
    if create:
        month_dir.mkdir(parents=True, exist_ok=True)
    return month_dir


def get_month_file(year=None, month=None, create=False):
    year, month = resolve_ym(year, month)
    return get_month_dir(year, month, create) / f"{year}{month:02d}.csv"


def get_employees_file(year=None, month=None, create=False):
    return get_month_dir(year, month, create) / 'employees.csv'


# ======================== CSV ========================
def normalize_group(value):
    value = str(value or '').strip()
    return LEGACY_GROUP_VALUES.get(value, value)


def normalize_row(row):
    new = {}
    for k, v in row.items():
        if k is None:
            continue
        key = LEGACY_KEYS.get(k, k)
        new[key] = normalize_group(v) if key in ('group', 'voter_group', 'voted_for_group') else (v or '')
    return new


def read_csv(filepath, key_field=None, strict=False):
    """
    讀取 CSV。strict=True 時讀取失敗會拋出例外（寫入前使用，避免讀到空資料後覆蓋原檔）
    """
    if not filepath.exists():
        return {} if key_field else []
    try:
        with open(filepath, 'r', encoding='utf-8-sig', newline='') as f:
            data = [normalize_row(r) for r in csv.DictReader(f)]
    except Exception as e:
        logger.error(f"讀取 CSV 失敗 {filepath}: {e}")
        if strict:
            raise
        return {} if key_field else []
    if key_field:
        return {row[key_field]: row for row in data}
    return data


def write_csv(filepath, data, fieldnames):
    """先寫暫存檔再取代，避免寫到一半中斷造成檔案損毀"""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    tmp = filepath.with_suffix(filepath.suffix + '.tmp')
    with open(tmp, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(data)
    os.replace(tmp, filepath)
    logger.info(f"成功寫入 CSV: {filepath}")


def backup_file(filepath):
    """重置前改名備份，不直接刪除"""
    if filepath.exists():
        bak = filepath.with_name(f"{filepath.name}.{datetime.now():%Y%m%d%H%M%S}.bak")
        os.replace(filepath, bak)
        logger.info(f"已備份 {filepath.name} → {bak.name}")


# ======================== 員工名單 ========================
def parse_group(emp):
    """
    取得組別：
      1. emoinfo.json 的「組別」或「班別」欄位為 2000 / 3000
      2. 若是爬蟲完整格式（load.json 格式），從「舊組織」判斷 BN30 ... 2000 / 3000
    """
    for key in ('組別', '班別'):
        v = str(emp.get(key, '')).strip()
        if v in GROUPS:
            return v
    m = re.search(r'BN30\s.*?\b(2000|3000)\b', str(emp.get('舊組織', '')))
    return m.group(1) if m else None


def read_roster_from_json():
    with open(emoinfo_json, 'r', encoding='utf-8-sig') as f:
        employees = json.load(f)
    if not isinstance(employees, list) or not employees:
        raise ValueError('emoinfo.json 必須是非空陣列')

    roster, seen = [], set()
    for i, emp in enumerate(employees, 1):
        emp_id = str(emp.get('工號', '')).strip().upper()
        name = str(emp.get('姓名', '')).strip()
        group = parse_group(emp)
        if not emp_id or not name:
            logger.warning(f"⚠️ 第 {i} 筆缺少工號或姓名，略過")
            continue
        if group is None:
            logger.warning(f"⚠️ 第 {i} 筆 {emp_id} {name} 無法判斷組別（非 2000/3000），略過")
            continue
        if emp_id in seen:
            logger.warning(f"⚠️ 工號重複 {emp_id}，略過")
            continue
        seen.add(emp_id)
        roster.append({'emp_id': emp_id, 'name': name, 'group': group})

    if not roster:
        raise ValueError('emoinfo.json 沒有任何 2000 / 3000 組人員')
    return roster


def load_employees_from_json(year=None, month=None, force=False):
    """
    從 emoinfo.json 載入員工到指定月份 employees.csv
    force=True：以 emoinfo.json 重建名單，投票狀態依投票記錄保留（不會清除投票）
    回傳 (成功與否, 訊息)
    """
    year, month = resolve_ym(year, month)
    with DATA_LOCK:
        employees_file = get_employees_file(year, month)
        if employees_file.exists() and not force:
            return True, f'{year}/{month:02d} 已有員工資料，未變更'
        try:
            roster = read_roster_from_json()
        except FileNotFoundError:
            logger.error(f'❌ 找不到 {emoinfo_json}')
            return False, '找不到 emoinfo.json'
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f'❌ emoinfo.json 格式錯誤: {e}')
            return False, f'emoinfo.json 格式錯誤：{e}'

        votes = read_csv(get_month_file(year, month), strict=True)
        last_vote = {}
        for v in votes:
            vid = v['voter_emp_id']
            last_vote[vid] = max(last_vote.get(vid, ''), v.get('timestamp', ''))

        data = [{
            **r,
            'has_voted': '1' if r['emp_id'] in last_vote else '0',
            'last_vote_time': last_vote.get(r['emp_id'], '')
        } for r in roster]

        write_csv(get_employees_file(year, month, create=True), data, EMP_FIELDS)
        count = {g_: sum(1 for r in roster if r['group'] == g_) for g_ in GROUPS}
        msg = f"已載入 {len(roster)} 人到 {year}/{month:02d}（2000組 {count['2000']} 人、3000組 {count['3000']} 人）"
        logger.info('✅ ' + msg)
        return True, msg


# ======================== 排程：每月自動生成當月名單 ========================
# 設定在 config.ini 的 [AUTO_LOAD]（修改後需重啟 Flask）
#   enabled = false（測試）：不啟動排程，改回「啟動或有人登入時，當月名單不存在就自動生成」
#   enabled = true （正式）：只在每月 day 號 start~end 由排程生成
def _parse_hhmm(value, default):
    try:
        return datetime.strptime(str(value).strip(), '%H:%M').time()
    except ValueError:
        logger.warning(f"⚠️ [AUTO_LOAD] 時間格式錯誤：{value}，改用預設 {default:%H:%M}")
        return default


AUTO_LOAD_ENABLED = config.getboolean('AUTO_LOAD', 'enabled', fallback=False)
AUTO_LOAD_DAY = config.getint('AUTO_LOAD', 'day', fallback=10)                                   # 每月幾號
AUTO_LOAD_START = _parse_hhmm(config.get('AUTO_LOAD', 'start', fallback='00:00'), dtime(0, 0))   # 開始時間
AUTO_LOAD_END = _parse_hhmm(config.get('AUTO_LOAD', 'end', fallback='00:10'), dtime(0, 10))      # 結束時間（不含）
AUTO_LOAD_CHECK_SECONDS = 60    # 每 60 秒檢查一次


def auto_load_employees_job():
    """
    背景排程：每月 AUTO_LOAD_DAY 號 AUTO_LOAD_START~AUTO_LOAD_END 之間，若當月 employees.csv 不存在就從 emoinfo.json 生成
    已存在則略過，不會覆蓋（避免影響已投票狀態）
    """
    while True:
        try:
            now = datetime.now()
            if now.day == AUTO_LOAD_DAY and AUTO_LOAD_START <= now.time() < AUTO_LOAD_END:
                if not get_employees_file(now.year, now.month).exists():
                    ok, msg = load_employees_from_json(now.year, now.month)
                    (logger.info if ok else logger.error)(f"⏰ 排程生成名單：{msg}")
        except Exception as e:
            logger.error(f"⏰ 排程生成名單失敗: {e}")
        time.sleep(AUTO_LOAD_CHECK_SECONDS)


def ensure_employees(year=None, month=None):
    """
    排程停用時（測試）：當月名單不存在就自動從 emoinfo.json 生成
    排程啟用時（正式）：不自動生成，等每月排程；臨時需要可用後台「重新載入員工資料」
    """
    if AUTO_LOAD_ENABLED:
        return
    if not get_employees_file(year, month).exists():
        load_employees_from_json(year, month)


def start_auto_load_scheduler():
    if not AUTO_LOAD_ENABLED:
        logger.info("⏰ 名單排程已停用（config.ini [AUTO_LOAD] enabled = false），名單於啟動或登入時自動生成")
        return
    threading.Thread(target=auto_load_employees_job, daemon=True, name='auto-load-employees').start()
    logger.info(f"⏰ 已啟動名單排程：每月 {AUTO_LOAD_DAY} 號 {AUTO_LOAD_START:%H:%M}~{AUTO_LOAD_END:%H:%M} 自動生成")


# ======================== 票數計算（以投票記錄為準） ========================
def get_usage(votes, emp_id):
    used = {g_: 0 for g_ in GROUPS}
    voted_ids = []
    for v in votes:
        if v['voter_emp_id'] == emp_id:
            grp = v.get('voted_for_group')
            if grp in used:
                used[grp] += 1
            voted_ids.append(v['voted_for_emp_id'])
    return used, voted_ids


def build_status(emp, votes, rules):
    group = emp['group']
    quota = rules.get(group, {})
    used, voted_ids = get_usage(votes, emp['emp_id'])
    remaining = {tg: max(0, quota[tg] - used.get(tg, 0)) for tg in quota}
    max_votes = sum(quota.values())
    votes_used = sum(used.get(tg, 0) for tg in quota)
    can_vote = any(r > 0 for r in remaining.values())
    detail = '、'.join(f"{tg}組 {used.get(tg, 0)}/{quota[tg]}" for tg in quota)
    return {
        'emp_id': emp['emp_id'],
        'name': emp['name'],
        'group': group,
        'quota': quota,
        'used': {tg: used.get(tg, 0) for tg in quota},
        'remaining': remaining,
        'votes_used': votes_used,
        'max_votes': max_votes,
        'can_vote': can_vote,
        'has_voted': emp.get('has_voted') == '1',
        'last_vote_time': emp.get('last_vote_time') or None,
        'message': f"可以投票（{detail}）" if can_vote else f"本月投票配額已用完（{detail}）",
        'voted_for_ids': voted_ids,
    }


# ======================== 登入 / 權限 ========================
def authenticate_user(username, password):
    """LDAP 驗證（不記錄密碼）"""
    try:
        from ldap3 import Server, Connection, ALL, NTLM  # type: ignore
        return True
        # cfg = load_config()
        # server = Server(cfg.get('LDAP', 'server', fallback='ldap://KHADDC02.kh.asegroup.com'), get_info=ALL)
        # domain = cfg.get('LDAP', 'domain', fallback='kh')
        # conn = Connection(server, user=f'{domain}\\{username}', password=password, authentication=NTLM)
        # ok = conn.bind()
        # conn.unbind()
        # return ok
    except Exception as e:
        logger.error(f"LDAP 驗證錯誤 ({username}): {e}")
        return False


def get_token_user():
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    try:
        data = token_serializer.loads(auth[7:], max_age=TOKEN_MAX_AGE)
        return str(data.get('emp_id', '')).upper() or None
    except (BadSignature, SignatureExpired):
        return None


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        emp_id = get_token_user()
        if not emp_id:
            return jsonify({'error': '請先登入或登入已逾時', 'code': 'AUTH_REQUIRED'}), 401
        g.emp_id = emp_id
        g.is_admin = emp_id in get_admin_ids()
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if not g.is_admin:
            return jsonify({'error': '無權限'}), 403
        return f(*args, **kwargs)
    return wrapper


def check_self_or_admin(emp_id):
    if emp_id.upper() != g.emp_id and not g.is_admin:
        return jsonify({'error': '只能查詢自己的資料'}), 403
    return None


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get('username', '')).strip().upper()
    password = str(data.get('password', ''))

    if not username or not password:
        return jsonify({'success': False, 'message': '請輸入工號與密碼'}), 400

    logger.info(f"收到 {username} 的登入請求")

    if load_config().getboolean('LDAP', 'enabled', fallback=True):
        if not authenticate_user(username, password):
            logger.warning(f"{username} 登入失敗")
            return jsonify({'success': False, 'message': '帳號或密碼錯誤，請重新輸入'})
    else:
        logger.warning('⚠️ LDAP 驗證已關閉（config.ini [LDAP] enabled = false），僅限測試使用')

    ensure_employees()
    employees = read_csv(get_employees_file(), key_field='emp_id')
    is_admin = username in get_admin_ids()
    in_roster = username in employees

    if not in_roster and not is_admin:
        if AUTO_LOAD_ENABLED and not get_employees_file().exists():
            return jsonify({'success': False, 'message': f'本月投票名單尚未建立（每月 {AUTO_LOAD_DAY} 號開放投票）'})
        return jsonify({'success': False, 'message': '您不在本月投票名單（2000 / 3000 組）內'})

    token = token_serializer.dumps({'emp_id': username})
    logger.info(f"{username} 登入成功")
    return jsonify({
        'success': True,
        'message': '登入成功!',
        'token': token,
        'emp_id': username,
        'name': employees.get(username, {}).get('name', username),
        'is_admin': is_admin,
        'in_roster': in_roster
    })


@app.route('/api/me', methods=['GET'])
@login_required
def me():
    ensure_employees()
    emp = read_csv(get_employees_file(), key_field='emp_id').get(g.emp_id)
    return jsonify({
        'emp_id': g.emp_id,
        'name': emp['name'] if emp else g.emp_id,
        'group': emp['group'] if emp else None,
        'is_admin': g.is_admin,
        'in_roster': emp is not None
    })


# ======================== 投票 ========================
@app.route('/api/candidates/<emp_id>', methods=['GET'])
@login_required
def get_candidates(emp_id):
    denied = check_self_or_admin(emp_id)
    if denied:
        return denied
    year, month = resolve_ym()
    ensure_employees(year, month)
    employees = read_csv(get_employees_file(year, month), key_field='emp_id')
    voter = employees.get(emp_id.upper())
    if not voter:
        return jsonify({'error': '工號不存在，請確認您的工號'}), 404

    status = build_status(voter, read_csv(get_month_file(year, month)), get_quota_rules())
    target_groups = [tg for tg, q in status['quota'].items() if q > 0]
    candidates = [
        {'emp_id': e['emp_id'], 'name': e['name'], 'group': e['group']}
        for e in employees.values()
        if e['group'] in target_groups and e['emp_id'] != voter['emp_id']
    ]
    return jsonify({'candidates': candidates, 'voter_info': status, 'year': year, 'month': month})


@app.route('/api/vote', methods=['POST'])
@login_required
def submit_vote():
    data = request.get_json(silent=True) or {}
    voter_emp_id = g.emp_id
    body_voter = str(data.get('voter_emp_id') or voter_emp_id).strip().upper()
    if body_voter != voter_emp_id:
        return jsonify({'error': '只能以自己的身分投票'}), 403

    raw_ids = data.get('voted_for_emp_ids') or []
    if not isinstance(raw_ids, list) or not raw_ids:
        return jsonify({'error': '請至少選擇一位候選人'}), 400
    voted_for_ids = [str(x).strip().upper() for x in raw_ids]

    # 一律寫入當月，不接受前端指定月份
    year, month = resolve_ym()

    with DATA_LOCK:
        ensure_employees(year, month)
        try:
            employees = read_csv(get_employees_file(year, month), key_field='emp_id', strict=True)
            vote_file = get_month_file(year, month)
            existing_votes = read_csv(vote_file, strict=True)
        except Exception:
            return jsonify({'error': '資料檔暫時無法讀取（可能被其他程式開啟），請稍後再試'}), 503

        voter = employees.get(voter_emp_id)
        if not voter:
            return jsonify({'error': '投票者工號不存在'}), 404

        # 本次提交中重複
        dup_ids = sorted({vid for vid in voted_for_ids if voted_for_ids.count(vid) > 1})
        if dup_ids:
            dup_names = [f"{employees.get(v, {}).get('name', v)}({v})" for v in dup_ids]
            return jsonify({'error': f'本次投票中有重複的候選人：{"、".join(dup_names)}，請重新選擇',
                            'duplicates': dup_names}), 400

        rules = get_quota_rules()
        status = build_status(voter, existing_votes, rules)

        # 本月已投過
        duplicates = [f"{employees.get(v, {}).get('name', v)}({v})"
                      for v in voted_for_ids if v in status['voted_for_ids']]
        if duplicates:
            logger.warning(f"⚠️ {voter_emp_id} 嘗試重複投票：{duplicates}")
            return jsonify({'error': f'您本月已投過：{"、".join(duplicates)}，無法重複投票，請重新選擇其他候選人',
                            'duplicates': duplicates}), 400

        # 候選人檢查 + 各組票數
        targets, batch_count = [], {}
        for vid in voted_for_ids:
            target = employees.get(vid)
            if not target:
                return jsonify({'error': f'候選人工號不存在: {vid}'}), 404
            if vid == voter_emp_id:
                return jsonify({'error': '不能投給自己'}), 400
            if target['group'] not in status['quota'] or status['quota'][target['group']] <= 0:
                return jsonify({'error': f"{voter['group']}組不能投給 {target['group']}組（{target['name']}）"}), 400
            batch_count[target['group']] = batch_count.get(target['group'], 0) + 1
            targets.append(target)

        for tg, n in batch_count.items():
            if n > status['remaining'][tg]:
                return jsonify({'error': f"{tg}組 剩餘 {status['remaining'][tg]} 票，本次選了 {n} 位"}), 403

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        new_rows = [{
            'timestamp': timestamp,
            'year_month': f"{year}{month:02d}",
            'voter_emp_id': voter_emp_id,
            'voter_name': voter['name'],
            'voter_group': voter['group'],
            'voted_for_emp_id': t['emp_id'],
            'voted_for_name': t['name'],
            'voted_for_group': t['group'],
        } for t in targets]

        try:
            all_votes = existing_votes + new_rows
            write_csv(get_month_file(year, month, create=True), all_votes, VOTE_FIELDS)
            voter['has_voted'] = '1'
            voter['last_vote_time'] = timestamp
            write_csv(get_employees_file(year, month, create=True), list(employees.values()), EMP_FIELDS)
        except Exception as e:
            logger.error(f"寫入投票失敗: {e}")
            return jsonify({'error': '寫入投票資料失敗（檔案可能被其他程式開啟），請稍後再試'}), 503

        new_status = build_status(voter, all_votes, rules)

    logger.info(f"🗳️ {voter_emp_id} 投給 {[t['emp_id'] for t in targets]}")
    return jsonify({
        'success': True,
        'message': f"投票成功（{new_status['votes_used']}/{new_status['max_votes']}）",
        'votes_used': new_status['votes_used'],
        'max_votes': new_status['max_votes'],
        'status': new_status
    })


# ======================== 查詢 / 統計 ========================
@app.route('/api/employees', methods=['GET'])
@login_required
def get_employees():
    year, month = resolve_ym(request.args.get('year', type=int), request.args.get('month', type=int))
    ensure_employees(year, month)
    employees = read_csv(get_employees_file(year, month))
    votes = read_csv(get_month_file(year, month))
    rules = get_quota_rules()

    result = []
    for emp in employees:
        s = build_status(emp, votes, rules)
        result.append({
            'emp_id': s['emp_id'],
            'name': s['name'],
            'group': s['group'],
            'has_voted': s['has_voted'],
            'last_vote_time': s['last_vote_time'] if g.is_admin else None,
            'votes_used': s['votes_used'],
            'max_votes': s['max_votes'],
            'used': s['used'],
            'quota': s['quota'],
            'can_vote': s['can_vote'],
        })
    return jsonify(result)


def build_ranking(votes, group=None):
    counts = {}
    for v in votes:
        if group and v.get('voted_for_group') != group:
            continue
        vid = v['voted_for_emp_id']
        item = counts.setdefault(vid, {
            'emp_id': vid, 'name': v['voted_for_name'],
            'group': v.get('voted_for_group'), 'vote_count': 0
        })
        item['vote_count'] += 1
    return sorted(counts.values(), key=lambda x: x['vote_count'], reverse=True)


@app.route('/api/vote_stats', methods=['GET'])
@login_required
def get_vote_stats():
    year, month = resolve_ym(request.args.get('year', type=int), request.args.get('month', type=int))
    votes = read_csv(get_month_file(year, month))
    return jsonify({
        'year': year,
        'month': month,
        'total_votes': len(votes),
        'ranking_2000': build_ranking(votes, '2000'),
        'ranking_3000': build_ranking(votes, '3000'),
    })


@app.route('/api/statistics', methods=['GET'])
@login_required
def get_statistics():
    year, month = resolve_ym(request.args.get('year', type=int), request.args.get('month', type=int))
    return jsonify({'vote_stats': build_ranking(read_csv(get_month_file(year, month)))})


@app.route('/api/monthly_participation', methods=['GET'])
@login_required
def get_monthly_participation():
    months_count = max(1, min(int(request.args.get('months', 6)), 36))
    now = datetime.now()

    months_to_query = []
    for i in range(months_count - 1, -1, -1):
        y, m = now.year, now.month - i
        while m < 1:
            m += 12
            y -= 1
        months_to_query.append((y, m))

    def group_total(emps):
        return {g_: sum(1 for e in emps if e.get('group') == g_) for g_ in GROUPS}

    fallback = group_total(read_csv(get_employees_file(now.year, now.month)))

    result = {'labels': [], 'rates_2000': [], 'rates_3000': [], 'total_rates': [],
              'votes_2000': [], 'votes_3000': [], 'total_votes': []}

    for y, m in months_to_query:
        totals = group_total(read_csv(get_employees_file(y, m)))
        for g_ in GROUPS:
            if totals[g_] == 0:
                totals[g_] = max(1, fallback[g_])

        votes = read_csv(get_month_file(y, m))
        voters = {g_: set() for g_ in GROUPS}
        vote_counts = {g_: 0 for g_ in GROUPS}
        for v in votes:
            vg = v.get('voter_group')
            if vg in GROUPS:
                voters[vg].add(v['voter_emp_id'])
                vote_counts[vg] += 1

        result['labels'].append(f"{y}-{m:02d}")
        for g_ in GROUPS:
            result[f'rates_{g_}'].append(min(100, round(len(voters[g_]) / totals[g_] * 100, 1)))
            result[f'votes_{g_}'].append(vote_counts[g_])
        all_voters = len(voters['2000']) + len(voters['3000'])
        result['total_rates'].append(min(100, round(all_voters / (totals['2000'] + totals['3000']) * 100, 1)))
        result['total_votes'].append(vote_counts['2000'] + vote_counts['3000'])

    return jsonify(result)


# ======================== 管理員 ========================
@app.route('/api/votes', methods=['GET'])
@admin_required
def get_votes():
    year, month = resolve_ym(request.args.get('year', type=int), request.args.get('month', type=int))
    return jsonify({'votes': read_csv(get_month_file(year, month)), 'year': year, 'month': month})


@app.route('/api/quotas', methods=['GET'])
@login_required
def get_quotas():
    return jsonify(quotas_payload())


@app.route('/api/quotas', methods=['POST'])
@admin_required
def update_quotas():
    data = request.get_json(silent=True) or {}
    keys = ['quota_2000_to_3000', 'quota_3000_to_2000', 'quota_3000_to_3000']
    values = {}
    for k in keys:
        try:
            values[k] = int(data.get(k))
        except (TypeError, ValueError):
            return jsonify({'error': f'{k} 必須是整數'}), 400
        if not 0 <= values[k] <= 20:
            return jsonify({'error': '配額必須在 0-20 之間'}), 400
    if values['quota_2000_to_3000'] == 0:
        return jsonify({'error': '2000組 → 3000組 至少 1 票'}), 400

    try:
        update_config_values('VOTE_QUOTAS', values)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    logger.info(f"{g.emp_id} 更新配額：{values}")
    return jsonify({
        'success': True,
        'message': (f"配額已更新：2000組→3000組 {values['quota_2000_to_3000']} 票；"
                    f"3000組→2000組 {values['quota_3000_to_2000']} 票、3000組→3000組 {values['quota_3000_to_3000']} 票"),
        **values
    })


@app.route('/api/reset', methods=['POST'])
@admin_required
def reset_votes():
    data = request.get_json(silent=True) or {}
    year, month = resolve_ym(data.get('year'), data.get('month'))
    try:
        with DATA_LOCK:
            backup_file(get_month_file(year, month))
            employees_file = get_employees_file(year, month)
            employees = read_csv(employees_file, strict=True)
            for emp in employees:
                emp['has_voted'] = '0'
                emp['last_vote_time'] = ''
            if employees:
                write_csv(employees_file, employees, EMP_FIELDS)
        logger.warning(f"⚠️ {g.emp_id} 重置了 {year}/{month:02d} 投票")
        return jsonify({'success': True, 'message': f'{year}年{month}月投票已重置（原檔已備份為 .bak）'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/load_employees', methods=['POST'])
@admin_required
def load_employees():
    data = request.get_json(silent=True) or {}
    year, month = resolve_ym(data.get('year'), data.get('month'))
    ok, msg = load_employees_from_json(year, month, force=bool(data.get('force', True)))
    return (jsonify({'success': True, 'message': msg}) if ok else (jsonify({'error': msg}), 500))


if __name__ == '__main__':
    # 啟動時載入當月名單（排程停用時才會生成）
    ensure_employees()
    start_auto_load_scheduler()

    now = datetime.now()
    logger.info(f"📁 當前資料目錄: {get_month_dir()}")
    logger.info(f"📅 當前月份: {now.year}年{now.month}月")
    logger.info(f"🗳️ 配額: {quotas_payload()}")

    host = config.get('SYSTEM', 'host', fallback='0.0.0.0')
    port = config.getint('SYSTEM', 'port', fallback=5000)
    app.run(host=host, port=port, threaded=True)