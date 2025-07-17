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
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');
    const loginButton = document.getElementById('login-button');
    const loginError = document.getElementById('login-error');
    const worldListContainer = document.getElementById('world-list');
    const showCreateWorldBtn = document.getElementById('show-create-world-btn');
    const createWorldButton = document.getElementById('create-world-button');
    const cancelCreateBtn = document.getElementById('cancel-create-btn');
    
    const gameTitle = document.getElementById('game-title');
    const chatContainer = document.getElementById('chat-container');
    const commandInput = document.getElementById('command-input');
    const sendButton = document.getElementById('send-button');

    const correctLastBtn = document.getElementById('correct-last-btn');

    // --- Anwendungs-Zustand ---
    let authToken = null;
    let activeWorld = { world_id: null, player_id: null };
    let attributePoints = {};

    // --- Funktionen ---

    function showScreen(screenName) {
        Object.values(screens).forEach(screen => screen.classList.remove('active'));
        if (screens[screenName]) {
            screens[screenName].classList.add('active');
        }
    }

    function displayMessage(htmlContent, type = 'story') {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'mb-4';

        // Markdown-ähnliches Parsing für Fett und Kursiv
        let processedContent = htmlContent.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>');
        processedContent = processedContent.replace(/\*(.*?)\*/g, '<i>$1</i>');

        if (type === 'story') {
            messageDiv.className += ' story-text text-gray-300';
            messageDiv.innerHTML = processedContent.split('\n').map(p => `<p>${p}</p>`).join('');
        } else if (type === 'player') {
            messageDiv.className += ' player-input-text text-blue-400 font-semibold';
            messageDiv.textContent = `> ${htmlContent}`;
        } else if (type === 'event') {
            messageDiv.className += ' event-text text-yellow-300 font-bold text-center py-2';
            messageDiv.innerHTML = `--- ${processedContent} ---`;
        }
        chatContainer.appendChild(messageDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    async function handleLogin() {
        loginError.textContent = '';
        loginButton.disabled = true;
        loginButton.textContent = 'Melde an...';

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
            await loadWorlds();
            showScreen('worldSelection');
        } catch (error) {
            loginError.textContent = `Fehler: ${error.message}`;
        } finally {
            loginButton.disabled = false;
            loginButton.textContent = 'Anmelden';
        }
    }

    async function loadWorlds() {
        try {
            const response = await fetch(`${API_BASE_URL}/worlds`, { headers: { 'Authorization': `Bearer ${authToken}` } });
            if (!response.ok) throw new Error('Welten konnten nicht geladen werden.');
            const data = await response.json();
            worldListContainer.innerHTML = '';
            if (data.worlds.length === 0) {
                worldListContainer.innerHTML = '<p class="text-center text-gray-400">Noch keine Welten vorhanden. Erstelle eine neue!</p>';
            } else {
                data.worlds.forEach(world => {
                    const button = document.createElement('button');
                    button.className = 'w-full px-4 py-2 text-left text-white bg-gray-700 rounded-md hover:bg-gray-600 transition-colors';
                    button.textContent = `Welt: ${world.world_name} (Charakter: ${world.player_name})`;
                    button.onclick = () => startGame(world.world_id, world.player_id, world.world_name);
                    worldListContainer.appendChild(button);
                });
            }
        } catch (error) {
            worldListContainer.innerHTML = `<p class="text-red-400 text-center">${error.message}</p>`;
        }
    }

    function setupAttributeAllocator() {
        const container = document.getElementById('attributes-container');
        container.innerHTML = '';
        attributePoints = {};
        ATTRIBUTES.forEach(attr => {
            attributePoints[attr] = 10;
            const attrDiv = document.createElement('div');
            attrDiv.className = 'flex items-center justify-between';
            attrDiv.innerHTML = `
                <label class="font-medium">${attr}</label>
                <div class="flex items-center space-x-2">
                    <button data-attr="${attr}" data-delta="-1" class="attr-btn px-2 py-0.5 bg-gray-600 rounded">-</button>
                    <span id="val-${attr}" class="w-8 text-center font-bold">10</span>
                    <button data-attr="${attr}" data-delta="1" class="attr-btn px-2 py-0.5 bg-gray-600 rounded">+</button>
                </div>
            `;
            container.appendChild(attrDiv);
        });
        updatePointsDisplay();
    }

    function updatePointsDisplay() {
        const totalSpent = Object.values(attributePoints).reduce((sum, val) => sum + val, 0);
        const remaining = POINT_BUY_BUDGET - totalSpent;
        const display = document.getElementById('points-display');
        display.textContent = `Verbleibende Punkte: ${remaining}`;
        createWorldButton.disabled = remaining !== 0;
        display.className = `text-center font-bold my-2 ${remaining === 0 ? 'text-green-400' : 'text-red-400'}`;
    }

    document.getElementById('attribute-allocator').addEventListener('click', (e) => {
        if (e.target.classList.contains('attr-btn')) {
            const attr = e.target.dataset.attr;
            const delta = parseInt(e.target.dataset.delta);
            const newValue = attributePoints[attr] + delta;
            if (newValue >= MIN_SCORE && newValue <= MAX_SCORE) {
                attributePoints[attr] = newValue;
                document.getElementById(`val-${attr}`).textContent = newValue;
                updatePointsDisplay();
            }
        }
    });

    async function handleCreateWorld() {
        const createError = document.getElementById('create-error');
        createError.textContent = '';
        createWorldButton.disabled = true;
        createWorldButton.textContent = 'Erschaffe...';
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
            const response = await fetch(`${API_BASE_URL}/worlds/create`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authToken}` },
                body: JSON.stringify(worldData)
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'Welt konnte nicht erstellt werden.');
            
            startGame(data.world_id, data.player_id, worldData.world_name, data.initial_story);

        } catch (error) {
            createError.textContent = `Fehler: ${error.message}`;
        } finally {
            createWorldButton.disabled = false;
            createWorldButton.textContent = 'Neue Welt erschaffen';
        }
    }

    async function startGame(worldId, playerId, worldName, initialStory = null) {
        activeWorld.world_id = worldId;
        activeWorld.player_id = playerId;
        gameTitle.textContent = `Abenteuer in: ${worldName}`;
        showScreen('game');
        chatContainer.innerHTML = ''; // Chat leeren

        if (initialStory) {
            displayMessage(initialStory, 'story');
            commandInput.focus();
        } else {
            displayMessage('Lade Spielzusammenfassung...', 'story');
            try {
                const response = await fetch(`${API_BASE_URL}/load_game_summary?world_id=${worldId}&player_id=${playerId}`, {
                    headers: { 'Authorization': `Bearer ${authToken}` }
                });
                if (!response.ok) throw new Error('Spielzusammenfassung konnte nicht geladen werden.');
                const data = await response.json();
                chatContainer.innerHTML = ''; // Lade-Nachricht entfernen
                displayMessage(data.response, 'story');
                commandInput.focus();
            } catch (error) {
                displayMessage(`Fehler beim Laden des Spiels: ${error.message}`, 'story');
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

        try {
            const response = await fetch(`${API_BASE_URL}/command`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${authToken}` },
                body: JSON.stringify({ command, world_id: activeWorld.world_id, player_id: activeWorld.player_id })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'Server-Fehler.');

            // NEU: Auf verschiedene Event-Typen reagieren
            if (data.event_type === 'STORY') {
                displayMessage(data.response, 'story');
            } else if (data.event_type === 'LEVEL_UP') {
                displayMessage(data.message, 'event');
                // Zukünftig könnte hier ein UI-Dialog zur Attributsverteilung erscheinen
                displayMessage(data.response, 'story'); // Zeige die Story danach
            } else {
                displayMessage(data.response, 'story'); // Fallback
            }

        } catch (error) {
            displayMessage(`Fehler: ${error.message}`, 'story');
        } finally {
            commandInput.disabled = false;
            sendButton.disabled = false;
            commandInput.focus();
        }
    }

    // --- Event-Listener ---
    loginButton.addEventListener('click', handleLogin);
    passwordInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') handleLogin(); });
    
    showCreateWorldBtn.addEventListener('click', () => {
        setupAttributeAllocator();
        showScreen('createWorld');
    });
    cancelCreateBtn.addEventListener('click', () => showScreen('worldSelection'));
    createWorldButton.addEventListener('click', handleCreateWorld);

    sendButton.addEventListener('click', sendCommand);
    commandInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendCommand(); });

    // --- Initialisierung ---
    const savedToken = localStorage.getItem('lastStrawberryToken');
    if (savedToken) {
        authToken = savedToken;
        // Optional: Token validieren und direkt zur Weltenauswahl springen
        showScreen('worldSelection');
        loadWorlds();
    } else {
        showScreen('login');
    }
});