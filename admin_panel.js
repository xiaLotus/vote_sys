const { createApp } = Vue;

createApp({
    data() {
        return {
            isLoggedIn: false,
            loginEmpId: '',
            loginError: '',
            currentAdmin: null,
            isAdmin: false,
            currentTab: 'employees',
            statistics: {
                total_employees: 0,
                voted_count: 0,
                pending_count: 0,
                vote_rate: 0,
                recent_votes: 0
            },
            votes: [],
            employees: [],
            voteSearch: '',
            employeeSearch: '',
            quotas: {
                rr: 1,
                shift: 1
            },
            weeklyChart: null,
            weeksToShow: 8, // 預設顯示 8 週
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
                    name: '每週趨勢', 
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
            const search = this.voteSearch.toLowerCase();
            return this.votes.filter(vote => 
                vote.voter_name.toLowerCase().includes(search) ||
                vote.voter_emp_id.toLowerCase().includes(search) ||
                vote.voted_for_name.toLowerCase().includes(search) ||
                vote.voted_for_emp_id.toLowerCase().includes(search)
            );
        },
        filteredEmployees() {
            const search = this.employeeSearch.toLowerCase();
            return this.employees.filter(emp =>
                emp.name.toLowerCase().includes(search) ||
                emp.emp_id.toLowerCase().includes(search)
            );
        },
        rrRanking() {
            return this.statistics.vote_stats
                ?.filter(s => s.shift_type === 'RR')
                .sort((a, b) => b.vote_count - a.vote_count) || [];
        },
        shiftRanking() {
            return this.statistics.vote_stats
                ?.filter(s => s.shift_type === '輪班')
                .sort((a, b) => b.vote_count - a.vote_count)
                .slice(0, 10) || [];
        }
    },
    watch: {
        currentTab(newTab) {
            if (newTab === 'weekly') {
                this.$nextTick(() => {
                    this.loadWeeklyStats();
                });
            }
        },
        weeksToShow(newValue) {
            // 當週數選擇改變時，立即重新加載數據
            if (this.currentTab === 'weekly') {
                this.loadWeeklyStats();
            }
        }
    },
    async mounted() {
        // 檢查 URL 是否有 emp_id 參數
        const urlParams = new URLSearchParams(window.location.search);
        const empId = urlParams.get('emp_id');
        
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
        
        // 自動登入
        this.loginEmpId = empId;
        await this.login(true); // 傳遞 true 表示是自動登入
    },
    beforeUnmount() {
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
        async login(autoLogin = false) {
            const empId = this.loginEmpId.trim().toUpperCase();
            
            if (!empId) {
                this.loginError = '請輸入工號';
                return;
            }

            try {
                const empResponse = await fetch(`http://127.0.0.1:5000/api/employees`);
                const employees = await empResponse.json();
                const employee = employees.find(e => e.emp_id === empId);

                if (!employee) {
                    this.loginError = '工號不存在';
                    return;
                }

                this.isAdmin = empId === 'K18251';
                
                this.currentAdmin = {
                    emp_id: empId,
                    name: employee.name
                };

                this.isLoggedIn = true;
                this.loginError = '';
                
                this.currentTab = this.isAdmin ? 'votes' : 'employees';
                
                await this.refreshData();
                await this.reloadQuotas(); // 載入配額設定

                // 如果是自動登入,顯示歡迎訊息
                if (autoLogin) {
                    Swal.fire({
                        title: '歡迎回來!',
                        text: `${employee.name},您的投票已成功記錄`,
                        icon: 'success',
                        timer: 2000,
                        showConfirmButton: false,
                        customClass: {
                            popup: 'rounded-2xl'
                        }
                    });
                }
            } catch (error) {
                this.loginError = '系統錯誤,請稍後再試';
            }
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
                const response = await fetch('http://127.0.0.1:5000/api/statistics');
                this.statistics = await response.json();
            } catch (error) {
                console.error('載入統計失敗', error);
            }
        },
        async loadEmployees() {
            try {
                const response = await fetch('http://127.0.0.1:5000/api/employees');
                this.employees = await response.json();
            } catch (error) {
                console.error('載入員工列表失敗', error);
            }
        },
        async loadVotes() {
            if (!this.isAdmin) return;
            
            try {
                const response = await fetch('http://127.0.0.1:5000/api/votes');
                this.votes = await response.json();
            } catch (error) {
                console.error('載入投票記錄失敗', error);
            }
        },
        async loadWeeklyStats() {
            // 防止重複執行
            if (this.isLoadingWeeklyStats) {
                console.log('正在載入中，跳過此次請求');
                return;
            }

            // 設置加載狀態
            this.isLoadingWeeklyStats = true;
            
            try {
                const response = await fetch(`http://127.0.0.1:5000/api/weekly_stats?weeks=${this.weeksToShow}`);
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                const data = await response.json();
                
                // 數據驗證和補0
                const validatedData = this.validateAndFillWeeklyData(data);
                
                // 計算平均值
                this.calculateWeeklyAverages(validatedData);
                
                // 渲染圖表
                await this.$nextTick(); // 確保 DOM 已更新
                this.renderWeeklyChart(validatedData);
                
            } catch (error) {
                console.error('載入每週統計失敗:', error);
                
                // 顯示錯誤提示
                Swal.fire({
                    title: '載入失敗',
                    text: '無法載入每週統計數據，請稍後再試',
                    icon: 'error',
                    confirmButtonColor: '#4F46E5',
                    confirmButtonText: '確定',
                    customClass: {
                        popup: 'rounded-2xl',
                        confirmButton: 'rounded-lg px-6 py-3'
                    }
                });
                
                // 顯示空數據
                this.renderEmptyChart();
            } finally {
                // 取消加載狀態
                this.isLoadingWeeklyStats = false;
            }
        },
        async refreshWeeklyStats() {
            // 刷新按鈕專用函數
            console.log('手動刷新每週統計');
            await this.loadWeeklyStats();
        },
        validateAndFillWeeklyData(data) {
            // 確保所有必要的數據字段都存在，如果不存在則用空數組或補0
            const weeks = data.weeks || [];
            const weeksCount = weeks.length || this.weeksToShow;
            
            // 如果沒有週次標籤，生成默認的
            if (weeks.length === 0) {
                for (let i = 0; i < weeksCount; i++) {
                    weeks.push(`週 ${i + 1}`);
                }
            }
            
            // 確保數據數組長度一致，不足的補0
            const ensureArrayLength = (arr, length) => {
                if (!Array.isArray(arr)) return Array(length).fill(0);
                if (arr.length < length) {
                    return [...arr, ...Array(length - arr.length).fill(0)];
                }
                return arr.slice(0, length);
            };
            
            return {
                weeks: weeks,
                rr_rates: ensureArrayLength(data.rr_rates, weeksCount),
                shift_rates: ensureArrayLength(data.shift_rates, weeksCount),
                total_rates: ensureArrayLength(data.total_rates, weeksCount),
                rr_votes: ensureArrayLength(data.rr_votes, weeksCount),
                shift_votes: ensureArrayLength(data.shift_votes, weeksCount),
                total_votes: ensureArrayLength(data.total_votes, weeksCount)
            };
        },
        calculateWeeklyAverages(data) {
            // 計算各類別的平均參與率
            if (data.rr_rates && data.rr_rates.length > 0) {
                const rrSum = data.rr_rates.reduce((a, b) => a + b, 0);
                this.weeklyStatsLabel.rr_avg = Math.round(rrSum / data.rr_rates.length * 10) / 10; // 保留一位小數
            } else {
                this.weeklyStatsLabel.rr_avg = 0;
            }

            if (data.shift_rates && data.shift_rates.length > 0) {
                const shiftSum = data.shift_rates.reduce((a, b) => a + b, 0);
                this.weeklyStatsLabel.shift_avg = Math.round(shiftSum / data.shift_rates.length * 10) / 10;
            } else {
                this.weeklyStatsLabel.shift_avg = 0;
            }

            if (data.total_rates && data.total_rates.length > 0) {
                const totalSum = data.total_rates.reduce((a, b) => a + b, 0);
                this.weeklyStatsLabel.total_avg = Math.round(totalSum / data.total_rates.length * 10) / 10;
            } else {
                this.weeklyStatsLabel.total_avg = 0;
            }

            // 計算平均票數
            if (data.rr_votes && data.rr_votes.length > 0) {
                const rrVotesSum = data.rr_votes.reduce((a, b) => a + b, 0);
                this.weeklyStatsLabel.rr_votes = Math.round(rrVotesSum / data.rr_votes.length);
            } else {
                this.weeklyStatsLabel.rr_votes = 0;
            }

            if (data.shift_votes && data.shift_votes.length > 0) {
                const shiftVotesSum = data.shift_votes.reduce((a, b) => a + b, 0);
                this.weeklyStatsLabel.shift_votes = Math.round(shiftVotesSum / data.shift_votes.length);
            } else {
                this.weeklyStatsLabel.shift_votes = 0;
            }

            if (data.total_votes && data.total_votes.length > 0) {
                const totalVotesSum = data.total_votes.reduce((a, b) => a + b, 0);
                this.weeklyStatsLabel.total_votes = Math.round(totalVotesSum / data.total_votes.length);
            } else {
                this.weeklyStatsLabel.total_votes = 0;
            }
        },
        async renderWeeklyChart(data) {
            // 如果正在渲染，跳過
            if (this.isRenderingChart) {
                console.log('圖表正在渲染中，跳過此次請求');
                return;
            }

            this.isRenderingChart = true;

            try {
                const ctx = document.getElementById('weeklyChart');
                if (!ctx) {
                    console.warn('找不到圖表 canvas 元素');
                    return;
                }

                // 確保數據有效
                if (!data || !data.weeks || data.weeks.length === 0) {
                    console.warn('沒有可顯示的數據');
                    await this.renderEmptyChart();
                    return;
                }

                // 完全銷毀舊圖表
                if (this.weeklyChart) {
                    try {
                        this.weeklyChart.destroy();
                        this.weeklyChart = null;
                    } catch (error) {
                        console.error('銷毀舊圖表時出錯:', error);
                        this.weeklyChart = null;
                    }
                }

                // 等待下一幀，確保銷毀完成
                await new Promise(resolve => requestAnimationFrame(resolve));

                // 再次檢查 canvas 是否存在（可能在等待期間被移除）
                const canvas = document.getElementById('weeklyChart');
                if (!canvas) {
                    console.warn('Canvas 元素已不存在');
                    return;
                }

                // 創建新圖表
                this.weeklyChart = new Chart(canvas, {
                    type: 'line',
                    data: {
                        labels: data.weeks || [],
                        datasets: [
                            {
                                label: 'RR 參與率',
                                data: data.rr_rates || [],
                                borderColor: 'rgb(239, 68, 68)',
                                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                                tension: 0.4,
                                fill: true,
                                yAxisID: 'y-rate',
                                pointRadius: 4,
                                pointHoverRadius: 6
                            },
                            {
                                label: '輪班參與率',
                                data: data.shift_rates || [],
                                borderColor: 'rgb(59, 130, 246)',
                                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                                tension: 0.4,
                                fill: true,
                                yAxisID: 'y-rate',
                                pointRadius: 4,
                                pointHoverRadius: 6
                            },
                            {
                                label: '總參與率',
                                data: data.total_rates || [],
                                borderColor: 'rgb(168, 85, 247)',
                                backgroundColor: 'rgba(168, 85, 247, 0.1)',
                                tension: 0.4,
                                fill: true,
                                borderWidth: 3,
                                yAxisID: 'y-rate',
                                pointRadius: 5,
                                pointHoverRadius: 7
                            },
                            {
                                label: '總票數',
                                data: data.total_votes || [],
                                borderColor: 'rgb(251, 146, 60)',
                                backgroundColor: 'rgba(251, 146, 60, 0.1)',
                                tension: 0.4,
                                fill: false,
                                borderWidth: 2,
                                borderDash: [5, 5],
                                yAxisID: 'y-votes',
                                hidden: false,
                                pointRadius: 4,
                                pointHoverRadius: 6
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
                                    font: {
                                        size: 14,
                                        weight: 'bold'
                                    },
                                    usePointStyle: true,
                                    padding: 15
                                }
                            },
                            title: {
                                display: true,
                                text: `近 ${this.weeksToShow} 週投票參與趨勢`,
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
                                        let label = context.dataset.label || '';
                                        if (label) {
                                            label += ': ';
                                        }
                                        if (context.parsed.y !== null) {
                                            if (context.dataset.yAxisID === 'y-rate') {
                                                label += context.parsed.y.toFixed(1) + '%';
                                            } else {
                                                label += context.parsed.y + ' 票';
                                            }
                                        }
                                        return label;
                                    }
                                }
                            }
                        },
                        scales: {
                            'y-rate': {
                                type: 'linear',
                                display: true,
                                position: 'left',
                                beginAtZero: true,
                                max: 100,
                                ticks: {
                                    stepSize: 10,
                                    font: {
                                        size: 12
                                    },
                                    callback: function(value) {
                                        return value + '%';
                                    }
                                },
                                title: {
                                    display: true,
                                    text: '參與率 (%)',
                                    font: {
                                        size: 14,
                                        weight: 'bold'
                                    }
                                },
                                grid: {
                                    drawOnChartArea: true,
                                }
                            },
                            'y-votes': {
                                type: 'linear',
                                display: true,
                                position: 'right',
                                beginAtZero: true,
                                ticks: {
                                    stepSize: 1,
                                    font: {
                                        size: 12
                                    },
                                    callback: function(value) {
                                        return value + ' 票';
                                    }
                                },
                                title: {
                                    display: true,
                                    text: '票數',
                                    font: {
                                        size: 14,
                                        weight: 'bold'
                                    },
                                    color: 'rgb(251, 146, 60)'
                                },
                                grid: {
                                    drawOnChartArea: false,
                                }
                            },
                            x: {
                                ticks: {
                                    font: {
                                        size: 12
                                    }
                                },
                                title: {
                                    display: true,
                                    text: '週次 (月-日)',
                                    font: {
                                        size: 14,
                                        weight: 'bold'
                                    }
                                }
                            }
                        }
                    }
                });
                
                console.log('圖表創建成功');
            } catch (error) {
                console.error('創建圖表時出錯:', error);
                await this.renderEmptyChart();
            } finally {
                this.isRenderingChart = false;
            }
        },
        async renderEmptyChart() {
            // 如果正在渲染，等待
            if (this.isRenderingChart) {
                await new Promise(resolve => setTimeout(resolve, 100));
            }

            this.isRenderingChart = true;

            try {
                const ctx = document.getElementById('weeklyChart');
                if (!ctx) {
                    console.warn('找不到圖表 canvas 元素');
                    return;
                }

                // 銷毀舊圖表
                if (this.weeklyChart) {
                    try {
                        this.weeklyChart.destroy();
                        this.weeklyChart = null;
                    } catch (error) {
                        console.error('銷毀舊圖表時出錯:', error);
                        this.weeklyChart = null;
                    }
                }

                // 等待下一幀
                await new Promise(resolve => requestAnimationFrame(resolve));

                // 再次檢查 canvas
                const canvas = document.getElementById('weeklyChart');
                if (!canvas) return;

                // 創建空圖表
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
            } catch (error) {
                console.error('創建空圖表時出錯:', error);
            } finally {
                this.isRenderingChart = false;
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
                        rr_quota: this.quotas.rr,
                        shift_quota: this.quotas.shift
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
                this.quotas.rr = data.rr_quota;
                this.quotas.shift = data.shift_quota;
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
                const response = await fetch('http://127.0.0.1:5000/api/reset', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ reset_type: resetType })
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
                title: '確認重新載入',
                html: '⚠️ 警告:此操作將從 emoinfo.json 重新載入員工資料並清除所有投票記錄!<br><br>確定要繼續嗎?',
                icon: 'warning',
                showCancelButton: true,
                confirmButtonColor: '#DC2626',
                cancelButtonColor: '#6B7280',
                confirmButtonText: '確定重新載入',
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
                const response = await fetch('http://127.0.0.1:5000/api/reload', {
                    method: 'POST'
                });

                const data = await response.json();

                if (response.ok) {
                    await Swal.fire({
                        title: '重新載入成功',
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
                        title: '重新載入失敗',
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
        }
    }
}).mount('#app');