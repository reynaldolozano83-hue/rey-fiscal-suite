// SAT Express Frontend Logic with Stripe Integration
const API_BASE = window.location.origin + "/api";

let currentOrderUuid = null;
let currentRfc = "";
let currentDocType = "csf";

// Handle redirects and success checking on load
window.onload = async () => {
    const urlParams = new URLSearchParams(window.location.search);
    const status = urlParams.get("status");
    const orderUuid = urlParams.get("order_uuid");
    
    if (status === "success" && orderUuid) {
        currentOrderUuid = orderUuid;
        
        // Hide initial form, show progress loader screen
        switchScreen("step-form", "step-progress");
        
        // Trigger fulfillment backend logic
        try {
            const res = await fetch(`${API_BASE}/orders/${orderUuid}/trigger-fulfillment`);
            const data = await res.json();
            
            // Start polling the download status
            startPollingStatus();
        } catch(e) {
            console.error(e);
            alert("Error al procesar el pago con el servidor.");
            switchScreen("step-progress", "step-form");
        }
    } else if (status === "cancel") {
        alert("El pago fue cancelado. Intentalo de nuevo.");
        // Clear search query parameters
        window.history.replaceState({}, document.title, "/");
    }
};

function toggleDocType(type) {
    currentDocType = type;
    const csfLabel = document.getElementById("label-csf");
    const opinionLabel = document.getElementById("label-opinion");
    
    if (type === 'csf') {
        csfLabel.classList.add("active");
        opinionLabel.classList.remove("active");
    } else {
        opinionLabel.classList.add("active");
        csfLabel.classList.remove("active");
    }
}

async function startOrder() {
    const rfc = document.getElementById("user-rfc").value.trim();
    const ciec = document.getElementById("user-ciec").value.trim();
    const email = document.getElementById("user-email").value.trim();
    
    if (!rfc || rfc.length < 12) {
        alert("Por favor ingresa un RFC válido de 12 o 13 caracteres.");
        return;
    }
    if (!ciec) {
        alert("Por favor ingresa tu contraseña SAT (CIEC).");
        return;
    }
    if (!email || !email.includes("@")) {
        alert("Por favor ingresa un correo electrónico válido para enviar tu PDF.");
        return;
    }
    
    currentRfc = rfc.toUpperCase();
    
    // Create the order on the backend and redirect to Stripe
    try {
        const res = await fetch(`${API_BASE}/orders`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rfc: rfc, ciec: ciec, email: email, doc_type: currentDocType })
        });
        const data = await res.json();
        
        if (data.status === 'success') {
            currentOrderUuid = data.order_uuid;
            
            // Redirect to Stripe Checkout Session
            window.location.href = `${API_BASE}/checkout-session/${currentOrderUuid}`;
        } else {
            alert("Error al iniciar el trámite. Revisa tus datos.");
        }
    } catch(e) {
        console.error(e);
        alert("Error de conexión con el servidor.");
    }
}

let pollInterval = null;

function startPollingStatus() {
    let progressPercent = 25;
    const bar = document.getElementById("progress-bar");
    const title = document.getElementById("progress-title");
    const desc = document.getElementById("progress-desc");
    
    bar.style.width = `${progressPercent}%`;
    
    pollInterval = setInterval(async () => {
        try {
            const res = await fetch(`${API_BASE}/orders/${currentOrderUuid}/status`);
            const data = await res.json();
            
            if (data.download_status === 'success') {
                clearInterval(pollInterval);
                bar.style.width = "100%";
                title.innerText = "¡Trámite Listo!";
                desc.innerText = "Documento descargado con éxito.";
                
                setTimeout(() => {
                    // Populate success screen details
                    document.getElementById("success-rfc").innerText = currentRfc || "Consultado";
                    document.getElementById("success-doc").innerText = currentDocType === 'csf' ? "Constancia de Situación Fiscal" : "Opinión de Cumplimiento 32-D";
                    
                    switchScreen("step-progress", "step-success");
                    
                    // Clear search parameters from address bar cleanly
                    window.history.replaceState({}, document.title, "/");
                }, 800);
            } else if (data.download_status === 'failed') {
                clearInterval(pollInterval);
                alert("Error de consulta SAT: " + (data.error_message || "La contraseña o el RFC son incorrectos. Por favor, verifica tus datos de acceso en el SAT."));
                switchScreen("step-progress", "step-form");
                window.history.replaceState({}, document.title, "/");
            } else {
                // Increment visual status bar
                progressPercent = Math.min(progressPercent + 20, 90);
                bar.style.width = `${progressPercent}%`;
                
                if (progressPercent === 45) {
                    title.innerText = "Resolviendo CAPTCHA...";
                    desc.innerText = "Brincando la validación del portal del SAT.";
                } else if (progressPercent === 65) {
                    title.innerText = "Iniciando descarga...";
                    desc.innerText = "Obteniendo el archivo PDF oficial de Hacienda.";
                } else if (progressPercent === 85) {
                    title.innerText = "Guardando en servidor...";
                    desc.innerText = "Almacenando tu PDF de forma segura.";
                }
            }
        } catch(e) {
            console.error(e);
        }
    }, 1200);
}

function downloadResultPdf() {
    if (!currentOrderUuid) return;
    window.location.href = `${API_BASE}/orders/${currentOrderUuid}/download`;
}

function restartFlow() {
    currentOrderUuid = null;
    document.getElementById("user-rfc").value = "";
    document.getElementById("user-ciec").value = "";
    document.getElementById("user-email").value = "";
    switchScreen("step-success", "step-form");
}

function switchScreen(fromId, toId) {
    document.getElementById(fromId).classList.add("hidden");
    document.getElementById(toId).classList.remove("hidden");
}
