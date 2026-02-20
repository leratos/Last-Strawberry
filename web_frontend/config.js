// web_frontend/config.js
// Runtime config for the V2 frontend.

function getApiBaseUrl() {
    const hostname = window.location.hostname;
    const protocol = window.location.protocol;

    if (hostname === "localhost" || hostname === "127.0.0.1" || hostname.startsWith("192.168.")) {
        return "http://127.0.0.1:8002";
    }

    if (hostname.includes("last-strawberry")) {
        return `${protocol}//${hostname}`;
    }

    return "http://127.0.0.1:8002";
}

window.LastStrawberryConfig = {
    API_BASE_URL: getApiBaseUrl(),
    HEALTH_PATH: "/v2/health",
    REQUEST_TIMEOUT_MS: 30000,
    TOKEN_STORAGE_KEY: "lastStrawberryV2Token",
};

window.testApiConnection = async function testApiConnection() {
    const url = `${window.LastStrawberryConfig.API_BASE_URL}${window.LastStrawberryConfig.HEALTH_PATH}`;
    try {
        const response = await fetch(url, {
            method: "GET",
            mode: "cors",
            credentials: "omit",
        });
        const body = await response.json();
        console.log("API test success:", response.status, body);
        return { ok: response.ok, status: response.status, body };
    } catch (error) {
        console.error("API test failed:", error);
        return { ok: false, status: 0, error: String(error) };
    }
};
