// web_frontend/config.js
// Konfiguration für Frontend API URLs

// Automatische URL-Erkennung basierend auf Hostname
function getApiBaseUrl() {
    const hostname = window.location.hostname;
    const protocol = window.location.protocol;
    
    console.log(`🔍 Frontend läuft auf: ${protocol}//${hostname}`);
    
    // ENTWICKLUNG: Lokale IPs oder localhost
    if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname.startsWith('192.168.')) {
        console.log('📍 Lokale Entwicklung erkannt - verwende lokalen Backend-Port');
        return 'http://127.0.0.1:8001';
    }
    
    // PRODUKTION: last-strawberry.com Domain
    if (hostname.includes('last-strawberry')) {
        // Prüfe, ob Backend auf Port 8001 läuft (während Entwicklung)
        const isDevMode = window.location.search.includes('dev=true') || 
                         localStorage.getItem('dev-mode') === 'true';
        
        if (isDevMode) {
            console.log('🛠️ Dev-Modus auf Produktionsserver - verwende direkten Backend-Port');
            return 'http://127.0.0.1:8001';
        }
        
        console.log('🌐 Produktionsumgebung erkannt - verwende Nginx-Proxy');
        // Nutze die gleiche URL wie die Webseite (Nginx @backend fallback)
        return `${protocol}//${hostname}`;
    }
    
    // Standard-Fallback für Entwicklung
    console.log('⚠️ Unbekannte Umgebung - verwende lokalen Fallback');
    return 'http://127.0.0.1:8001';
}

// Server-Konfiguration
window.LastStrawberryConfig = {
    API_BASE_URL: getApiBaseUrl(),
    PRODUCTION_API_URL: `${window.location.protocol}//${window.location.hostname}`,
    LOCAL_API_URL: 'http://127.0.0.1:8001',
    
    // Manuelle Override-Funktionen für Debugging
    setDevMode: function(enabled) {
        localStorage.setItem('dev-mode', enabled.toString());
        console.log(`🔧 Dev-Modus ${enabled ? 'aktiviert' : 'deaktiviert'} - Seite neu laden für Änderung`);
    },
    
    forceLocalBackend: function() {
        this.API_BASE_URL = this.LOCAL_API_URL;
        console.log('🔧 Backend-URL manuell auf lokal gesetzt:', this.API_BASE_URL);
        return this.API_BASE_URL;
    },
    
    forceProductionBackend: function() {
        this.API_BASE_URL = this.PRODUCTION_API_URL;
        console.log('🔧 Backend-URL manuell auf Produktion gesetzt:', this.API_BASE_URL);
        return this.API_BASE_URL;
    },
    
    getCurrentConfig: function() {
        console.log('📋 Aktuelle Konfiguration:');
        console.log('  Frontend URL:', window.location.href);
        console.log('  Backend URL:', this.API_BASE_URL);
        console.log('  Dev-Modus:', localStorage.getItem('dev-mode'));
        return {
            frontend: window.location.href,
            backend: this.API_BASE_URL,
            devMode: localStorage.getItem('dev-mode')
        };
    },
    
    // Weitere Konfigurationen
    PING_TIMEOUT: 3000,
    WARMUP_THRESHOLD: 5 * 60 * 1000, // 5 Minuten
    MAX_WARMUP_RETRIES: 5,
    WARMUP_RETRY_DELAY: 60000 // 60 Sekunden
};

// Fallback API URLs - verschiedene Optionen probieren
window.LastStrawberryConfig.fallbackUrls = [
    `${window.location.protocol}//${window.location.hostname}`,  // Nginx @backend
    'http://127.0.0.1:8001'  // Entwicklung
];

console.log('Last-Strawberry Config loaded:', window.LastStrawberryConfig);
console.log('API URL Configured:', window.LastStrawberryConfig.API_BASE_URL);
console.log('Fallback URLs:', window.LastStrawberryConfig.fallbackUrls);

// Test-Funktion für API-Erreichbarkeit
window.testApiConnection = async function() {
    console.log('🧪 Testing API connection...');
    
    const testUrls = [
        window.LastStrawberryConfig.API_BASE_URL + '/ping',
        window.LastStrawberryConfig.API_BASE_URL + '/health',
        'https://last-strawberry.com/ping',
        'https://last-strawberry.com/health'
    ];
    
    for (const url of testUrls) {
        try {
            console.log(`🔍 Testing: ${url}`);
            const response = await fetch(url, {
                method: 'GET',
                mode: 'cors',
                credentials: 'same-origin'
            });
            console.log(`✅ ${url} -> ${response.status} ${response.statusText}`);
            
            if (response.ok) {
                const data = await response.json();
                console.log(`📄 Response:`, data);
            }
        } catch (error) {
            console.error(`❌ ${url} failed:`, error);
        }
    }
};
