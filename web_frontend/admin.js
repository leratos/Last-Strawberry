// web_frontend/admin.js

document.addEventListener('DOMContentLoaded', () => {
    // --- Konstanten ---
    const API_BASE_URL = 'http://127.0.0.1:8001';

    // --- Utility Funktionen ---
    
    // HTML-Escaping Funktion für XSS-Schutz
    function escapeHTML(str) {
        if (typeof str !== 'string') return str;
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    // --- DOM-Elemente ---
    const trainAnalysisBtn = document.getElementById('train-analysis-btn');
    const trainNarrativeBtn = document.getElementById('train-narrative-btn');
    const worldSelect = document.getElementById('world-select');
    const statusLog = document.getElementById('status-log');
    const userListContainer = document.getElementById('user-list');
    const addUserBtn = document.getElementById('add-user-btn');
    const userModal = document.getElementById('user-modal');
    const closeUserModal = document.getElementById('close-user-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalUserId = document.getElementById('modal-user-id');
    const modalUsername = document.getElementById('modal-username');
    const modalPassword = document.getElementById('modal-password');
    const modalRoleAdmin = document.getElementById('role-admin');
    const modalRoleGm = document.getElementById('role-gamemaster');
    const cancelUserModalBtn = document.getElementById('cancel-user-modal-btn');
    const saveUserModalBtn = document.getElementById('save-user-modal-btn');

    // --- Anwendungs-Zustand ---
    const authToken = localStorage.getItem('lastStrawberryToken');

    // --- Utility Functions ---
    
    function showModal(modal) {
        modal.classList.remove('hidden');
        modal.classList.add('flex');
        setTimeout(() => feather.replace(), 100);
    }

    function hideModal(modal) {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
    }

    function logStatus(message, type = 'info') {
        const p = document.createElement('div');
        const timestamp = new Date().toLocaleTimeString();
        p.className = 'flex items-center space-x-2 mb-2';
        
        let iconName = 'info';
        let colorClass = 'text-blue-400';
        
        if (type === 'error') {
            iconName = 'alert-circle';
            colorClass = 'text-red-400';
        } else if (type === 'success') {
            iconName = 'check-circle';
            colorClass = 'text-green-400';
        }
        
        p.innerHTML = `
            <i data-feather="${iconName}" class="w-4 h-4 ${colorClass}"></i>
            <span class="text-gray-500">${timestamp}:</span>
            <span class="${colorClass}">${escapeHTML(message)}</span>
        `;
        
        statusLog.appendChild(p);
        feather.replace();
        statusLog.scrollTop = statusLog.scrollHeight;
    }

    async function apiRequest(endpoint, method = 'GET', body = null) {
        const headers = { 'Authorization': `Bearer ${authToken}` };
        if (body) headers['Content-Type'] = 'application/json';
        
        const response = await fetch(`${API_BASE_URL}${endpoint}`, { 
            method, 
            headers, 
            body: body ? JSON.stringify(body) : null 
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Ein Server-Fehler ist aufgetreten.');
        return data;
    }
    
    // --- Benutzerverwaltung ---
    
    function openUserModal(user = null) {
        modalUserId.value = user ? user.user_id : '';
        modalUsername.value = user ? user.username : '';
        modalUsername.disabled = !!user;
        modalPassword.value = '';
        modalPassword.placeholder = user ? 'Neues Passwort (leer lassen, um nicht zu ändern)' : 'Passwort';
        modalTitle.textContent = user ? `Benutzer bearbeiten: ${user.username}` : 'Neuen Benutzer anlegen';
        
        modalRoleAdmin.checked = user ? user.roles.includes('admin') : false;
        modalRoleGm.checked = user ? user.roles.includes('gamemaster') : true;
        modalRoleAdmin.disabled = user && user.user_id === 1;

        showModal(userModal);
    }

    function closeUserModalHandler() {
        hideModal(userModal);
    }

    async function saveUser() {
        const userId = modalUserId.value;
        const username = modalUsername.value;
        const password = modalPassword.value;
        const roles = [];
        if (modalRoleAdmin.checked) roles.push('admin');
        if (modalRoleGm.checked) roles.push('gamemaster');

        try {
            if (userId) { // Bearbeiten
                await apiRequest(`/admin/users/${userId}`, 'PUT', { password: password || null, roles });
                logStatus(`Benutzer ${username} aktualisiert.`, 'success');
            } else { // Erstellen
                if (!username || !password) throw new Error("Benutzername und Passwort sind erforderlich.");
                await apiRequest('/admin/users', 'POST', { username, password, roles });
                logStatus(`Benutzer ${username} erfolgreich erstellt.`, 'success');
            }
            closeUserModalHandler();
            fetchUsers();
        } catch (error) {
            logStatus(`Fehler beim Speichern des Benutzers: ${error.message}`, 'error');
            alert(`Fehler: ${error.message}`);
        }
    }

    async function fetchUsers() {
        try {
            const users = await apiRequest('/admin/users');
            userListContainer.innerHTML = '';
            
            if (users.length === 0) {
                userListContainer.innerHTML = `
                    <div class="text-center py-8">
                        <i data-feather="users" class="w-12 h-12 mx-auto text-gray-500 mb-4"></i>
                        <p class="text-gray-400">Noch keine Benutzer vorhanden.</p>
                    </div>
                `;
                feather.replace();
                return;
            }
            
            users.forEach(user => {
                const userDiv = document.createElement('div');
                userDiv.className = 'glass-card p-4 rounded-lg flex justify-between items-center hover:bg-opacity-80 transition-all';
                userDiv.innerHTML = `
                    <div class="flex items-center space-x-3">
                        <div class="w-10 h-10 bg-gradient-to-br from-purple-600 to-indigo-600 rounded-full flex items-center justify-center">
                            <span class="text-sm font-bold text-white">${escapeHTML(user.username.charAt(0).toUpperCase())}</span>
                        </div>
                        <div>
                            <p class="font-semibold text-white">${escapeHTML(user.username)}</p>
                            <p class="text-sm text-gray-400">ID: ${escapeHTML(user.user_id.toString())} • Rollen: ${escapeHTML(user.roles.join(', '))}</p>
                        </div>
                    </div>
                    <div class="flex space-x-2">
                        <button data-user-id="${escapeHTML(user.user_id.toString())}" class="edit-user-btn px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors">
                            <span class="flex items-center space-x-1">
                                <i data-feather="edit-2" class="w-4 h-4"></i>
                                <span>Bearbeiten</span>
                            </span>
                        </button>
                    </div>
                `;
                userListContainer.appendChild(userDiv);
            });

            // Update feather icons
            feather.replace();

            document.querySelectorAll('.edit-user-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const userId = e.target.closest('button').dataset.userId;
                    const user = users.find(u => u.user_id == userId);
                    openUserModal(user);
                });
            });
        } catch (error) {
            logStatus(`Fehler beim Laden der Benutzer: ${error.message}`, 'error');
            userListContainer.innerHTML = `
                <div class="text-center py-8">
                    <i data-feather="alert-circle" class="w-12 h-12 mx-auto text-red-500 mb-4"></i>
                    <p class="text-red-400">${escapeHTML(error.message)}</p>
                </div>
            `;
            feather.replace();
        }
    }

    async function fetchWorldsForTraining() {
        try {
            const data = await apiRequest('/worlds');
            worldSelect.innerHTML = '<option value="">-- Bitte eine Welt wählen --</option>';
            if (data.worlds && data.worlds.length > 0) {
                data.worlds.forEach(world => {
                    const option = document.createElement('option');
                    option.value = world.world_id;
                    option.textContent = `${world.world_name}`;
                    option.dataset.worldName = world.world_name;
                    worldSelect.appendChild(option);
                });
            } else {
                worldSelect.innerHTML = '<option>Keine Welten gefunden</option>';
            }
        } catch (error) {
            logStatus(`Fehler beim Laden der Welten: ${error.message}`, "error");
        }
    }
    
    worldSelect.addEventListener('change', () => {
        trainNarrativeBtn.disabled = !worldSelect.value;
    });

    async function triggerTraining(type) {
        let url, btn;
        const originalTexts = {};

        if (type === 'analysis') {
            url = `${API_BASE_URL}/admin/train_analysis`;
            btn = trainAnalysisBtn;
        } else if (type === 'narrative') {
            const worldId = worldSelect.value;
            if (!worldId) {
                logStatus("Bitte wählen Sie zuerst eine Welt.", "error");
                return;
            }
            const worldName = worldSelect.options[worldSelect.selectedIndex].dataset.worldName;
            url = `${API_BASE_URL}/admin/train_narrative/${worldId}?world_name=${encodeURIComponent(worldName)}`;
            btn = trainNarrativeBtn;
        } else return;
        
        originalTexts.analysis = trainAnalysisBtn.innerHTML;
        originalTexts.narrative = trainNarrativeBtn.innerHTML;
        
        trainAnalysisBtn.disabled = true;
        trainNarrativeBtn.disabled = true;
        btn.innerHTML = '<i data-feather="loader" class="w-4 h-4 animate-spin"></i> <span>Training läuft...</span>';
        feather.replace();
        
        logStatus(`Sende Anfrage für ${type}-Training... Server startet den Prozess im Hintergrund.`);
        try {
            const data = await apiRequest(url, 'POST');
            logStatus(data.message, 'success');
        } catch (error) {
            logStatus(`Fehler beim Starten des Trainings: ${error.message}`, 'error');
        } finally {
            trainAnalysisBtn.disabled = false;
            trainNarrativeBtn.disabled = !worldSelect.value;
            trainAnalysisBtn.innerHTML = originalTexts.analysis;
            trainNarrativeBtn.innerHTML = originalTexts.narrative;
            feather.replace();
        }
    }
    
    // --- Event-Listener ---
    addUserBtn.addEventListener('click', () => openUserModal());
    closeUserModal.addEventListener('click', closeUserModalHandler);
    cancelUserModalBtn.addEventListener('click', closeUserModalHandler);
    saveUserModalBtn.addEventListener('click', saveUser);
    trainAnalysisBtn.addEventListener('click', () => triggerTraining('analysis'));
    trainNarrativeBtn.addEventListener('click', () => triggerTraining('narrative'));

    // Close modal on outside click
    userModal.addEventListener('click', (e) => {
        if (e.target === userModal) {
            closeUserModalHandler();
        }
    });

    // --- Initialisierung ---
    if (!authToken) {
        logStatus("Fehler: Nicht angemeldet. Bitte loggen Sie sich zuerst in der Hauptanwendung ein und laden Sie diese Seite neu.", "error");
        document.querySelectorAll('button, select').forEach(el => el.disabled = true);
    } else {
        logStatus("Admin-Panel initialisiert. Lade Daten...", "success");
        fetchUsers();
        fetchWorldsForTraining();
    }
    
    // Initialize feather icons
    feather.replace();
});