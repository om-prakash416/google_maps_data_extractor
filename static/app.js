document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('scrape-form');
    const startBtn = document.getElementById('start-btn');
    const stopBtn = document.getElementById('stop-btn');
    const statusText = document.getElementById('status-text');
    const statusDot = document.getElementById('status-dot');
    const progressBar = document.querySelector('.progress-bar-container');
    const logConsole = document.getElementById('log-console');
    const exportCard = document.getElementById('export-card');
    const exportBtns = document.querySelectorAll('.btn-export');

    let currentJobId = null;
    let pollInterval = null;

    function appendLog(msg, type = 'normal') {
        const p = document.createElement('p');
        p.className = `log-${type}`;
        p.textContent = msg;
        logConsole.appendChild(p);
        logConsole.scrollTop = logConsole.scrollHeight;
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const query = document.getElementById('query').value;
        const area = document.getElementById('area').value;
        const pincode = document.getElementById('pincode').value;
        const radius = document.getElementById('radius').value;
        const max_results = document.getElementById('max_results').value;

        // Reset UI
        startBtn.disabled = true;
        stopBtn.disabled = false;
        exportCard.classList.add('disabled');
        logConsole.innerHTML = '';
        progressBar.classList.add('active');
        
        statusText.textContent = "Status: Queuing...";
        statusDot.className = 'pulse-dot running';

        try {
            const res = await fetch('/api/scrape', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, area, pincode, radius, max_results })
            });
            const data = await res.json();
            
            if (res.ok) {
                currentJobId = data.job_id;
                appendLog(`✅ ${data.message}`, 'success');
                startPolling();
            } else {
                throw new Error(data.error || "Failed to start job");
            }
        } catch (err) {
            appendLog(`❌ Error: ${err.message}`, 'error');
            resetUI(false);
        }
    });

    stopBtn.addEventListener('click', async () => {
        if (!currentJobId) return;
        
        stopBtn.disabled = true;
        appendLog("🛑 Stop signal sent. Waiting for graceful exit...", 'error');
        statusText.textContent = "Status: Stopping...";
        
        await fetch(`/api/stop/${currentJobId}`, { method: 'POST' });
    });

    function startPolling() {
        if (pollInterval) clearInterval(pollInterval);
        
        pollInterval = setInterval(async () => {
            if (!currentJobId) return;
            
            try {
                const res = await fetch(`/api/status/${currentJobId}`);
                if (!res.ok) {
                    if (res.status === 404) {
                        throw new Error("Job not found (404). The server may have restarted due to memory limits.");
                    }
                    throw new Error("Status check failed");
                }
                
                const data = await res.json();
                
                // Print logs
                data.logs.forEach(log => {
                    let type = 'normal';
                    if (log.includes('❌')) type = 'error';
                    if (log.includes('✅') || log.includes('🎉')) type = 'success';
                    if (log.includes('🚀') || log.includes('🔍')) type = 'info';
                    appendLog(log, type);
                });

                if (data.status === 'running') {
                    statusText.textContent = "Status: Scraping...";
                }

                if (data.status === 'completed' || data.status === 'error') {
                    clearInterval(pollInterval);
                    pollInterval = null;
                    progressBar.classList.remove('active');
                    
                    if (data.status === 'completed') {
                        statusText.textContent = `Status: Completed (${data.results_count} items)`;
                        statusDot.className = 'pulse-dot completed';
                        if (data.results_count > 0) {
                            exportCard.classList.remove('disabled');
                        }
                    } else {
                        statusText.textContent = "Status: Error";
                        statusDot.className = 'pulse-dot error';
                    }
                    
                    resetUI(false);
                }
            } catch (err) {
                console.error("Polling error:", err);
                clearInterval(pollInterval);
                pollInterval = null;
                progressBar.classList.remove('active');
                statusText.textContent = "Status: Server Error";
                statusDot.className = 'pulse-dot error';
                appendLog(`❌ Polling error: ${err.message}`, 'error');
                resetUI(false);
            }
        }, 3000); // poll every 3 seconds
    }

    function resetUI(clearData = true) {
        startBtn.disabled = false;
        stopBtn.disabled = true;
        if (clearData) {
            progressBar.classList.remove('active');
            statusDot.className = 'pulse-dot';
            statusText.textContent = "Status: Ready";
        }
    }

    exportBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            if (!currentJobId) return;
            const format = btn.getAttribute('data-format');
            window.location.href = `/api/download/${currentJobId}/${format}`;
        });
    });
});
