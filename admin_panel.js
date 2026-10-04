// 後端位址：預設與網頁同一台主機的 5000 port
const API_BASE = window.API_BASE || `http://${location.hostname || '127.0.0.1'}:5000`;

function getSession() {
    try {
        return {
            token: sessionStorage.getItem('vote_token'),
            user: JSON.parse(sessionStorage.getItem('vote_user') || 'null')
        };
    } catch (e) {
        return { token: null, user: null };
    }
}

async function apiFetch(path, options = {}) {
    const { token } = getSession();
    const response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token || ''}`,
            ...(options.headers || {})
        }
    });
    if (response.status === 401) {
        window.location.href = 'login.html';
        throw new Error('登入已逾時');
    }
    const data = await response.json().catch(() => ({}));
    return { ok: response.ok, status: response.status, data };
}

const SWAL_CLASS = {
    popup: 'rounded-2xl',
    confirmButton: 'rounded-lg px-6 py-3',
    cancelButton: 'rounded-lg px-6 py-3'
};

const app = Vue.createApp({
    data() {
        return {
            currentAdmin: { emp_id: '', name: '載入中...' },
            inRoster: false,
            isAdmin: false,
            currentTab: 'employees',
            ranking2000: [],
            ranking3000: [],
            statistics: {
                total_employees: 0,
                voted_count: 0,
                pending_count: 0,
                vote_rate: 0,
                total_votes: 0
            },
            votes: [],
            employees: [],
            voteSearch: '',
            employeeSearch: '',
            isRefreshing: false,          // 頂部「刷新」按鈕載入中
            lastUpdated: '',              // 最後更新時間
            employeeGroupFilter: 'all',   // 員工列表：組別篩選
            employeeStatusFilter: 'all',  // 員工列表：投票狀態篩選
            quotas: {
                quota_2000_to_3000: 4,
                quota_3000_to_2000: 2,
                quota_3000_to_3000: 2
            },
            monthlyChart: null,
            monthsToShow: 6,
            monthlyRefreshLock: false,
            isLoadingMonthlyStats: false,
            monthlyStatsLabel: {
                avg_2000: 0,
                avg_3000: 0,
                total_avg: 0,
                votes_2000: 0,
                votes_3000: 0,
                total_votes: 0
            },
            allTabs: [
                {
                    id: 'votes',
                    name: '投票記錄',
                    icon: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"/></svg>',
                    adminOnly: true
                },
                {
                    id: 'employees',
                    name: '員工列表',
                    icon: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"/></svg>',
                    adminOnly: false
                },
                {
                    id: 'monthly',
                    name: '每月趨勢',
                    icon: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z"/></svg>',
                    adminOnly: false
                },
                {
                    id: 'statistics',
                    name: '統計分析',
                    icon: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>',
                    adminOnly: false
                },
                {
                    id: 'system',
                    name: '系統管理',
                    icon: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>',
                    adminOnly: true
                }
            ]
        };
    },
    computed: {
        visibleTabs() {
            return this.allTabs.filter(tab => !tab.adminOnly || this.isAdmin);
        },
        filteredVotes() {
            if (!this.voteSearch) return this.votes;
            const query = this.voteSearch.toLowerCase();
            return this.votes.filter(vote =>
                vote.voter_name?.toLowerCase().includes(query) ||
                vote.voter_emp_id?.toLowerCase().includes(query) ||
                vote.voted_for_name?.toLowerCase().includes(query) ||
                vote.voted_for_emp_id?.toLowerCase().includes(query)
            );
        },
        filteredEmployees() {
            const search = this.employeeSearch.toLowerCase();
            return this.employees.filter(emp =>
                (emp.name.toLowerCase().includes(search) || emp.emp_id.toLowerCase().includes(search)) &&
                (this.employeeGroupFilter === 'all' || emp.group === this.employeeGroupFilter) &&
                (this.employeeStatusFilter === 'all' ||
                    (this.employeeStatusFilter === 'voted' && emp.has_voted) ||
                    (this.employeeStatusFilter === 'pending' && !emp.has_voted))
            );
        }
    },
    watch: {
        monthsToShow() {
            if (this.currentTab === 'monthly') this.refreshMonthlyStats();
        },
        currentTab(newTab) {
            if (newTab === 'monthly') this.$nextTick(() => this.loadMonthlyStats());
        }
    },
    async mounted() {
        const { token } = getSession();
        if (!token) {
            window.location.href = 'login.html';
            return;
        }

        // 身分與權限一律以後端回傳為準
        const { ok, data } = await apiFetch('/api/me');
        if (!ok) {
            window.location.href = 'login.html';
            return;
        }
        this.currentAdmin = { emp_id: data.emp_id, name: data.name };
        this.inRoster = data.in_roster;
        this.isAdmin = data.is_admin;
        this.currentTab = this.isAdmin ? 'votes' : 'employees';

        await this.refreshData();
        await this.reloadQuotas();
    },
    beforeUnmount() {
        if (this.monthlyChart) {
            this.monthlyChart.destroy();
            this.monthlyChart = null;
        }
    },
    methods: {
        groupBadge(group) {
            return group === '2000' ? 'badge badge-2000' : 'badge badge-3000';
        },
        usageText(emp) {
            return Object.keys(emp.quota).map(g => `${g}組 ${emp.used[g] || 0}/${emp.quota[g]}`).join('、');
        },

        async logout() {
            const result = await Swal.fire({
                title: '確定要登出嗎?',
                icon: 'question',
                showCancelButton: true,
                confirmButtonColor: '#4F46E5',
                cancelButtonColor: '#6B7280',
                confirmButtonText: '確定登出',
                cancelButtonText: '取消',
                customClass: SWAL_CLASS
            });
            if (result.isConfirmed) window.location.href = 'login.html';
        },
        backToVoting() {
            window.location.href = 'voting_system_vue.html';
        },

        async refreshData() {
            await Promise.all([
                this.loadStatistics(),
                this.loadEmployees(),
                this.isAdmin ? this.loadVotes() : Promise.resolve()
            ]);
            this.lastUpdated = new Date().toLocaleTimeString('zh-TW', { hour12: false });
        },
        // 頂部「刷新」按鈕：重新載入全部資料，並顯示載入中 / 完成提示
        async manualRefresh() {
            if (this.isRefreshing) return;
            this.isRefreshing = true;
            try {
                await Promise.all([
                    this.refreshData(),
                    this.isAdmin ? this.reloadQuotas() : Promise.resolve(),
                    this.currentTab === 'monthly' ? this.loadMonthlyStats() : Promise.resolve()
                ]);
                Swal.fire({
                    toast: true,
                    position: 'top-end',
                    icon: 'success',
                    title: `資料已更新 · ${this.lastUpdated}`,
                    showConfirmButton: false,
                    timer: 1600,
                    timerProgressBar: true
                });
            } catch (error) {
                console.error('刷新失敗', error);
                Swal.fire({ toast: true, position: 'top-end', icon: 'error', title: '刷新失敗，請稍後再試', showConfirmButton: false, timer: 2000 });
            } finally {
                this.isRefreshing = false;
            }
        },
        async loadStatistics() {
            try {
                const { data } = await apiFetch('/api/vote_stats');
                this.ranking2000 = data.ranking_2000 || [];
                this.ranking3000 = data.ranking_3000 || [];
                this.statistics.total_votes = data.total_votes || 0;
            } catch (error) {
                console.error('載入統計失敗', error);
                this.ranking2000 = [];
                this.ranking3000 = [];
            }
        },
        async loadEmployees() {
            try {
                const { data } = await apiFetch('/api/employees');
                this.employees = Array.isArray(data) ? data : [];

                const total = this.employees.length;
                const voted = this.employees.filter(emp => emp.has_voted).length;
                this.statistics.total_employees = total;
                this.statistics.voted_count = voted;
                this.statistics.pending_count = total - voted;
                this.statistics.vote_rate = total > 0 ? ((voted / total) * 100).toFixed(1) : 0;
            } catch (error) {
                console.error('載入員工列表失敗', error);
                this.employees = [];
            }
        },
        async loadVotes() {
            try {
                const { data } = await apiFetch('/api/votes');
                this.votes = Array.isArray(data.votes) ? data.votes : [];
            } catch (error) {
                console.error('載入投票記錄失敗', error);
                this.votes = [];
            }
        },

        async loadMonthlyStats() {
            if (this.isLoadingMonthlyStats) return;
            this.isLoadingMonthlyStats = true;
            try {
                const { ok, data } = await apiFetch(`/api/monthly_participation?months=${this.monthsToShow}`);
                if (!ok) throw new Error(data.error || '載入失敗');

                const sum = arr => arr.reduce((a, b) => a + b, 0);
                const avg = arr => (arr.length ? (sum(arr) / arr.length).toFixed(1) : 0);
                this.monthlyStatsLabel = {
                    avg_2000: avg(data.rates_2000),
                    avg_3000: avg(data.rates_3000),
                    total_avg: avg(data.total_rates),
                    votes_2000: sum(data.votes_2000),
                    votes_3000: sum(data.votes_3000),
                    total_votes: sum(data.total_votes)
                };

                await this.$nextTick();
                this.renderMonthlyChart(data);
            } catch (error) {
                console.error('載入每月統計失敗:', error);
                Swal.fire({
                    title: '載入失敗',
                    text: '無法載入每月統計數據，請稍後再試',
                    icon: 'error',
                    confirmButtonColor: '#4F46E5',
                    confirmButtonText: '確定',
                    customClass: SWAL_CLASS
                });
            } finally {
                this.isLoadingMonthlyStats = false;
            }
        },
        async refreshMonthlyStats() {
            if (this.monthlyRefreshLock) return;
            this.monthlyRefreshLock = true;
            try {
                await this.loadMonthlyStats();
            } finally {
                this.monthlyRefreshLock = false;
            }
        },
        renderMonthlyChart(data) {
            const canvas = document.getElementById('monthlyChart');
            if (!canvas) return;
            if (this.monthlyChart) {
                this.monthlyChart.destroy();
                this.monthlyChart = null;
            }
            Chart.defaults.font.family = 'Inter, "Segoe UI", "Microsoft JhengHei", sans-serif';
            Chart.defaults.color = '#8f8f8f';
            Chart.defaults.borderColor = '#ededed';
            // markRaw：避免 Vue 把 Chart 實例變成響應式物件，造成圖表座標錯亂
            this.monthlyChart = Vue.markRaw(new Chart(canvas.getContext('2d'), {
                type: 'line',
                data: {
                    labels: data.labels,
                    datasets: [
                        {
                            label: '2000組 參與率',
                            data: data.rates_2000,
                            borderColor: '#171717',
                            backgroundColor: 'rgba(23, 23, 23, 0.04)',
                            tension: 0.4,
                            fill: true
                        },
                        {
                            label: '3000組 參與率',
                            data: data.rates_3000,
                            borderColor: '#a3a3a3',
                            backgroundColor: 'rgba(163, 163, 163, 0.06)',
                            borderDash: [5, 4],
                            tension: 0.4,
                            fill: true
                        },
                        {
                            label: '總體參與率',
                            data: data.total_rates,
                            borderColor: '#3ecf8e',
                            backgroundColor: 'rgba(62, 207, 142, 0.10)',
                            tension: 0.4,
                            fill: true
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: { position: 'top', labels: { usePointStyle: true, padding: 15, font: { size: 12 } } },
                        title: {
                            display: true,
                            text: `近 ${this.monthsToShow} 月投票參與趨勢`,
                            color: '#171717',
                            font: { size: 14, weight: '600' },
                            padding: { top: 10, bottom: 20 }
                        },
                        tooltip: {
                            callbacks: {
                                label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%`
                            }
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            max: 100,
                            ticks: { callback: value => value + '%' },
                            title: { display: true, text: '參與率 (%)', font: { size: 12 } }
                        },
                        x: { title: { display: true, text: '月份', font: { size: 12 } } }
                    }
                }
            }));
        },

        async saveQuotas() {
            if (!this.isAdmin) return;
            const q = this.quotas;
            const values = [q.quota_2000_to_3000, q.quota_3000_to_2000, q.quota_3000_to_3000];
            if (values.some(v => !Number.isInteger(v) || v < 0 || v > 20) || q.quota_2000_to_3000 < 1) {
                Swal.fire({
                    title: '配額錯誤',
                    text: '配額必須是 0-20 的整數，且 2000組→3000組 至少 1 票',
                    icon: 'error',
                    confirmButtonColor: '#4F46E5',
                    confirmButtonText: '確定',
                    customClass: SWAL_CLASS
                });
                return;
            }

            const { ok, data } = await apiFetch('/api/quotas', { method: 'POST', body: JSON.stringify(q) });
            await Swal.fire({
                title: ok ? '儲存成功' : '儲存失敗',
                text: ok ? data.message : data.error,
                icon: ok ? 'success' : 'error',
                confirmButtonColor: '#4F46E5',
                confirmButtonText: '確定',
                customClass: SWAL_CLASS
            });
            if (ok) await this.refreshData();
        },
        async reloadQuotas() {
            try {
                const { ok, data } = await apiFetch('/api/quotas');
                if (ok) this.quotas = data;
            } catch (error) {
                console.error('載入配額失敗', error);
            }
        },

        async resetSystem() {
            const result = await Swal.fire({
                title: '確認重置本月投票',
                html: '⚠️ 將清除本月所有投票記錄，所有員工可重新投票。<br>原檔會自動備份為 .bak。確定要繼續嗎?',
                icon: 'warning',
                showCancelButton: true,
                confirmButtonColor: '#DC2626',
                cancelButtonColor: '#6B7280',
                confirmButtonText: '確定重置',
                cancelButtonText: '取消',
                customClass: SWAL_CLASS
            });
            if (!result.isConfirmed) return;

            const { ok, data } = await apiFetch('/api/reset', { method: 'POST', body: JSON.stringify({}) });
            await Swal.fire({
                title: ok ? '重置成功' : '重置失敗',
                text: ok ? data.message : data.error,
                icon: ok ? 'success' : 'error',
                confirmButtonColor: '#4F46E5',
                confirmButtonText: '確定',
                customClass: SWAL_CLASS
            });
            if (ok) await this.refreshData();
        },
        async reloadEmployees() {
            const result = await Swal.fire({
                title: '確定要重新載入員工資料嗎?',
                text: '將以 emoinfo.json 重建本月名單，已投票記錄會保留',
                icon: 'question',
                showCancelButton: true,
                confirmButtonColor: '#4F46E5',
                cancelButtonColor: '#6B7280',
                confirmButtonText: '確定載入',
                cancelButtonText: '取消',
                customClass: SWAL_CLASS
            });
            if (!result.isConfirmed) return;

            const { ok, data } = await apiFetch('/api/load_employees', {
                method: 'POST',
                body: JSON.stringify({ force: true })
            });
            await Swal.fire({
                title: ok ? '載入成功!' : '載入失敗',
                text: ok ? data.message : data.error,
                icon: ok ? 'success' : 'error',
                confirmButtonColor: '#4F46E5',
                confirmButtonText: '確定',
                customClass: SWAL_CLASS
            });
            if (ok) await this.refreshData();
        },

        formatDate(timestamp) {
            return new Date(timestamp.replace(' ', 'T')).toLocaleString('zh-TW');
        },
        exportVotes() {
            if (!this.isAdmin) return;
            const esc = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
            let csv = '﻿投票時間,投票者工號,投票者姓名,投票者組別,被投票者工號,被投票者姓名,被投票者組別\n';
            this.votes.forEach(v => {
                csv += [v.timestamp, v.voter_emp_id, v.voter_name, v.voter_group,
                        v.voted_for_emp_id, v.voted_for_name, v.voted_for_group].map(esc).join(',') + '\n';
            });
            const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = `投票記錄_${new Date().toISOString().split('T')[0]}.csv`;
            link.click();
            URL.revokeObjectURL(link.href);
        }
    }
});
app.mount('#app');