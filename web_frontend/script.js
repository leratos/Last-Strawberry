// web_frontend/script.js

document.addEventListener("DOMContentLoaded", () => {
    const API_BASE_URL = window.LastStrawberryConfig?.API_BASE_URL || "http://127.0.0.1:8002";
    const TOKEN_STORAGE_KEY = window.LastStrawberryConfig?.TOKEN_STORAGE_KEY || "lastStrawberryV2Token";
    const ATTRIBUTES = ["Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma", "Perception"];
    const POINT_BUY_BUDGET = 75;
    const MIN_SCORE = 8;
    const MAX_SCORE = 15;

    const screens = {
        login: document.getElementById("login-screen"),
        worldSelection: document.getElementById("world-selection-screen"),
        createWorld: document.getElementById("create-world-screen"),
        game: document.getElementById("game-screen"),
    };

    const navbar = document.getElementById("navbar");
    const navWorldName = document.getElementById("nav-world-name");
    const profileBtn = document.getElementById("profile-btn");
    const storyExportBtn = document.getElementById("story-export-btn");
    const adminLink = document.getElementById("admin-link");
    const logoutBtn = document.getElementById("logout-btn");

    const usernameInput = document.getElementById("username");
    const passwordInput = document.getElementById("password");
    const loginButton = document.getElementById("login-button");
    const loginError = document.getElementById("login-error");

    const worldListContainer = document.getElementById("world-list");
    const showCreateWorldBtn = document.getElementById("show-create-world-btn");
    const createWorldButton = document.getElementById("create-world-button");
    const cancelCreateBtn = document.getElementById("cancel-create-btn");
    const createError = document.getElementById("create-error");

    const gameTitle = document.getElementById("game-title");
    const chatContainer = document.getElementById("chat-container");
    const gameInputArea = document.getElementById("game-input-area");
    const commandInput = document.getElementById("command-input");
    const sendButton = document.getElementById("send-button");
    const correctLastBtn = document.getElementById("correct-last-btn");

    const attributeAllocator = document.getElementById("attribute-allocator");
    const attributesContainer = document.getElementById("attributes-container");
    const pointsDisplay = document.getElementById("points-display");

    let authToken = null;
    let currentUser = null;
    let activeWorld = { worldId: null, playerId: null, worldName: "" };
    let attributePoints = {};

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function decodeJwtPayload(token) {
        try {
            const parts = token.split(".");
            if (parts.length !== 3) {
                return null;
            }
            const payloadPart = parts[1];
            const normalized = payloadPart.replace(/-/g, "+").replace(/_/g, "/");
            const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
            const json = atob(padded);
            return JSON.parse(json);
        } catch (error) {
            console.error("Failed to decode JWT payload:", error);
            return null;
        }
    }

    function stableUserIdFromUsername(username) {
        let hash = 2166136261;
        for (let i = 0; i < username.length; i += 1) {
            hash ^= username.charCodeAt(i);
            hash = Math.imul(hash, 16777619);
        }
        const positive = Math.abs(hash | 0);
        return (positive % 2000000000) + 1;
    }

    function resolveLoginUserId(username, passwordValue) {
        const numericCandidate = Number.parseInt(passwordValue, 10);
        if (Number.isInteger(numericCandidate) && numericCandidate > 0) {
            return numericCandidate;
        }
        return stableUserIdFromUsername(username);
    }

    function parseCurrentUserFromToken(token) {
        const payload = decodeJwtPayload(token);
        if (!payload || payload.sub === undefined) {
            return null;
        }
        const userId = Number.parseInt(String(payload.sub), 10);
        if (!Number.isInteger(userId) || userId <= 0) {
            return null;
        }
        return {
            user_id: userId,
            username: String(payload.username || "player"),
            roles: ["player"],
        };
    }

    function showScreen(screenName) {
        Object.values(screens).forEach((screen) => screen.classList.remove("active"));
        if (screens[screenName]) {
            screens[screenName].classList.add("active");
        }

        if (screenName === "login") {
            navbar.classList.add("hidden");
            gameInputArea.classList.remove("active");
            return;
        }

        navbar.classList.remove("hidden");
        if (screenName === "game" && activeWorld.worldId) {
            gameInputArea.classList.add("active");
        } else {
            gameInputArea.classList.remove("active");
        }
    }

    function setLoading(button, loading, loadingLabel) {
        if (!button) {
            return;
        }
        if (loading) {
            button.disabled = true;
            button.dataset.originalHtml = button.innerHTML;
            button.innerHTML = `<span class="flex items-center justify-center space-x-2"><i data-feather="loader" class="w-5 h-5 animate-spin"></i><span>${escapeHtml(loadingLabel)}</span></span>`;
            feather.replace();
            return;
        }

        button.disabled = false;
        if (button.dataset.originalHtml) {
            button.innerHTML = button.dataset.originalHtml;
            delete button.dataset.originalHtml;
            feather.replace();
        }
    }

    function showNotification(message, type = "info") {
        const toast = document.createElement("div");
        toast.className = "fixed top-4 right-4 z-50 px-5 py-3 rounded-lg shadow-lg text-white";

        if (type === "success") {
            toast.classList.add("bg-green-600");
        } else if (type === "error") {
            toast.classList.add("bg-red-600");
        } else {
            toast.classList.add("bg-blue-600");
        }

        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 3500);
    }

    async function apiRequest(path, options = {}) {
        const method = options.method || "GET";
        const body = options.body ?? null;
        const timeoutMs = window.LastStrawberryConfig?.REQUEST_TIMEOUT_MS || 30000;

        const headers = {
            Accept: "application/json",
        };
        if (body !== null) {
            headers["Content-Type"] = "application/json";
        }
        if (authToken) {
            headers.Authorization = `Bearer ${authToken}`;
        }

        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), timeoutMs);

        try {
            const response = await fetch(`${API_BASE_URL}${path}`, {
                method,
                headers,
                body: body === null ? null : JSON.stringify(body),
                mode: "cors",
                signal: controller.signal,
            });

            if (!response.ok) {
                let detail = `HTTP ${response.status}`;
                try {
                    const payload = await response.json();
                    if (payload && typeof payload.detail === "string") {
                        detail = payload.detail;
                    }
                } catch (_error) {
                    // ignore parse failure
                }
                throw new Error(detail);
            }

            const contentType = response.headers.get("content-type") || "";
            if (!contentType.includes("application/json")) {
                return null;
            }
            return await response.json();
        } catch (error) {
            if (error.name === "AbortError") {
                throw new Error("Request timeout.");
            }
            throw error;
        } finally {
            clearTimeout(timeout);
        }
    }

    function displayMessage(content, type = "story") {
        const wrapper = document.createElement("div");
        wrapper.className = "mb-4 p-4 rounded-lg";

        if (type === "player") {
            wrapper.classList.add("text-blue-300", "bg-blue-900", "bg-opacity-30", "font-semibold");
        } else if (type === "event") {
            wrapper.classList.add("text-yellow-300", "bg-yellow-900", "bg-opacity-30");
        } else {
            wrapper.classList.add("text-gray-200", "bg-gray-800", "bg-opacity-50", "story-text");
        }

        const safeText = escapeHtml(content || "");
        wrapper.innerHTML = safeText
            .split("\n")
            .map((line) => `<p>${line}</p>`)
            .join("");

        chatContainer.appendChild(wrapper);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function resetActiveWorld() {
        activeWorld = { worldId: null, playerId: null, worldName: "" };
        navWorldName.textContent = "";
        gameTitle.textContent = "Last-Strawberry Adventure";
        chatContainer.innerHTML = "";
        gameInputArea.classList.remove("active");
    }

    function clearCreateWorldForm() {
        const ids = [
            "new-world-name",
            "new-world-lore",
            "new-char-name",
            "new-char-backstory",
        ];
        ids.forEach((id) => {
            const el = document.getElementById(id);
            if (el) {
                el.value = "";
            }
        });
        createError.textContent = "";
        setupAttributeAllocator();
    }

    function buildWorldDescription() {
        const lore = (document.getElementById("new-world-lore")?.value || "").trim();
        const charName = (document.getElementById("new-char-name")?.value || "").trim();
        const backstory = (document.getElementById("new-char-backstory")?.value || "").trim();
        const attrs = ATTRIBUTES.map((attr) => `${attr}:${attributePoints[attr]}`).join(", ");
        return [
            lore ? `Lore: ${lore}` : "",
            charName ? `Character: ${charName}` : "",
            backstory ? `Backstory: ${backstory}` : "",
            `Attributes: ${attrs}`,
        ]
            .filter(Boolean)
            .join("\n");
    }

    function setupAttributeAllocator() {
        attributePoints = {};
        ATTRIBUTES.forEach((attr) => {
            attributePoints[attr] = 10;
        });

        attributesContainer.innerHTML = "";
        ATTRIBUTES.forEach((attr) => {
            const row = document.createElement("div");
            row.className = "glass-card p-4 rounded-lg";
            row.innerHTML = `
                <div class="flex items-center justify-between mb-2">
                    <span class="font-medium text-white">${escapeHtml(attr)}</span>
                    <span id="val-${escapeHtml(attr)}" class="text-lg font-bold text-purple-300">${attributePoints[attr]}</span>
                </div>
                <div class="flex space-x-2">
                    <button class="attr-btn btn-secondary px-3 py-1 rounded" data-attr="${escapeHtml(attr)}" data-delta="-1">-</button>
                    <button class="attr-btn btn-primary px-3 py-1 rounded flex-1" data-attr="${escapeHtml(attr)}" data-delta="1">+</button>
                </div>
            `;
            attributesContainer.appendChild(row);
        });
        updatePointsDisplay();
        feather.replace();
    }

    function updatePointsDisplay() {
        const spent = Object.values(attributePoints).reduce((sum, value) => sum + Number(value), 0);
        const remaining = POINT_BUY_BUDGET - spent;
        pointsDisplay.textContent = `Remaining points: ${remaining}`;
        pointsDisplay.className = remaining === 0
            ? "text-center font-bold mb-6 text-lg text-green-400"
            : "text-center font-bold mb-6 text-lg text-yellow-400";
    }

    function renderWorlds(worlds) {
        worldListContainer.innerHTML = "";

        if (!Array.isArray(worlds) || worlds.length === 0) {
            worldListContainer.innerHTML = `
                <div class="text-center py-8">
                    <i data-feather="globe" class="w-12 h-12 mx-auto text-gray-500 mb-4"></i>
                    <p class="text-gray-300">No worlds yet.</p>
                    <p class="text-gray-500 text-sm mt-1">Create your first world to begin.</p>
                </div>
            `;
            feather.replace();
            return;
        }

        worlds.forEach((world) => {
            const card = document.createElement("div");
            card.className = "glass-card p-4 rounded-lg hover:bg-opacity-80 transition-all cursor-pointer";
            const createdAt = world.created_at ? new Date(world.created_at).toLocaleString() : "n/a";
            card.innerHTML = `
                <div class="flex justify-between items-center">
                    <div class="flex-1">
                        <h4 class="font-semibold text-white">${escapeHtml(world.name)}</h4>
                        <p class="text-sm text-gray-400 mt-1">${escapeHtml(world.description || "No description")}</p>
                        <p class="text-xs text-gray-500 mt-1">Created: ${escapeHtml(createdAt)}</p>
                    </div>
                    <i data-feather="play-circle" class="w-5 h-5 text-purple-400"></i>
                </div>
            `;
            card.addEventListener("click", () => startGame(world));
            worldListContainer.appendChild(card);
        });
        feather.replace();
    }

    async function loadWorlds() {
        const worlds = await apiRequest("/v2/worlds");
        renderWorlds(worlds || []);
    }

    async function handleLogin() {
        loginError.textContent = "";
        const username = (usernameInput.value || "").trim();
        if (!username) {
            loginError.textContent = "Username is required.";
            return;
        }

        setLoading(loginButton, true, "Signing in");
        try {
            const userId = resolveLoginUserId(username, passwordInput.value || "");
            const result = await apiRequest("/v2/auth/login", {
                method: "POST",
                body: { user_id: userId, username },
            });
            authToken = result.access_token;
            localStorage.setItem(TOKEN_STORAGE_KEY, authToken);
            currentUser = parseCurrentUserFromToken(authToken) || { user_id: userId, username, roles: ["player"] };
            await loadWorlds();
            showScreen("worldSelection");
            showNotification("Login successful.", "success");
        } catch (error) {
            loginError.textContent = error.message;
            showNotification(`Login failed: ${error.message}`, "error");
        } finally {
            setLoading(loginButton, false, "");
        }
    }

    function handleLogout() {
        authToken = null;
        currentUser = null;
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        resetActiveWorld();
        showScreen("login");
        showNotification("Logged out.", "info");
    }

    async function handleCreateWorld() {
        createError.textContent = "";
        const name = (document.getElementById("new-world-name")?.value || "").trim();
        if (!name) {
            createError.textContent = "World name is required.";
            return;
        }

        setLoading(createWorldButton, true, "Creating");
        try {
            const description = buildWorldDescription();
            const world = await apiRequest("/v2/worlds", {
                method: "POST",
                body: { name, description },
            });
            clearCreateWorldForm();
            await loadWorlds();
            showScreen("worldSelection");
            showNotification("World created.", "success");
            await startGame(world);
        } catch (error) {
            createError.textContent = error.message;
            showNotification(`Create world failed: ${error.message}`, "error");
        } finally {
            setLoading(createWorldButton, false, "");
        }
    }

    async function startGame(world) {
        activeWorld = {
            worldId: Number(world.id),
            playerId: currentUser?.user_id || 1,
            worldName: world.name || "Unknown world",
        };
        gameTitle.textContent = `Adventure in: ${activeWorld.worldName}`;
        navWorldName.textContent = `World: ${activeWorld.worldName}`;
        chatContainer.innerHTML = "";
        showScreen("game");
        displayMessage(`Loaded world "${activeWorld.worldName}".`, "event");

        try {
            const turns = await apiRequest(`/v2/worlds/${activeWorld.worldId}/turns?limit=30`);
            const orderedTurns = Array.isArray(turns) ? [...turns].reverse() : [];
            if (orderedTurns.length === 0) {
                displayMessage("No turns yet. Start with your first command.", "story");
            } else {
                orderedTurns.forEach((turn) => {
                    displayMessage(turn.player_command, "player");
                    displayMessage(turn.narrative, "story");
                });
            }
        } catch (error) {
            displayMessage(`Could not load turn history: ${error.message}`, "event");
        }

        commandInput.focus();
    }

    async function sendCommand() {
        const command = (commandInput.value || "").trim();
        if (!command || !activeWorld.worldId || !activeWorld.playerId) {
            return;
        }

        displayMessage(command, "player");
        commandInput.value = "";
        commandInput.disabled = true;
        setLoading(sendButton, true, "Sending");

        try {
            const response = await apiRequest("/v2/game/turn", {
                method: "POST",
                body: {
                    world_id: activeWorld.worldId,
                    player_id: activeWorld.playerId,
                    player_command: command,
                },
            });
            displayMessage(response?.narrative || "No narrative returned.", "story");
        } catch (error) {
            displayMessage(`Error: ${error.message}`, "event");
        } finally {
            commandInput.disabled = false;
            setLoading(sendButton, false, "");
            commandInput.focus();
        }
    }

    function hideUnsupportedControls() {
        [profileBtn, storyExportBtn, correctLastBtn, adminLink].forEach((el) => {
            if (el) {
                el.classList.add("hidden");
            }
        });
    }

    function restoreSession() {
        const token = localStorage.getItem(TOKEN_STORAGE_KEY);
        if (!token) {
            return false;
        }
        const user = parseCurrentUserFromToken(token);
        if (!user) {
            localStorage.removeItem(TOKEN_STORAGE_KEY);
            return false;
        }
        authToken = token;
        currentUser = user;
        return true;
    }

    loginButton.addEventListener("click", handleLogin);
    passwordInput.addEventListener("keypress", (event) => {
        if (event.key === "Enter") {
            handleLogin();
        }
    });
    usernameInput.addEventListener("keypress", (event) => {
        if (event.key === "Enter") {
            handleLogin();
        }
    });
    logoutBtn.addEventListener("click", handleLogout);

    showCreateWorldBtn.addEventListener("click", () => {
        clearCreateWorldForm();
        showScreen("createWorld");
    });
    cancelCreateBtn.addEventListener("click", async () => {
        showScreen("worldSelection");
        await loadWorlds();
    });
    createWorldButton.addEventListener("click", handleCreateWorld);

    attributeAllocator.addEventListener("click", (event) => {
        const button = event.target.closest(".attr-btn");
        if (!button) {
            return;
        }
        const attr = button.dataset.attr;
        const delta = Number.parseInt(button.dataset.delta || "0", 10);
        const current = Number(attributePoints[attr] || 10);
        const next = current + delta;
        if (next < MIN_SCORE || next > MAX_SCORE) {
            return;
        }
        attributePoints[attr] = next;
        const valueEl = document.getElementById(`val-${attr}`);
        if (valueEl) {
            valueEl.textContent = String(next);
        }
        updatePointsDisplay();
    });

    sendButton.addEventListener("click", sendCommand);
    commandInput.addEventListener("keypress", (event) => {
        if (event.key === "Enter") {
            sendCommand();
        }
    });

    hideUnsupportedControls();
    setupAttributeAllocator();
    resetActiveWorld();

    if (restoreSession()) {
        loadWorlds()
            .then(() => showScreen("worldSelection"))
            .catch((error) => {
                console.error("Session restore failed:", error);
                handleLogout();
            });
    } else {
        showScreen("login");
    }

    feather.replace();
});
