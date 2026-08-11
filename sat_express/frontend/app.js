// SAT Express Frontend Logic
const API_BASE = window.location.origin + "/api";

let currentOrderUuid = null;
let currentRfc = "";
let currentDocType = "csf";

function toggleDocType(type) {
    currentDocType = type;
    const csfLabel = document.getElementById("label-csf");
    const opinionLabel = document.getElementById("label-opinion");
    
    if (type === 'csf') {
        csfLabel.className = "border-2 border-blue-900 bg-blue-50/20 rounded-xl p-3 flex flex-col items-center justify-center cursor-pointer transition text-center select-option";
        opinionLabel.className = "border border-slate-200 hover:border-blue-900 rounded-xl p-3 flex flex-col items-center justify-center cursor-pointer transition text-center select-option";
    } else {
        opinionLabel.className = "border-2 border-blue-900 bg-blue-50/20 rounded-xl p-3 flex flex-col items-center justify-center cursor-pointer transition text-center select-option";
        csfLabel.className = "border border-slate-200 hover:border-blue-900 rounded-xl p-3 flex flex-col items-center justify-center cursor-pointer transition text-center select-option";
    }
}

async function startOrder() {
    const rfc = document.getElementById("user-rfc").value.trim();
    const ciec = document.getElementById("user-ciec").value.trim();
    const email = document.getElementById("user-email").value.trim();
    
    if (!rfc || rfc.length < 12) {
        alert("Por favor ingresa un RFC valido de 12 o 13 caracteres.");
        return;
    }
    if (!ciec) {
        alert("Por favor ingresa tu contraseña SAT (CIEC).");
        return;
    }
    if (!email || !email.includes("@")) {
        alert("Por favor ingresa un correo electronico valido para enviar tu PDF.");
        return;
    }
    
    currentRfc = rfc.toUpperCase();
    
    // Create the order on the backend
    try {
        const res = await fetch(`${API_BASE}/orders`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rfc: rfc, ciec: ciec, email: email, doc_type: currentDocType })
        });
        const data = await res.json();
        
        if (data.status === 'success') {
            currentOrderUuid = data.order_uuid;
            
            // Set payment info
            document.getElementById("pay-concept").innerText = currentDocType === 'csf' ? "Descarga Constancia SAT" : "Opinión de Cumplimiento 32-D";
            document.getElementById("pay-rfc").innerText = currentRfc;
            
            // Switch screen
            switchScreen("step-form", "step-payment");
        } else {
            alert("Error al iniciar el tramite. Revisa tus datos.");
        }
    } catch(e) {
        console.error(e);
        alert("Error de conexion con el servidor.");
    }
}

function cancelPayment() {
    switchScreen("step-payment", "step-form");
}

async function triggerPayment() {
    if (!currentOrderUuid) return;
    
    switchScreen("step-payment", "step-progress");
    
    // Call simulated payment endpoint on backend
    try {
        const res = await fetch(`${API_BASE}/orders/${currentOrderUuid}/pay-simulate`, { method: "POST" });
        const data = await res.json();
        
        if (data.status === 'paid') {
            // Start polling the SAT download progress
            startPollingStatus();
        } else {
            alert("Error al procesar el pago.");
            switchScreen("step-progress", "step-payment");
        }
    } catch(e) {
        console.error(e);
        switchScreen("step-progress", "step-payment");
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
                    document.getElementById("success-rfc").innerText = currentRfc;
                    document.getElementById("success-doc").innerText = currentDocType === 'csf' ? "Constancia de Situación Fiscal" : "Opinión de Cumplimiento 32-D";
                    
                    switchScreen("step-progress", "step-success");
                }, 800);
            } else if (data.download_status === 'failed') {
                clearInterval(pollInterval);
                alert("Error de consulta SAT: " + (data.error_message || "La contraseña o el RFC son incorrectos. Por favor, verifica tus datos de acceso en el SAT."));
                switchScreen("step-progress", "step-form");
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
