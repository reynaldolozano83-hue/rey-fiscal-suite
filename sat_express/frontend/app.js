// Trámite Express Frontend Logic
const API_BASE = window.location.origin + "/api";

let currentOrderUuid = null;
let currentIdentifier = ""; // Stores RFC or CURP
let currentDocType = "csf";
let currentPrice = 10;
let currentServiceMode = 'diy';

window.onload = async () => {
    const urlParams = new URLSearchParams(window.location.search);
    const status = urlParams.get("status");
    const orderUuid = urlParams.get("order_uuid");
    
    if (status === "success" && orderUuid) {
        currentOrderUuid = orderUuid;
        switchScreen("step-form", "step-progress");
        try {
            const res = await fetch(`${API_BASE}/orders/${orderUuid}/trigger-fulfillment`);
            const data = await res.json();
            startPollingStatus();
        } catch(e) {
            console.error(e);
            alert("Error al procesar el pago con el servidor.");
            switchScreen("step-progress", "step-form");
        }
    } else if (status === "cancel") {
        alert("El pago fue cancelado. Inténtalo de nuevo.");
        window.history.replaceState({}, document.title, "/");
    }
};


function toggleServiceMode(mode) {
    currentServiceMode = mode;
    currentPrice = (mode === 'diy') ? 10 : 50;
    
    // Toggle active borders in UI
    const labelDiy = document.getElementById("label-mode-diy");
    const labelFull = document.getElementById("label-mode-full");
    
    if (mode === 'diy') {
        labelDiy.style.border = "2px solid #10b981";
        labelFull.style.border = "1px solid #e2e8f0";
    } else {
        labelDiy.style.border = "1px solid #e2e8f0";
        labelFull.style.border = "2px solid #10b981";
    }
    
    const submitBtn = document.getElementById("btn-submit-order");
    submitBtn.innerText = `Continuar al Pago ($${currentPrice}.00 MXN)`;
}

function toggleDocType(type) {
    currentDocType = type;
    
    // Reset active classes
    const labels = ["csf", "opinion", "nss", "curp"];
    labels.forEach(l => {
        const lbl = document.getElementById(`label-${l}`);
        if (l === type) {
            lbl.classList.add("active");
        } else {
            lbl.classList.remove("active");
        }
    });

    // Toggle fields based on type
    const satFields = document.getElementById("sat-fields");
    const curpFields = document.getElementById("curp-fields");
    const submitBtn = document.getElementById("btn-submit-order");
    
    if (type === 'csf' || type === 'opinion') {
        satFields.classList.remove("hidden");
        curpFields.classList.add("hidden");
        
    } else if (type === 'nss') {
        satFields.classList.add("hidden");
        curpFields.classList.remove("hidden");
        
    } else if (type === 'curp') {
        satFields.classList.add("hidden");
        curpFields.classList.remove("hidden");
        
    }

    submitBtn.innerText = `Continuar al Pago ($${currentPrice}.00 MXN)`;
}

async function startOrder() {
    const delivery = document.getElementById("user-delivery").value.trim();
    
    if (!delivery) {
        alert("Por favor ingresa tu celular o correo electrónico para enviarte tu PDF.");
        return;
    }

    let payload = {
        doc_type: currentDocType,
        delivery: delivery,
        service_mode: currentServiceMode
    };

    if (currentDocType === 'csf' || currentDocType === 'opinion') {
        const rfc = document.getElementById("user-rfc").value.trim();
        const ciec = document.getElementById("user-ciec").value.trim();
        
        if (!rfc || rfc.length < 12) {
            alert("Por favor ingresa un RFC válido de 12 o 13 caracteres.");
            return;
        }
        if (!ciec) {
            alert("Por favor ingresa tu contraseña SAT (CIEC).");
            return;
        }
        
        currentIdentifier = rfc.toUpperCase();
        payload.rfc = currentIdentifier;
        payload.ciec = ciec;
    } else {
        const curp = document.getElementById("user-curp").value.trim();
        if (!curp || curp.length < 18) {
            alert("Por favor ingresa tu CURP oficial de 18 caracteres.");
            return;
        }
        currentIdentifier = curp.toUpperCase();
        payload.curp = currentIdentifier;
    }
    
    try {
        const res = await fetch(`${API_BASE}/orders`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        
        if (data.status === 'success') {
            currentOrderUuid = data.order_uuid;
            
            // Set payment info
            let docName = "Constancia SAT";
            if (currentDocType === 'opinion') docName = "Opinión SAT 32D";
            else if (currentDocType === 'nss') docName = "Número de Seguro Social (NSS)";
            else if (currentDocType === 'curp') docName = "CURP Oficial";

            document.getElementById("pay-concept").innerText = docName;
            document.getElementById("pay-amount").innerText = `$${currentPrice}.00 MXN`;
            document.getElementById("pay-identifier").innerText = currentIdentifier;
            document.getElementById("btn-pay-simulate").innerText = `Simular Pago Exitoso ($${currentPrice}.00)`;
            
            switchScreen("step-form", "step-payment");
        } else {
            alert("Error al iniciar el trámite. Revisa tus datos.");
        }
    } catch(e) {
        console.error(e);
        alert("Error de conexión con el servidor.");
    }
}

function cancelPayment() {
    switchScreen("step-payment", "step-form");
}

async function triggerPayment() {
    if (!currentOrderUuid) return;
    
    switchScreen("step-payment", "step-progress");
    
    try {
        const res = await fetch(`${API_BASE}/orders/${currentOrderUuid}/pay-simulate`, { method: "POST" });
        const data = await res.json();
        if (data.status === 'paid') {
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
                desc.innerText = "Documento obtenido con éxito.";
                
                setTimeout(() => {
                    document.getElementById("success-identifier").innerText = currentIdentifier || "Consultado";
                    
                    let docName = "Constancia SAT";
                    if (currentDocType === 'opinion') docName = "Opinión SAT 32D";
                    else if (currentDocType === 'nss') docName = "Número de Seguro Social (NSS)";
                    else if (currentDocType === 'curp') docName = "CURP Oficial";
                    document.getElementById("success-doc").innerText = docName;
                    
                    switchScreen("step-progress", "step-success");
                    window.history.replaceState({}, document.title, "/");
                }, 800);
            } else if (data.download_status === 'failed') {
                clearInterval(pollInterval);
                alert("Error de consulta: " + (data.error_message || "No se pudo obtener el documento. Verifica los datos de acceso proporcionados."));
                switchScreen("step-progress", "step-form");
                window.history.replaceState({}, document.title, "/");
            } else {
                progressPercent = Math.min(progressPercent + 20, 90);
                bar.style.width = `${progressPercent}%`;
                
                if (progressPercent === 45) {
                    title.innerText = "Conectando al Servidor Oficial...";
                    desc.innerText = "Iniciando sesión segura en las dependencias federales.";
                } else if (progressPercent === 65) {
                    title.innerText = "Validando identidad...";
                    desc.innerText = "Resolviendo la autenticación y CAPTCHA del portal.";
                } else if (progressPercent === 85) {
                    title.innerText = "Generando PDF oficial...";
                    desc.innerText = "Obteniendo los archivos encriptados en formato PDF.";
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
    document.getElementById("user-curp").value = "";
    document.getElementById("user-delivery").value = "";
    switchScreen("step-success", "step-form");
}

function switchScreen(fromId, toId) {
    document.getElementById(fromId).classList.add("hidden");
    document.getElementById(toId).classList.remove("hidden");
}
