// web_frontend/admin.js

document.addEventListener('DOMContentLoaded', () => {
    // --- Konstanten ---
    const API_BASE_URL = 'http://localhost:8001';

    // --- DOM-Elemente ---
    const trainAnalysisBtn = document.getElementById('train-analysis-btn');
    const trainNarrativeBtn = document.getElementById('train-narrative-btn');
    const worldSelect = document.getElementById('world-select');
    const statusLog = document.getElementById('status-log');
    const userListContainer = document.getElementById('user-list');
    const addUserBtn = document.getElementById('add-user-btn');
    const userModal = document.getElementById('user-modal');
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

    // --- Funktionen ---

    function logStatus(message, type = 'info') {
        const p = document.createElement('p');
        const timestamp = new Date().toLocaleTimeString();
        p.innerHTML = `<span class="text-gray-500">${timestamp}:</span> ${message}`;
        if (type === 'error') p.className = 'text-red-400';
        else if (type === 'success') p.className = 'text-green-400';
        statusLog.appendChild(p);
        statusLog.scrollTop = statusLog.scrollHeight;
    }

    async function apiRequest(endpoint, method = 'GET', body = null) {
        const headers = { 'Authorization': `Bearer ${authToken}` };
        if (body) headers['Content-Type'] = 'application/json';
        
        const response = await fetch(`${API_BASE_URL}${endpoint}`, { method, headers, body: body ? JSON.stringify(body) : null });
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

        userModal.classList.remove('hidden');
        userModal.classList.add('flex');
    }

    function closeUserModal() {
        userModal.classList.add('hidden');
        userModal.classList.remove('flex');
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
            closeUserModal();
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
            users.forEach(user => {
                const userDiv = document.createElement('div');
                userDiv.className = 'p-3 bg-gray-700 rounded flex justify-between items-center';
                userDiv.innerHTML = `<div>
                    <p class="font-semibold">${user.username} <span class="text-gray-400 text-sm">(ID: ${user.user_id})</span></p>
                    <p class="text-sm text-gray-400">Rollen: ${user.roles.join(', ')}</p>
                </div>
                <div class="flex space-x-2">
                    <button data-user-id="${user.user_id}" class="edit-user-btn px-3 py-1 bg-blue-600 rounded text-sm hover:bg-blue-700">Bearbeiten</button>
                </div>`;
                userListContainer.appendChild(userDiv);
            });

            document.querySelectorAll('.edit-user-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const userId = e.target.dataset.userId;
                    const user = users.find(u => u.user_id == userId);
                    openUserModal(user);
                });
            });
        } catch (error) {
            logStatus(`Fehler beim Laden der Benutzer: ${error.message}`, 'error');
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
        
        originalTexts.analysis = trainAnalysisBtn.textContent;
        originalTexts.narrative = trainNarrativeBtn.textContent;
        trainAnalysisBtn.disabled = true;
        trainNarrativeBtn.disabled = true;
        btn.textContent = 'Training läuft...';
        
        logStatus(`Sende Anfrage für ${type}-Training... Server startet den Prozess im Hintergrund.`);
        try {
            const data = await apiRequest(url, 'POST');
            logStatus(data.message, 'success');
        } catch (error) {
            logStatus(`Fehler beim Starten des Trainings: ${error.message}`, 'error');
        } finally {
            trainAnalysisBtn.disabled = false;
            trainNarrativeBtn.disabled = !worldSelect.value;
            trainAnalysisBtn.textContent = originalTexts.analysis;
            trainNarrativeBtn.textContent = originalTexts.narrative;
        }
    }
    
    // --- Event-Listener ---
    addUserBtn.addEventListener('click', () => openUserModal());
    cancelUserModalBtn.addEventListener('click', closeUserModal);
    saveUserModalBtn.addEventListener('click', saveUser);
    trainAnalysisBtn.addEventListener('click', () => triggerTraining('analysis'));
    trainNarrativeBtn.addEventListener('click', () => triggerTraining('narrative'));

    // --- Initialisierung ---
    if (!authToken) {
        logStatus("Fehler: Nicht angemeldet. Bitte loggen Sie sich zuerst in der Hauptanwendung ein und laden Sie diese Seite neu.", "error");
        document.querySelectorAll('button, select').forEach(el => el.disabled = true);
    } else {
        fetchUsers();
        fetchWorldsForTraining();
    }
});