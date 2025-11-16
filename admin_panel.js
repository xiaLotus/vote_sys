const app = Vue.createApp({
    data() {
        return {
            loginEmpId: '',
            loginError: '',
            // 改成：
            currentAdmin: {
                emp_id: '',
                name: '載入中...'
            },
            rrRanking: [],
            shiftRanking: [],
            isAdmin: false,
            currentTab: 'employees',
            statistics: {
                total_employees: 0,
                voted_count: 0,
                pending_count: 0,
                vote_rate: 0,
                recent_votes: 0
            },
            votes: [],  // 確保初始化為空數組
            employees: [],
            voteSearch: '',
            searchQuery: '',  // 添加這行
            employeeSearch: '',
            quotas: {
                rr: 1,
                shift: 1
            },
            weeklyChart: null,
            monthsToShow: 6, // 預設顯示 6 月
            monthlyRefreshLock: false, // 🔒 防連續刷新鎖
            weeklyStatsLabel: {
                rr_avg: 0,
                shift_avg: 0,
                total_avg: 0,
                rr_votes: 0,
                shift_votes: 0,
                total_votes: 0
            },
            isLoadingWeeklyStats: false, // 加載狀態
            isRenderingChart: false, // 圖表渲染狀態
            loadWeeklyStatsTimeout: null, // 防抖計時器
            renderingLock: false, // 渲染鎖
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
                    id: 'weekly', 
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
        }
    },
    computed: {
        visibleTabs() {
            return this.allTabs.filter(tab => !tab.adminOnly || this.isAdmin);
        },
        filteredVotes() {
            if (!Array.isArray(this.votes)) {
                return [];
            }
            
            if (!this.searchQuery) {
                return this.votes;
            }
            
            const query = this.searchQuery.toLowerCase();
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
                emp.name.toLowerCase().includes(search) ||
                emp.emp_id.toLowerCase().includes(search)
            );
        },
    },
    watch: {
        // ✅ 修正：監聽 monthsToShow，移除 weeksToShow
        monthsToShow: {
            handler() {
                if (this.currentTab === 'weekly') {
                    this.refreshMonthlyStats(); // 呼叫帶 SweetAlert 的版本
                }
            },
            immediate: false
        },
        
        currentTab(newTab) {
            if (newTab === 'weekly') {
                this.$nextTick(() => {
                    this.loadMonthlyStats(); // 初次進入 tab 時載入
                });
            }
        }
    },
    async mounted() {
        console.log('=== admin_panel 頁面載入 ===');
        
        // 檢查 URL 是否有 emp_id 參數
        const urlParams = new URLSearchParams(window.location.search);
        const empId = urlParams.get('emp_id');
        
        console.log('從 URL 獲取的 emp_id:', empId);
        
        if (!empId) {
            // 如果沒有工號參數,跳轉回投票系統
            Swal.fire({
                title: '錯誤',
                text: '請從投票系統進入',
                icon: 'error',
                confirmButtonColor: '#4F46E5',
                confirmButtonText: '返回投票系統',
                customClass: {
                    popup: 'rounded-2xl',
                    confirmButton: 'rounded-lg px-6 py-3'
                }
            }).then(() => {
                window.location.href = 'voting_system_vue.html';
            });
            return;
        }
        
        // 直接設置登入狀態
        this.loginEmpId = empId;
        this.isAdmin = ['K18251', 'G9745'].includes(empId);
        this.currentAdmin = {
            emp_id: empId,
            name: empId
        };
        this.isLoggedIn = true;
        this.currentTab = this.isAdmin ? 'votes' : 'employees';
        
        console.log('已設置登入狀態，isLoggedIn:', this.isLoggedIn);
        
        // 嘗試載入數據（可選）
        try {
            await this.refreshData();
            await this.reloadQuotas();
        } catch (error) {
            console.log('離線模式，無法載入數據');
        }
    },

    beforeUnmount() {
        // 清除防抖計時器
        if (this.loadWeeklyStatsTimeout) {
            clearTimeout(this.loadWeeklyStatsTimeout);
            this.loadWeeklyStatsTimeout = null;
        }

        // 清除渲染鎖
        this.renderingLock = false;
        this.isRenderingChart = false;
        this.isLoadingWeeklyStats = false;

        // 組件銷毀前清理圖表
        if (this.weeklyChart) {
            try {
                this.weeklyChart.destroy();
                this.weeklyChart = null;
            } catch (error) {
                console.error('清理圖表時出錯:', error);
            }
        }
    },
    methods: {

        async logout() {
            const result = await Swal.fire({
                title: '確定要登出嗎?',
                icon: 'question',
                showCancelButton: true,
                confirmButtonColor: '#4F46E5',
                cancelButtonColor: '#6B7280',
                confirmButtonText: '確定登出',
                cancelButtonText: '取消',
                customClass: {
                    popup: 'rounded-2xl',
                    confirmButton: 'rounded-lg px-6 py-3',
                    cancelButton: 'rounded-lg px-6 py-3'
                }
            });

            if (result.isConfirmed) {
                // 跳轉回投票系統
                window.location.href = 'voting_system_vue.html';
            }
        },
        backToVoting() {
            // 返回投票系統,並帶上工號參數
            window.location.href = `voting_system_vue.html?emp_id=${this.currentAdmin.emp_id}`;
        },
        async refreshData() {
            await Promise.all([
                this.loadStatistics(),
                this.loadEmployees(),
                this.isAdmin ? this.loadVotes() : Promise.resolve()
            ]);
        },
        async loadStatistics() {
            try {
                const { year, month } = this.getCurrentYearMonth();
                const response = await fetch(`http://127.0.0.1:5000/api/vote_stats?year=${year}&month=${month}`);
                const data = await response.json();
                
                console.log('統計數據:', data);
                
                // 確保數據存在
                this.rrRanking = Array.isArray(data.rr_ranking) ? data.rr_ranking : [];
                this.shiftRanking = Array.isArray(data.shift_ranking) ? data.shift_ranking : [];
                
                console.log('RR排行榜:', this.rrRanking);
                console.log('輪班排行榜:', this.shiftRanking);
            } catch (error) {
                console.error('載入統計失敗', error);
                this.rrRanking = [];
                this.shiftRanking = [];
            }
        },
        getCurrentYearMonth() {
            const now = new Date();
            return {
                year: now.getFullYear(),
                month: now.getMonth() + 1  // 不用 padStart，因後端 API 接收數字
            };
        },
        async loadEmployees() {
            try {
                const { year, month } = this.getCurrentYearMonth();
                const response = await fetch(`http://127.0.0.1:5000/api/employees?year=${year}&month=${month}`);
                const data = await response.json();
                
                console.log('員工數據:', data);
                
                // 確保數據存在，並為每個員工添加 can_vote 字段
                this.employees = Array.isArray(data) ? data.map(emp => ({
                    ...emp,
                    can_vote: emp.votes_used < emp.max_votes
                })) : [];

                // 計算統計數據
                const totalEmployees = this.employees.length;
                const votedCount = this.employees.filter(emp => emp.has_voted === true).length;
                const notVotedCount = totalEmployees - votedCount;
                const votedRate = totalEmployees > 0 
                    ? ((votedCount / totalEmployees) * 100).toFixed(1) 
                    : 0;
                
                // 設置到 statistics 對象中供 HTML 使用
                this.statistics.total_employees = totalEmployees;
                this.statistics.voted_count = votedCount;
                this.statistics.pending_count = notVotedCount;
                this.statistics.vote_rate = votedRate;
                this.statistics.recent_votes = votedCount;
                
                console.log(`員工統計 - 總數:${totalEmployees}, 已投:${votedCount}, 未投:${notVotedCount}, 投票率:${votedRate}%, 本月投票:${votedCount}`);
            } catch (error) {
                console.error('載入員工列表失敗', error);
                this.employees = [];
                this.statistics.total_employees = 0;
                this.statistics.voted_count = 0;
                this.statistics.pending_count = 0;
                this.statistics.vote_rate = 0;
                this.statistics.recent_votes = 0;
            }
        },
        async loadVotes() {
            try {
                const { year, month } = this.getCurrentYearMonth();
                const response = await fetch(`http://127.0.0.1:5000/api/votes?year=${year}&month=${month}`);
                const data = await response.json();
                
                // 確保 votes 是數組
                this.votes = Array.isArray(data.votes) ? data.votes : [];
                
                console.log('成功載入投票記錄，數量:', this.votes.length);
            } catch (error) {
                console.error('載入投票記錄失敗', error);
                this.votes = [];
            }
        },
        async loadMonthlyStats() {
            if (this.isLoadingWeeklyStats) {
                console.log('正在載入中，跳過此次請求');
                return;
            }

            if (this.loadWeeklyStatsTimeout) {
                clearTimeout(this.loadWeeklyStatsTimeout);
                this.loadWeeklyStatsTimeout = null;
            }

            this.isLoadingWeeklyStats = true;
            
            try {
                const monthsToShow = this.monthsToShow || 6;
                const response = await fetch(`http://127.0.0.1:5000/api/monthly_participation?months=${monthsToShow}`);
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                const data = await response.json();
                
                const validatedData = this.validateAndFillMonthlyData(data);
                this.calculateMonthlyAverages(validatedData);
                
                await this.$nextTick();
                await this.renderMonthlyChart(validatedData);
                
            } catch (error) {
                console.error('載入每月統計失敗:', error);
                
                Swal.fire({
                    title: '載入失敗',
                    text: '無法載入每月統計數據，請稍後再試',
                    icon: 'error',
                    confirmButtonColor: '#4F46E5',
                    confirmButtonText: '確定',
                    customClass: {
                        popup: 'rounded-2xl',
                        confirmButton: 'rounded-lg px-6 py-3'
                    }
                });
                
                await this.$nextTick();
                await this.renderEmptyChart();
            } finally {
                this.isLoadingWeeklyStats = false;
            }
        },

        async refreshMonthlyStats() {
            // 🔒 防連續點擊
            if (this.monthlyRefreshLock) {
                Swal.fire({
                    icon: 'info',
                    title: '請稍候',
                    text: '資料載入中…請等待上一次操作完成',
                    timer: 1500,
                    showConfirmButton: false
                });
                return;
            }

            this.monthlyRefreshLock = true;

            // 🟡 Step 1: Loading 提示
            const loadingAlert = Swal.fire({
                title: '載入中…',
                html: `正在取得 <strong>${this.monthsToShow} 個月</strong> 的參與率趨勢`,
                allowOutsideClick: false,
                allowEscapeKey: false,
                showConfirmButton: false,
                didOpen: () => Swal.showLoading()
            });

            try {
                // 🟢 Step 2: 執行真正刷新
                await this.loadMonthlyStats(); // ← 注意：不再包裝，直接 call

                // 🟢 Step 3: 成功 + 顯示「✅ 完成」提示（關鍵！）
                await Swal.fire({
                    icon: 'success',
                    title: '更新完成！',
                    html: `已成功載入 <strong>${this.monthsToShow} 個月</strong> 數據`,
                    timer: 1200,
                    showConfirmButton: false,
                    timerProgressBar: true,
                    didOpen: () => Swal.showLoading(),
                    willClose: () => Swal.hideLoading()
                });

            } catch (error) {
                // 🔴 Step 4: 失敗提示
                console.error('每月趨勢刷新失敗:', error);
                await Swal.fire({
                    icon: 'error',
                    title: '更新失敗',
                    text: '請檢查網路或伺服器狀態',
                    confirmButtonColor: '#ef4444'
                });
            } finally {
                // 🔓 解鎖
                this.monthlyRefreshLock = false;
                // 確保 loading 關掉（防異常）
                if (Swal.isVisible()) Swal.close();
            }
        },
        validateAndFillMonthlyData(data) {
            const labels = data.labels || [];
            const rr_rates = data.rr_rates || [];
            const shift_rates = data.shift_rates || [];
            const total_rates = data.total_rates || [];
            const rr_votes = data.rr_votes || [];
            const shift_votes = data.shift_votes || [];
            const total_votes = data.total_votes || [];
            
            const length = Math.max(
                labels.length,
                rr_rates.length,
                shift_rates.length,
                total_rates.length,
                rr_votes.length,
                shift_votes.length,
                total_votes.length
            );
            
            for (let i = 0; i < length; i++) {
                if (!labels[i]) labels[i] = `月 ${i + 1}`;
                if (rr_rates[i] === undefined || rr_rates[i] === null) rr_rates[i] = 0;
                if (shift_rates[i] === undefined || shift_rates[i] === null) shift_rates[i] = 0;
                if (total_rates[i] === undefined || total_rates[i] === null) total_rates[i] = 0;
                if (rr_votes[i] === undefined || rr_votes[i] === null) rr_votes[i] = 0;
                if (shift_votes[i] === undefined || shift_votes[i] === null) shift_votes[i] = 0;
                if (total_votes[i] === undefined || total_votes[i] === null) total_votes[i] = 0;
            }
            
            return {
                labels,
                rr_rates,
                shift_rates,
                total_rates,
                rr_votes,
                shift_votes,
                total_votes
            };
        },

        calculateMonthlyAverages(data) {
            const sum = arr => arr.reduce((a, b) => a + b, 0);
            const avg = arr => arr.length > 0 ? (sum(arr) / arr.length).toFixed(1) : 0;
            
            this.weeklyStatsLabel = {
                rr_avg: avg(data.rr_rates),
                shift_avg: avg(data.shift_rates),
                total_avg: avg(data.total_rates),
                rr_votes: sum(data.rr_votes),
                shift_votes: sum(data.shift_votes),
                total_votes: sum(data.total_votes)
            };
        },

        async renderMonthlyChart(data) {
            if (this.renderingLock) {
                console.log('圖表正在渲染中，跳過');
                return;
            }
            
            this.renderingLock = true;
            this.isRenderingChart = true;
            
            try {
                await this.$nextTick();
                
                const canvas = document.getElementById('weeklyChart');
                if (!canvas) {
                    console.error('找不到圖表容器');
                    return;
                }
                
                if (this.weeklyChart) {
                    this.weeklyChart.destroy();
                    this.weeklyChart = null;
                }
                
                const ctx = canvas.getContext('2d');
                
                this.weeklyChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: data.labels,
                        datasets: [
                            {
                                label: '2000 參與率',
                                data: data.rr_rates,        // 2000 班別資料
                                borderColor: 'rgb(239, 68, 68)',
                                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                                tension: 0.4,
                                fill: true
                            },
                            {
                                label: '3000 參與率',
                                data: data.shift_rates,     // 3000 班別資料
                                borderColor: 'rgb(59, 130, 246)',
                                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                                tension: 0.4,
                                fill: true
                            },
                            {
                                label: '總體參與率',
                                data: data.total_rates,
                                borderColor: 'rgb(16, 185, 129)',
                                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                                tension: 0.4,
                                fill: true
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: {
                            mode: 'index',
                            intersect: false,
                        },
                        plugins: {
                            legend: {
                                position: 'top',
                                labels: {
                                    usePointStyle: true,
                                    padding: 15,
                                    font: {
                                        size: 12
                                    }
                                }
                            },
                            title: {
                                display: true,
                                text: `近 ${this.monthsToShow} 月投票參與趨勢`,
                                font: {
                                    size: 16,
                                    weight: 'bold'
                                },
                                padding: {
                                    top: 10,
                                    bottom: 20
                                }
                            },
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        return context.dataset.label + ': ' + context.parsed.y.toFixed(1) + '%';
                                    }
                                }
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true,
                                max: 100,
                                ticks: {
                                    callback: function(value) {
                                        return value + '%';
                                    }
                                },
                                title: {
                                    display: true,
                                    text: '參與率 (%)',
                                    font: {
                                        size: 12
                                    }
                                }
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: '月份',
                                    font: {
                                        size: 12
                                    }
                                }
                            }
                        }
                    }
                });
                
                console.log('圖表渲染成功');
            } catch (error) {
                console.error('渲染圖表失敗:', error);
            } finally {
                this.renderingLock = false;
                this.isRenderingChart = false;
            }
        },

        async renderEmptyChart() {
            // 使用渲染鎖
            if (this.renderingLock) {
                console.log('圖表渲染已鎖定，等待完成...');
                let waitTime = 0;
                while (this.renderingLock && waitTime < 2000) {
                    await new Promise(resolve => setTimeout(resolve, 100));
                    waitTime += 100;
                }
                if (this.renderingLock) {
                    console.warn('渲染鎖超時，強制解鎖');
                    this.renderingLock = false;
                    this.isRenderingChart = false;
                }
            }

            this.renderingLock = true;
            this.isRenderingChart = true;

            try {
                const ctx = document.getElementById('weeklyChart');
                if (!ctx) {
                    console.warn('找不到圖表 canvas 元素（空圖表）');
                    return;
                }

                // 銷毀舊圖表
                if (this.weeklyChart) {
                    try {
                        console.log('銷毀舊圖表（空圖表模式）...');
                        this.weeklyChart.destroy();
                        this.weeklyChart = null;
                    } catch (error) {
                        console.error('銷毀舊圖表時出錯（空圖表）:', error);
                        this.weeklyChart = null;
                    }
                }

                // 等待 DOM 穩定 - 2 幀 + 50ms
                await new Promise(resolve => requestAnimationFrame(resolve));
                await new Promise(resolve => requestAnimationFrame(resolve));
                await new Promise(resolve => setTimeout(resolve, 50));

                // 再次檢查 canvas
                const canvas = document.getElementById('weeklyChart');
                if (!canvas) {
                    console.warn('Canvas 元素已不存在（空圖表）');
                    return;
                }

                // 檢查 canvas context
                try {
                    const testCtx = canvas.getContext('2d');
                    if (!testCtx) {
                        console.warn('無法獲取 canvas context（空圖表）');
                        return;
                    }
                } catch (error) {
                    console.error('測試 canvas context 時出錯（空圖表）:', error);
                    return;
                }

                // 創建空圖表
                console.log('創建空圖表...');
                this.weeklyChart = new Chart(canvas, {
                    type: 'line',
                    data: {
                        labels: ['暫無數據'],
                        datasets: [{
                            label: '暫無數據',
                            data: [0],
                            borderColor: 'rgb(209, 213, 219)',
                            backgroundColor: 'rgba(209, 213, 219, 0.1)',
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                display: false
                            },
                            title: {
                                display: true,
                                text: '暫無投票數據',
                                font: {
                                    size: 16,
                                    weight: 'bold'
                                }
                            }
                        }
                    }
                });
                
                console.log('空圖表創建成功');
            } catch (error) {
                console.error('創建空圖表時出錯:', error);
                console.error('錯誤堆疊:', error.stack);
            } finally {
                this.isRenderingChart = false;
                this.renderingLock = false; // 解鎖
            }
        },
        async saveQuotas() {
            if (!this.isAdmin) return;

            // 驗證配額範圍
            if (this.quotas.rr < 1 || this.quotas.rr > 10 || 
                this.quotas.shift < 1 || this.quotas.shift > 10) {
                Swal.fire({
                    title: '配額錯誤',
                    text: '配額必須在 1-10 之間',
                    icon: 'error',
                    confirmButtonColor: '#4F46E5',
                    confirmButtonText: '確定',
                    customClass: {
                        popup: 'rounded-2xl',
                        confirmButton: 'rounded-lg px-6 py-3'
                    }
                });
                return;
            }

            try {
                const response = await fetch('http://127.0.0.1:5000/api/quotas', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        quota_2000: this.quotas.rr,
                        quota_3000: this.quotas.shift
                    })
                });

                const data = await response.json();

                if (response.ok) {
                    await Swal.fire({
                        title: '儲存成功',
                        text: data.message,
                        icon: 'success',
                        confirmButtonColor: '#4F46E5',
                        confirmButtonText: '確定',
                        customClass: {
                            popup: 'rounded-2xl',
                            confirmButton: 'rounded-lg px-6 py-3'
                        }
                    });
                    await this.refreshData();
                } else {
                    Swal.fire({
                        title: '儲存失敗',
                        text: data.error,
                        icon: 'error',
                        confirmButtonColor: '#4F46E5',
                        confirmButtonText: '確定',
                        customClass: {
                            popup: 'rounded-2xl',
                            confirmButton: 'rounded-lg px-6 py-3'
                        }
                    });
                }
            } catch (error) {
                Swal.fire({
                    title: '系統錯誤',
                    text: error.message,
                    icon: 'error',
                    confirmButtonColor: '#4F46E5',
                    confirmButtonText: '確定',
                    customClass: {
                        popup: 'rounded-2xl',
                        confirmButton: 'rounded-lg px-6 py-3'
                    }
                });
            }
        },
        async reloadQuotas() {
            try {
                const response = await fetch('http://127.0.0.1:5000/api/quotas');
                const data = await response.json();
                this.quotas.rr = data.quota_2000;
                this.quotas.shift = data.quota_3000;
            } catch (error) {
                console.error('載入配額失敗', error);
            }
        },
        async resetSystem(resetType) {
            let title = '';
            let text = '';
            
            if (resetType === 'votes_only') {
                title = '確認重置投票記錄';
                text = '⚠️ 此操作只會清除投票記錄,保留每週配額限制。確定要繼續嗎?';
            } else {
                title = '確認完全重置系統';
                text = '⚠️ 警告:此操作將清除所有投票記錄和每週投票追蹤!所有員工將能立即再次投票。確定要繼續嗎?';
            }
            
            const result = await Swal.fire({
                title: title,
                html: text,
                icon: 'warning',
                showCancelButton: true,
                confirmButtonColor: '#DC2626',
                cancelButtonColor: '#6B7280',
                confirmButtonText: '確定重置',
                cancelButtonText: '取消',
                customClass: {
                    popup: 'rounded-2xl',
                    confirmButton: 'rounded-lg px-6 py-3',
                    cancelButton: 'rounded-lg px-6 py-3'
                }
            });

            if (!result.isConfirmed) {
                return;
            }

            try {
                const { year, month } = this.getCurrentYearMonth();
                const response = await fetch('http://127.0.0.1:5000/api/reset', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        admin_id: this.currentAdmin.empId,
                        year: year,
                        month: month
                    })
                });

                const data = await response.json();

                if (response.ok) {
                    await Swal.fire({
                        title: '重置成功',
                        text: data.message,
                        icon: 'success',
                        confirmButtonColor: '#4F46E5',
                        confirmButtonText: '確定',
                        customClass: {
                            popup: 'rounded-2xl',
                            confirmButton: 'rounded-lg px-6 py-3'
                        }
                    });
                    await this.refreshData();
                } else {
                    Swal.fire({
                        title: '重置失敗',
                        text: data.error,
                        icon: 'error',
                        confirmButtonColor: '#4F46E5',
                        confirmButtonText: '確定',
                        customClass: {
                            popup: 'rounded-2xl',
                            confirmButton: 'rounded-lg px-6 py-3'
                        }
                    });
                }
            } catch (error) {
                Swal.fire({
                    title: '系統錯誤',
                    text: error.message,
                    icon: 'error',
                    confirmButtonColor: '#4F46E5',
                    confirmButtonText: '確定',
                    customClass: {
                        popup: 'rounded-2xl',
                        confirmButton: 'rounded-lg px-6 py-3'
                    }
                });
            }
        },
        async reloadEmployees() {
            const result = await Swal.fire({
                title: '確定要重新載入員工資料嗎?',
                text: '這將從 emoinfo.json 重新載入員工列表',
                icon: 'question',
                showCancelButton: true,
                confirmButtonColor: '#4F46E5',
                cancelButtonColor: '#6B7280',
                confirmButtonText: '確定載入',
                cancelButtonText: '取消',
                customClass: {
                    popup: 'rounded-2xl',
                    confirmButton: 'rounded-lg px-6 py-3',
                    cancelButton: 'rounded-lg px-6 py-3'
                }
            });

            if (result.isConfirmed) {
                try {
                    const { year, month } = this.getCurrentYearMonth();
                    const response = await fetch('http://127.0.0.1:5000/api/load_employees', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            year: year,
                            month: month
                        })
                    });

                    const data = await response.json();

                    if (response.ok) {
                        await Swal.fire({
                            title: '載入成功!',
                            text: data.message,
                            icon: 'success',
                            timer: 2000,
                            showConfirmButton: false,
                            customClass: {
                                popup: 'rounded-2xl'
                            }
                        });

                        await this.refreshData();
                    } else {
                        Swal.fire({
                            title: '載入失敗',
                            text: data.error,
                            icon: 'error',
                            confirmButtonColor: '#4F46E5',
                            confirmButtonText: '確定',
                            customClass: {
                                popup: 'rounded-2xl',
                                confirmButton: 'rounded-lg px-6 py-3'
                            }
                        });
                    }
                } catch (error) {
                    Swal.fire({
                        title: '系統錯誤',
                        text: '載入失敗,請稍後再試',
                        icon: 'error',
                        confirmButtonColor: '#4F46E5',
                        confirmButtonText: '確定',
                        customClass: {
                            popup: 'rounded-2xl',
                            confirmButton: 'rounded-lg px-6 py-3'
                        }
                    });
                }
            }
        },
        formatDate(timestamp) {
            return new Date(timestamp).toLocaleString('zh-TW');
        },
        getVotedFor(emp_id) {
            if (!this.isAdmin) return '-';
            const vote = this.votes.find(v => v.voter_emp_id === emp_id);
            return vote ? `${vote.voted_for_name} (${vote.voted_for_emp_id})` : '-';
        },
        exportVotes() {
            if (!this.isAdmin) return;
            
            let csv = '\ufeff投票時間,投票者工號,投票者姓名,投票者班別,被投票者工號,被投票者姓名,被投票者班別\n';
            
            this.votes.forEach(vote => {
                csv += `${this.formatDate(vote.timestamp)},${vote.voter_emp_id},${vote.voter_name},${vote.voter_shift},${vote.voted_for_emp_id},${vote.voted_for_name},${vote.voted_for_shift}\n`;
            });
            
            const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = `投票記錄_${new Date().toISOString().split('T')[0]}.csv`;
            link.click();
        },
        //  getCurrentYearMonth() {
        //     const now = new Date();
        //     return { year: now.getFullYear(), month: now.getMonth() + 1 };
        // },
          // ✅ 新增：帶 SweetAlert 的載入流程
        async loadMonthlyStatsWithAlert(months = this.monthsToShow) {
            // 顯示 SweetAlert loading（非阻塞）
            const alert = Swal.fire({
            title: '載入中…',
            html: `正在取得 <strong>${months} 個月</strong> 的參與率趨勢`,
            allowOutsideClick: false,
            allowEscapeKey: false,
            showConfirmButton: false,
            didOpen: () => Swal.showLoading()
            });

            try {
            // 臨時覆寫 monthsToShow 以確保一致性（可選）
            this.monthsToShow = months;
            await this.loadMonthlyStats(); // 原有邏輯不變
            } catch (e) {
            console.error('載入失敗:', e);
            } finally {
            // 無論成功失敗，都關閉 SweetAlert
            if (Swal.isVisible()) Swal.close();
            }
        },
    }
})
app.mount('#app');