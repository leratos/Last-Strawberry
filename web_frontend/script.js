// web_frontend/script.js

document.addEventListener('DOMContentLoaded', () => {
    // --- Konstanten und Konfiguration ---
    const API_BASE_URL = 'http://localhost:8001';
    const ATTRIBUTES = ["Stärke", "Geschicklichkeit", "Konstitution", "Intelligenz", "Weisheit", "Charisma", "Wahrnehmung"];
    const POINT_BUY_BUDGET = 75;
    const MIN_SCORE = 8;
    const MAX_SCORE = 15;

    // --- DOM-Elemente holen ---
    const screens = {
        login: document.getElementById('login-screen'),
        worldSelection: document.getElementById('world-selection-screen'),
        createWorld: document.getElementById('create-world-screen'),
        game: document.getElementById('game-screen'),
    };
    
    // Navigation
    const navbar = document.getElementById('navbar');
    const navWorldName = document.getElementById('nav-world-name');
    const profileBtn = document.getElementById('profile-btn');
    const adminLink = document.getElementById('admin-link');
    const logoutBtn = document.getElementById('logout-btn');
    
    // Login elements
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');
    const loginButton = document.getElementById('login-button');
    const loginError = document.getElementById('login-error');
    
    // World selection elements
    const worldListContainer = document.getElementById('world-list');
    const showCreateWorldBtn = document.getElementById('show-create-world-btn');
    const createWorldButton = document.getElementById('create-world-button');
    const cancelCreateBtn = document.getElementById('cancel-create-btn');
    
    // Game elements
    const gameTitle = document.getElementById('game-title');
    const chatContainer = document.getElementById('chat-container');
    const gameInputArea = document.getElementById('game-input-area');
    const commandInput = document.getElementById('command-input');
    const sendButton = document.getElementById('send-button');
    const correctLastBtn = document.getElementById('correct-last-btn');

    // Modal elements
    const profileModal = document.getElementById('profile-modal');
    const closeProfileModal = document.getElementById('close-profile-modal');
    const profileAvatar = document.getElementById('profile-avatar');
    const profileUsername = document.getElementById('profile-username');
    const profileRoles = document.getElementById('profile-roles');
    const changePasswordBtn = document.getElementById('change-password-btn');
    
    const passwordModal = document.getElementById('password-modal');
    const closePasswordModal = document.getElementById('close-password-modal');
    const currentPasswordInput = document.getElementById('current-password');
    const newPasswordInput = document.getElementById('new-password');
    const confirmPasswordInput = document.getElementById('confirm-password');
    const cancelPasswordBtn = document.getElementById('cancel-password-btn');
    const savePasswordBtn = document.getElementById('save-password-btn');
    const passwordError = document.getElementById('password-error');
    const passwordSuccess = document.getElementById('password-success');
    
    const storyExportModal = document.getElementById('story-export-modal');
    const storyExportBtn = document.getElementById('story-export-btn');
    const closeStoryExportModal = document.getElementById('close-story-export-modal');
    const exportFormatSelect = document.getElementById('export-format');
    const exportWorldSelect = document.getElementById('export-world');
    const cancelExportBtn = document.getElementById('cancel-export-btn');
    const startExportBtn = document.getElementById('start-export-btn');
    
    const correctionModal = document.getElementById('correction-modal');
    const closeCorrectionModal = document.getElementById('close-correction-modal');
    const narrativeTextarea = document.getElementById('narrative-textarea');
    const jsonTextarea = document.getElementById('json-textarea');
    const cancelCorrectionBtn = document.getElementById('cancel-correction-btn');
    const saveCorrectionBtn = document.getElementById('save-correction-btn');

    // --- Anwendungs-Zustand ---
    let authToken = null;
    let currentUser = null;
    let activeWorld = { world_id: null, player_id: null };
    let attributePoints = {};
    let lastAIResponse = null; // Speichert die letzte AI-Antwort für Korrekturen

    // --- Utility Funktionen ---
    
    function showScreen(screenName) {
        Object.values(screens).forEach(screen => screen.classList.remove('active'));
        if (screens[screenName]) {
            screens[screenName].classList.add('active');
        }
        
        // Show/hide navbar based on screen
        if (screenName === 'login') {
            navbar.classList.add('hidden');
        } else {
            navbar.classList.remove('hidden');
            // Show admin link only for admins
            if (currentUser && currentUser.roles && currentUser.roles.includes('admin')) {
                adminLink.classList.remove('hidden');
            } else {
                adminLink.classList.add('hidden');
            }
        }
        
        // Show/hide game input area based on screen and game state
        if (screenName === 'game' && activeWorld.world_id && activeWorld.player_id) {
            gameInputArea.classList.add('active');
        } else {
            gameInputArea.classList.remove('active');
        }
        
        // Update feather icons after DOM changes
        setTimeout(() => feather.replace(), 100);
    }

    function showModal(modal) {
        modal.classList.remove('hidden');
        modal.classList.add('flex');
        setTimeout(() => feather.replace(), 100);
    }

    function hideModal(modal) {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
    }

    function showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `fixed top-4 right-4 z-50 px-6 py-4 rounded-lg shadow-lg transform transition-all duration-300 translate-x-full`;
        
        if (type === 'success') {
            notification.className += ' bg-green-600 text-white';
        } else if (type === 'error') {
            notification.className += ' bg-red-600 text-white';
        } else {
            notification.className += ' bg-blue-600 text-white';
        }
        
        notification.innerHTML = `
            <div class="flex items-center space-x-2">
                <i data-feather="${type === 'success' ? 'check-circle' : type === 'error' ? 'alert-circle' : 'info'}" class="w-5 h-5"></i>
                <span>${message}</span>
            </div>
        `;
        
        document.body.appendChild(notification);
        feather.replace();
        
        // Animate in
        setTimeout(() => {
            notification.classList.remove('translate-x-full');
        }, 100);
        
        // Remove after 5 seconds
        setTimeout(() => {
            notification.classList.add('translate-x-full');
            setTimeout(() => {
                document.body.removeChild(notification);
            }, 300);
        }, 5000);
    }

    async function apiRequest(endpoint, method = 'GET', body = null) {
        const headers = {};
        if (authToken) {
            headers['Authorization'] = `Bearer ${authToken}`;
        }
        if (body) {
            headers['Content-Type'] = 'application/json';
        }
        
        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
            method,
            headers,
            body: body ? JSON.stringify(body) : null
        });
        
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || 'Ein Server-Fehler ist aufgetreten.');
        }
        return data;
    }

    function displayMessage(htmlContent, type = 'story') {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'mb-4 p-4 rounded-lg';

        // Markdown-ähnliches Parsing für Fett und Kursiv
        let processedContent = htmlContent.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>');
        processedContent = processedContent.replace(/\*(.*?)\*/g, '<i>$1</i>');

        if (type === 'story') {
            messageDiv.className += ' story-text text-gray-300 bg-gray-800 bg-opacity-50';
            messageDiv.innerHTML = processedContent.split('\n').map(p => `<p>${p}</p>`).join('');
        } else if (type === 'player') {
            messageDiv.className += ' player-input-text text-blue-400 font-semibold bg-blue-900 bg-opacity-30';
            messageDiv.innerHTML = `<div class="flex items-center space-x-2">
                <i data-feather="user" class="w-4 h-4"></i>
                <span>${htmlContent}</span>
            </div>`;
        } else if (type === 'event') {
            messageDiv.className += ' text-yellow-400 bg-yellow-900 bg-opacity-30';
            messageDiv.innerHTML = `<div class="flex items-center space-x-2">
                <i data-feather="star" class="w-4 h-4"></i>
                <span>${processedContent}</span>
            </div>`;
        }
        
        chatContainer.appendChild(messageDiv);
        feather.replace();
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    // --- Authentication ---

    async function handleLogin() {
        loginError.textContent = '';
        loginButton.disabled = true;
        
        const originalText = loginButton.innerHTML;
        loginButton.innerHTML = '<i data-feather="loader" class="w-5 h-5 animate-spin"></i>';
        feather.replace();

        try {
            const formData = new FormData();
            formData.append('username', usernameInput.value);
            formData.append('password', passwordInput.value);

            const response = await fetch(`${API_BASE_URL}/token`, { method: 'POST', body: formData });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Anmeldung fehlgeschlagen.');
            }
            const data = await response.json();
            authToken = data.access_token;
            localStorage.setItem('lastStrawberryToken', authToken);
            
            // Get user profile
            await loadUserProfile();
            
            await loadWorlds();
            showScreen('worldSelection');
            showNotification('Erfolgreich angemeldet!', 'success');
        } catch (error) {
            loginError.textContent = `Fehler: ${error.message}`;
            showNotification(`Anmeldung fehlgeschlagen: ${error.message}`, 'error');
        } finally {
            loginButton.disabled = false;
            loginButton.innerHTML = originalText;
            feather.replace();
        }
    }

    async function loadUserProfile() {
        try {
            currentUser = await apiRequest('/profile');
            profileUsername.textContent = currentUser.username;
            profileRoles.textContent = `Rollen: ${currentUser.roles.join(', ')}`;
            profileAvatar.textContent = currentUser.username.charAt(0).toUpperCase();
        } catch (error) {
            console.error('Failed to load user profile:', error);
        }
    }

    function handleLogout() {
        authToken = null;
        currentUser = null;
        localStorage.removeItem('lastStrawberryToken');
        
        // Reset game state and hide input area
        activeWorld = { world_id: null, player_id: null };
        gameInputArea.classList.remove('active');
        chatContainer.innerHTML = '';
        
        showScreen('login');
        showNotification('Erfolgreich abgemeldet!', 'success');
        
        // Clear forms
        usernameInput.value = '';
        passwordInput.value = '';
        loginError.textContent = '';
    }

    // --- Profile Management ---

    async function handlePasswordChange() {
        passwordError.textContent = '';
        passwordSuccess.textContent = '';
        
        const currentPassword = currentPasswordInput.value;
        const newPassword = newPasswordInput.value;
        const confirmPassword = confirmPasswordInput.value;
        
        if (!currentPassword || !newPassword || !confirmPassword) {
            passwordError.textContent = 'Alle Felder sind erforderlich.';
            return;
        }
        
        if (newPassword !== confirmPassword) {
            passwordError.textContent = 'Die neuen Passwörter stimmen nicht überein.';
            return;
        }
        
        if (newPassword.length < 6) {
            passwordError.textContent = 'Das neue Passwort muss mindestens 6 Zeichen lang sein.';
            return;
        }
        
        savePasswordBtn.disabled = true;
        const originalText = savePasswordBtn.textContent;
        savePasswordBtn.textContent = 'Speichere...';
        
        try {
            await apiRequest('/profile/password', 'PUT', {
                current_password: currentPassword,
                new_password: newPassword
            });
            
            passwordSuccess.textContent = 'Passwort erfolgreich geändert!';
            showNotification('Passwort erfolgreich geändert!', 'success');
            
            // Clear form
            currentPasswordInput.value = '';
            newPasswordInput.value = '';
            confirmPasswordInput.value = '';
            
            // Close modal after 2 seconds
            setTimeout(() => {
                hideModal(passwordModal);
            }, 2000);
            
        } catch (error) {
            passwordError.textContent = error.message;
            showNotification(`Fehler beim Ändern des Passworts: ${error.message}`, 'error');
        } finally {
            savePasswordBtn.disabled = false;
            savePasswordBtn.textContent = originalText;
        }
    }

    // --- World Management ---

    async function loadWorlds() {
        try {
            const data = await apiRequest('/worlds');
            worldListContainer.innerHTML = '';
            
            if (data.worlds.length === 0) {
                worldListContainer.innerHTML = `
                    <div class="text-center py-8">
                        <i data-feather="globe" class="w-12 h-12 mx-auto text-gray-500 mb-4"></i>
                        <p class="text-gray-400">Noch keine Welten vorhanden.</p>
                        <p class="text-gray-500 text-sm">Erstelle eine neue Welt, um dein Abenteuer zu beginnen!</p>
                    </div>
                `;
                feather.replace();
            } else {
                data.worlds.forEach(world => {
                    const worldDiv = document.createElement('div');
                    worldDiv.className = 'glass-card p-4 rounded-lg hover:bg-opacity-80 transition-all cursor-pointer group';
                    worldDiv.innerHTML = `
                        <div class="flex justify-between items-center">
                            <div class="flex-1">
                                <h4 class="font-semibold text-white group-hover:text-purple-300 transition-colors">${world.world_name}</h4>
                                <p class="text-sm text-gray-400 mt-1">Spieler: ${world.character_name || 'Unbekannt'}</p>
                                <p class="text-xs text-gray-500 mt-1">Erstellt: ${new Date(world.created_at).toLocaleDateString('de-DE')}</p>
                            </div>
                            <div class="flex items-center space-x-2">
                                <i data-feather="play-circle" class="w-5 h-5 text-purple-400"></i>
                            </div>
                        </div>
                    `;
                    worldDiv.addEventListener('click', () => {
                        startGame(world.world_id, world.player_id, world.world_name);
                    });
                    worldListContainer.appendChild(worldDiv);
                });
                feather.replace();
            }
        } catch (error) {
            worldListContainer.innerHTML = `
                <div class="text-center py-8">
                    <i data-feather="alert-circle" class="w-12 h-12 mx-auto text-red-500 mb-4"></i>
                    <p class="text-red-400">${error.message}</p>
                </div>
            `;
            feather.replace();
            showNotification(`Fehler beim Laden der Welten: ${error.message}`, 'error');
        }
    }

    // --- Character Creation ---

    function setupAttributeAllocator() {
        const container = document.getElementById('attributes-container');
        container.innerHTML = '';
        attributePoints = {};
        
        ATTRIBUTES.forEach(attr => {
            attributePoints[attr] = 10;
            const attrDiv = document.createElement('div');
            attrDiv.className = 'glass-card p-4 rounded-lg';
            attrDiv.innerHTML = `
                <div class="text-center">
                    <label class="font-medium text-white block mb-3">${attr}</label>
                    <div class="flex items-center justify-center space-x-3">
                        <button data-attr="${attr}" data-delta="-1" class="attr-btn w-10 h-10 bg-red-600 hover:bg-red-700 text-white rounded-full transition-colors">
                            <i data-feather="minus" class="w-4 h-4"></i>
                        </button>
                        <span id="val-${attr}" class="w-12 h-12 bg-gray-700 rounded-full flex items-center justify-center text-xl font-bold text-white">10</span>
                        <button data-attr="${attr}" data-delta="1" class="attr-btn w-10 h-10 bg-green-600 hover:bg-green-700 text-white rounded-full transition-colors">
                            <i data-feather="plus" class="w-4 h-4"></i>
                        </button>
                    </div>
                </div>
            `;
            container.appendChild(attrDiv);
        });
        feather.replace();
        updatePointsDisplay();
    }

    function updatePointsDisplay() {
        const totalSpent = Object.values(attributePoints).reduce((sum, val) => sum + val, 0);
        const remaining = POINT_BUY_BUDGET - totalSpent;
        const display = document.getElementById('points-display');
        
        display.innerHTML = `
            <div class="flex items-center justify-center space-x-2">
                <i data-feather="zap" class="w-5 h-5"></i>
                <span>Verbleibende Punkte: ${remaining}</span>
            </div>
        `;
        
        createWorldButton.disabled = remaining !== 0;
        
        if (remaining === 0) {
            display.className = 'text-center font-bold mb-6 text-lg text-green-400';
        } else {
            display.className = 'text-center font-bold mb-6 text-lg text-red-400';
        }
        
        feather.replace();
    }

    async function handleCreateWorld() {
        const createError = document.getElementById('create-error');
        createError.textContent = '';
        createWorldButton.disabled = true;
        
        const originalText = createWorldButton.innerHTML;
        createWorldButton.innerHTML = '<i data-feather="loader" class="w-5 h-5 animate-spin"></i> <span>Erschaffe...</span>';
        feather.replace();
        
        try {
            const worldData = {
                world_name: document.getElementById('new-world-name').value,
                lore: document.getElementById('new-world-lore').value,
                char_name: document.getElementById('new-char-name').value,
                backstory: document.getElementById('new-char-backstory').value,
                attributes: attributePoints
            };
            
            if (!worldData.world_name || !worldData.lore || !worldData.char_name || !worldData.backstory) {
                throw new Error("Alle Felder für die neue Welt sind erforderlich.");
            }
            
            const data = await apiRequest('/worlds/create', 'POST', worldData);
            showNotification('Welt erfolgreich erstellt!', 'success');
            startGame(data.world_id, data.player_id, worldData.world_name, data.initial_story);
            
        } catch (error) {
            createError.textContent = `Fehler: ${error.message}`;
            showNotification(`Fehler beim Erstellen der Welt: ${error.message}`, 'error');
        } finally {
            createWorldButton.disabled = false;
            createWorldButton.innerHTML = originalText;
            feather.replace();
        }
    }

    // --- Game Logic ---

    async function startGame(worldId, playerId, worldName, initialStory = null) {
        activeWorld.world_id = worldId;
        activeWorld.player_id = playerId;
        gameTitle.textContent = `Abenteuer in: ${worldName}`;
        navWorldName.textContent = `Welt: ${worldName}`;
        showScreen('game');
        chatContainer.innerHTML = '';

        if (initialStory) {
            displayMessage(initialStory, 'story');
            // Aktiviere die Eingabemaske nach dem ersten Story-Text
            gameInputArea.classList.add('active');
            commandInput.focus();
        } else {
            displayMessage('Lade Spielzusammenfassung...', 'story');
            try {
                const data = await apiRequest(`/load_game_summary?world_id=${worldId}&player_id=${playerId}`);
                chatContainer.innerHTML = '';
                displayMessage(data.response || data.summary || 'Willkommen zurück! Was möchtest du tun?', 'story');
                // Aktiviere die Eingabemaske nach dem Laden
                gameInputArea.classList.add('active');
                commandInput.focus();
            } catch (error) {
                chatContainer.innerHTML = '';
                displayMessage(`Fehler beim Laden der Zusammenfassung: ${error.message}`, 'story');
                // Aktiviere die Eingabemaske auch bei Fehlern
                gameInputArea.classList.add('active');
                commandInput.focus();
            }
        }
    }

    async function sendCommand() {
        const command = commandInput.value.trim();
        if (!command || !authToken || !activeWorld.world_id) return;

        displayMessage(command, 'player');
        commandInput.value = '';
        commandInput.disabled = true;
        sendButton.disabled = true;
        
        sendButton.innerHTML = '<i data-feather="loader" class="w-5 h-5 animate-spin"></i>';
        feather.replace();

        try {
            const data = await apiRequest('/command', 'POST', {
                command,
                world_id: activeWorld.world_id,
                player_id: activeWorld.player_id
            });
            
            if (!data.response) {
                throw new Error('Keine Antwort vom Server erhalten.');
            }

            // Speichere die letzte AI-Antwort für Korrekturen
            lastAIResponse = {
                response: data.response,
                event_type: data.event_type || 'STORY',
                raw_data: data
            };

            if (data.event_type === 'STORY') {
                displayMessage(data.response, 'story');
            } else if (data.event_type === 'LEVEL_UP') {
                displayMessage(data.response, 'event');
            } else {
                displayMessage(data.response, 'story');
            }

        } catch (error) {
            displayMessage(`Fehler: ${error.message}`, 'story');
            showNotification(`Fehler beim Senden des Befehls: ${error.message}`, 'error');
        } finally {
            commandInput.disabled = false;
            sendButton.disabled = false;
            sendButton.innerHTML = '<i data-feather="send" class="w-5 h-5"></i>';
            feather.replace();
            commandInput.focus();
        }
    }

    // --- Correction Functions ---

    async function openCorrectionModal() {
        if (!activeWorld.world_id || !activeWorld.player_id) {
            showNotification('Keine aktive Spielwelt verfügbar.', 'error');
            return;
        }

        try {
            // Lade das letzte Event aus der Datenbank
            showNotification('Lade letztes Event...', 'info');
            
            const data = await apiRequest(`/get_last_event?world_id=${activeWorld.world_id}&player_id=${activeWorld.player_id}`);
            
            if (!data || !data.event) {
                showNotification('Kein Event zum Korrigieren verfügbar.', 'error');
                return;
            }

            const event = data.event;
            
            // Fülle die Textfelder mit den Event-Daten
            narrativeTextarea.value = event.ai_output || '';
            jsonTextarea.value = event.extracted_commands_json || '[]';

            showModal(correctionModal);
            showNotification('Event-Daten geladen.', 'success');
            
        } catch (error) {
            showNotification(`Fehler beim Laden des Events: ${error.message}`, 'error');
        }
    }

    async function saveCorrectionData() {
        try {
            const narrativeText = narrativeTextarea.value.trim();
            const jsonText = jsonTextarea.value.trim();

            if (!narrativeText) {
                showNotification('Erzähltext darf nicht leer sein.', 'error');
                return;
            }

            // Validiere JSON
            let jsonData;
            try {
                jsonData = JSON.parse(jsonText);
            } catch (error) {
                showNotification('Ungültiges JSON-Format in extracted_commands_json.', 'error');
                return;
            }

            // Sende Korrektur an Backend
            const correctionData = {
                world_id: activeWorld.world_id,
                player_id: activeWorld.player_id,
                ai_output: narrativeText,
                extracted_commands_json: jsonText
            };

            await apiRequest('/save_event_correction', 'POST', correctionData);

            // Aktualisiere auch die Anzeige im Chat (falls die Korrektur den aktuell sichtbaren Text betrifft)
            const storyMessages = chatContainer.querySelectorAll('.story-text');
            if (storyMessages.length > 0) {
                const lastStoryMessage = storyMessages[storyMessages.length - 1];
                // Markdown-ähnliches Parsing für Fett und Kursiv
                function escapeHTML(str) {
                    return str
                        .replace(/&/g, "&amp;")
                        .replace(/</g, "&lt;")
                        .replace(/>/g, "&gt;")
                        .replace(/"/g, "&quot;")
                        .replace(/'/g, "&#39;");
                }
                let processedContent = narrativeText;
                // Escape HTML first, then parse Markdown-like syntax
                processedContent = processedContent.split('\n').map(p => escapeHTML(p)).join('\n');
                processedContent = processedContent.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>');
                processedContent = processedContent.replace(/\*(.*?)\*/g, '<i>$1</i>');
                lastStoryMessage.innerHTML = processedContent.split('\n').map(p => `<p>${p}</p>`).join('');
            }

            hideModal(correctionModal);
            showNotification('Event-Korrektur erfolgreich gespeichert!', 'success');

        } catch (error) {
            showNotification(`Fehler beim Speichern der Korrektur: ${error.message}`, 'error');
        }
    }

    // --- Event Listeners ---
    
    // Login
    loginButton.addEventListener('click', handleLogin);
    passwordInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleLogin();
    });
    
    // Navigation
    profileBtn.addEventListener('click', () => showModal(profileModal));
    logoutBtn.addEventListener('click', handleLogout);
    
    // Profile modal
    closeProfileModal.addEventListener('click', () => hideModal(profileModal));
    changePasswordBtn.addEventListener('click', () => {
        hideModal(profileModal);
        showModal(passwordModal);
    });
    
    // Password modal
    closePasswordModal.addEventListener('click', () => hideModal(passwordModal));
    cancelPasswordBtn.addEventListener('click', () => hideModal(passwordModal));
    savePasswordBtn.addEventListener('click', handlePasswordChange);
    
    // World creation
    showCreateWorldBtn.addEventListener('click', () => {
        setupAttributeAllocator();
        showScreen('createWorld');
    });
    cancelCreateBtn.addEventListener('click', () => showScreen('worldSelection'));
    createWorldButton.addEventListener('click', handleCreateWorld);
    
    // Attribute allocation
    document.getElementById('attribute-allocator').addEventListener('click', (e) => {
        if (e.target.closest('.attr-btn')) {
            const btn = e.target.closest('.attr-btn');
            const attr = btn.dataset.attr;
            const delta = parseInt(btn.dataset.delta);
            const newValue = attributePoints[attr] + delta;
            
            if (newValue >= MIN_SCORE && newValue <= MAX_SCORE) {
                attributePoints[attr] = newValue;
                document.getElementById(`val-${attr}`).textContent = newValue;
                updatePointsDisplay();
            }
        }
    });
    
    // Game
    sendButton.addEventListener('click', sendCommand);
    commandInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendCommand();
    });
    
    // Correction modal
    correctLastBtn.addEventListener('click', openCorrectionModal);
    closeCorrectionModal.addEventListener('click', () => hideModal(correctionModal));
    cancelCorrectionBtn.addEventListener('click', () => hideModal(correctionModal));
    saveCorrectionBtn.addEventListener('click', saveCorrectionData);
    
    // Story Export modal
    storyExportBtn.addEventListener('click', () => {
        showModal(storyExportModal);
        loadExportWorldOptions();
    });
    closeStoryExportModal.addEventListener('click', () => hideModal(storyExportModal));
    cancelExportBtn.addEventListener('click', () => hideModal(storyExportModal));
    startExportBtn.addEventListener('click', startStoryExport);
    
    // Close modals on outside click
    [profileModal, passwordModal, correctionModal, storyExportModal].forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                hideModal(modal);
            }
        });
    });

    // --- Initialisierung ---
    
    // Stelle sicher, dass beim ersten Laden nur der Login-Screen sichtbar ist
    Object.values(screens).forEach(screen => screen.classList.remove('active'));
    gameInputArea.classList.remove('active');
    
    const savedToken = localStorage.getItem('lastStrawberryToken');
    if (savedToken) {
        authToken = savedToken;
        loadUserProfile().then(() => {
            showScreen('worldSelection');
            loadWorlds();
        }).catch(() => {
            // Token invalid, show login
            handleLogout();
        });
    } else {
        showScreen('login');
    }

    // --- Story Export Funktionen ---
    
    async function loadExportWorldOptions() {
        try {
            // Populate world selection dropdown - for now just show current world
            if (activeWorld.world_id) {
                exportWorldSelect.innerHTML = '<option value="">Aktuelle Welt</option>';
            } else {
                exportWorldSelect.innerHTML = '<option value="">Keine aktive Welt</option>';
            }
        } catch (error) {
            console.error('Error loading export world options:', error);
        }
    }
    
    async function startStoryExport() {
        const format = exportFormatSelect.value;
        const worldId = activeWorld.world_id;
        
        if (!worldId) {
            showErrorNotification('Keine aktive Welt zum Exportieren.');
            return;
        }
        
        try {
            startExportBtn.disabled = true;
            startExportBtn.innerHTML = '<i data-feather="loader" class="w-4 h-4 mr-2 animate-spin"></i>Exportiere...';
            feather.replace();
            
            const response = await fetch(`${API_BASE_URL}/export-story/${worldId}?format=${format}`, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${authToken}`,
                    'Content-Type': 'application/json',
                }
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Export fehlgeschlagen');
            }

            // Get filename from response headers or create default
            let filename = `story_export_${worldId}.${format}`;
            const contentDisposition = response.headers.get('content-disposition');
            if (contentDisposition && contentDisposition.includes('filename=')) {
                filename = contentDisposition.split('filename=')[1].replace(/"/g, '');
            }

            // Download the file
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            showSuccessNotification('Story erfolgreich exportiert!');
            hideModal(storyExportModal);

        } catch (error) {
            console.error('Story export error:', error);
            showErrorNotification(`Export-Fehler: ${error.message}`);
        } finally {
            startExportBtn.disabled = false;
            startExportBtn.innerHTML = '<i data-feather="download" class="w-4 h-4 mr-2"></i>Export starten';
            feather.replace();
        }
    }
    
    // Initialize feather icons
    feather.replace();
});
