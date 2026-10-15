document.addEventListener('DOMContentLoaded', () => {
    const folderPathInput = document.getElementById('folderPath');
    const outputFolderInput = document.getElementById('outputFolder');
    const scanBtn = document.getElementById('scanBtn');
    const processBtn = document.getElementById('processBtn');
    const clearLogsBtn = document.getElementById('clearLogsBtn');

    const statsGrid = document.getElementById('statsGrid');
    const progressCard = document.getElementById('progressCard');
    const tableCard = document.getElementById('tableCard');
    const logCard = document.getElementById('logCard');

    const statTotalAudios = document.getElementById('statTotalAudios');
    const statAudiosToSplit = document.getElementById('statAudiosToSplit');
    const statTotalChunks = document.getElementById('statTotalChunks');

    const previewTableBody = document.getElementById('previewTableBody');
    const logTerminal = document.getElementById('logTerminal');

    const progressFill = document.getElementById('progressFill');
    const progressPercent = document.getElementById('progressPercent');
    const progressTitle = document.getElementById('progressTitle');
    const systemStatusBadge = document.getElementById('systemStatusBadge');

    let currentScanData = null;
    let statusPollInterval = null;

    // Log helper
    function logMsg(msg, type = 'normal') {
        const div = document.createElement('div');
        div.className = `log-line ${type}`;
        div.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
        logTerminal.appendChild(div);
        logTerminal.scrollTop = logTerminal.scrollHeight;
    }

    clearLogsBtn.addEventListener('click', () => {
        logTerminal.innerHTML = '';
    });

    // Scan Folder Event
    scanBtn.addEventListener('click', async () => {
        const pathVal = folderPathInput.value.trim();
        if (!pathVal) {
            alert('Please enter a valid directory folder path.');
            return;
        }

        scanBtn.disabled = true;
        scanBtn.querySelector('span').textContent = 'Scanning...';
        logCard.style.display = 'block';
        logMsg(`Scanning directory: ${pathVal}`, 'info');

        try {
            const res = await fetch('/api/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder_path: pathVal })
            });

            const rawText = await res.text();
            let data;
            try {
                data = JSON.parse(rawText);
            } catch (e) {
                throw new Error(rawText || `Server returned HTTP status ${res.status}`);
            }
            if (!res.ok) {
                const errMsg = (data && data.detail) ? data.detail : (typeof data === 'string' ? data : 'Scan failed');
                throw new Error(errMsg);
            }



            currentScanData = data;

            // Render stats
            statTotalAudios.textContent = data.total_audios;
            statAudiosToSplit.textContent = data.audios_over_30m;
            statTotalChunks.textContent = data.total_chunks;

            statsGrid.style.display = 'grid';
            tableCard.style.display = 'block';

            // Populate preview table
            previewTableBody.innerHTML = '';
            
            data.files.forEach((file) => {
                file.parts.forEach((part) => {
                    const tr = document.createElement('tr');
                    
                    const isSplit = file.needs_split;
                    const splitBadgeHtml = isSplit 
                        ? `<span class="badge badge-split">Split (${part.part_num}/${file.total_parts})</span>` 
                        : `<span class="badge badge-single">Direct Copy</span>`;

                    tr.innerHTML = `
                        <td>${String(file.video_seq).padStart(2, '0')}</td>
                        <td>${String(part.part_num).padStart(2, '0')}</td>
                        <td>${file.original_filename}</td>
                        <td>${file.duration_formatted}</td>
                        <td>${splitBadgeHtml}</td>
                        <td style="color: var(--accent); font-weight: 500;">${part.new_filename}</td>
                    `;
                    previewTableBody.appendChild(tr);
                });
            });

            logMsg(`Found ${data.total_audios} audio file(s). ${data.audios_over_30m} file(s) require 29-minute chunking. Total output: ${data.total_chunks} parts.`, 'success');

        } catch (err) {
            logMsg(`Scan Error: ${err.message}`, 'error');
            alert(`Error: ${err.message}`);
        } finally {
            scanBtn.disabled = false;
            scanBtn.querySelector('span').textContent = 'Analyze Folder';
        }
    });

    // Start Process Event
    processBtn.addEventListener('click', async () => {
        if (!currentScanData || currentScanData.files.length === 0) {
            alert('Please analyze a folder containing audio files first.');
            return;
        }

        const pathVal = folderPathInput.value.trim();
        const outVal = outputFolderInput.value.trim();

        processBtn.disabled = true;
        scanBtn.disabled = true;
        progressCard.style.display = 'block';
        systemStatusBadge.innerHTML = `<span class="pulse-dot" style="background: var(--warning)"></span> Processing...`;

        logMsg(`Initiating audio slicing and batch rename operation...`, 'info');

        try {
            const res = await fetch('/api/process', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    folder_path: pathVal,
                    output_folder: outVal || null
                })
            });

            const rawText = await res.text();
            let data;
            try {
                data = JSON.parse(rawText);
            } catch (e) {
                throw new Error(rawText || `Server returned HTTP status ${res.status}`);
            }
            if (!res.ok) throw new Error(data.detail || 'Failed to start processing');


            logMsg(`Output folder destination: ${data.output_folder}`, 'info');

            // Start polling status
            startPollingStatus();

        } catch (err) {
            logMsg(`Error starting job: ${err.message}`, 'error');
            alert(`Error: ${err.message}`);
            processBtn.disabled = false;
            scanBtn.disabled = false;
        }
    });

    function startPollingStatus() {
        if (statusPollInterval) clearInterval(statusPollInterval);

        let lastLogCount = 0;

        statusPollInterval = setInterval(async () => {
            try {
                const res = await fetch('/api/status');
                const st = await res.json();

                // Append new logs
                if (st.logs && st.logs.length > lastLogCount) {
                    for (let i = lastLogCount; i < st.logs.length; i++) {
                        const line = st.logs[i];
                        const logType = line.startsWith('SUCCESS') ? 'success' : (line.startsWith('ERROR') ? 'error' : 'normal');
                        logMsg(line, logType);
                    }
                    lastLogCount = st.logs.length;
                }

                // Update Progress bar
                if (st.total_chunks > 0) {
                    const pct = Math.round((st.processed_count / st.total_chunks) * 100);
                    progressFill.style.width = `${pct}%`;
                    progressPercent.textContent = `${pct}%`;
                    progressTitle.textContent = `Processing chunk ${st.processed_count} of ${st.total_chunks} (${st.current_file})...`;
                }

                if (st.completed || st.error) {
                    clearInterval(statusPollInterval);
                    processBtn.disabled = false;
                    scanBtn.disabled = false;
                    
                    if (st.completed) {
                        systemStatusBadge.innerHTML = `<span class="pulse-dot" style="background: var(--accent)"></span> Processing Complete`;
                        progressTitle.textContent = `Finished processing all ${st.total_chunks} chunk parts successfully!`;
                    } else if (st.error) {
                        systemStatusBadge.innerHTML = `<span class="pulse-dot" style="background: var(--danger)"></span> Error Encountered`;
                        progressTitle.textContent = `Processing failed. Check logs below.`;
                    }
                }

            } catch (e) {
                console.error("Status check failed", e);
            }
        }, 800);
    }
});
