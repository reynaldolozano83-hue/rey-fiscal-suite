// Trámite Express Frontend Logic
const API_BASE = window.location.origin + "/api";

let currentOrderUuid = null;
let currentIdentifier = ""; 
let currentDocType = "csf";
let currentPrice = 10;
let currentServiceMode = "diy";

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
    const labels = ["csf", "opinion", "nss", "curp", "acta", "penales", "cfe", "citas"];
    labels.forEach(l => {
        const lbl = document.getElementById(`label-${l}`);
        if (lbl) {
            if (l === type) {
                lbl.classList.add("active");
            } else {
                lbl.classList.remove("active");
            }
        }
    });

    // Toggle fields based on type
    const satFields = document.getElementById("sat-fields");
    const curpContainer = document.getElementById("curp-container");
    const utilityFields = document.getElementById("utility-fields");
    
    // Hide all first
    satFields.classList.add("hidden");
    curpContainer.classList.add("hidden");
    utilityFields.classList.add("hidden");

    if (type === 'csf' || type === 'opinion') {
        satFields.classList.remove("hidden");
    } else if (type === 'cfe') {
        utilityFields.classList.remove("hidden");
    } else {
        // CURP, NSS, Acta, Penales, Citas
        curpContainer.classList.remove("hidden");
    }
}

function toggleNoCurpFields() {
    const chk = document.getElementById("chk-no-curp");
    const curpInput = document.getElementById("field-curp-input");
    const personalFields = document.getElementById("personal-fields");
    
    if (chk.checked) {
        curpInput.classList.add("hidden");
        personalFields.classList.remove("hidden");
    } else {
        curpInput.classList.remove("hidden");
        personalFields.classList.add("hidden");
    }
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

    // Extract dynamic identifier based on visible fields
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
    } else if (currentDocType === 'cfe') {
        const utility = document.getElementById("user-utility").value.trim();
        if (!utility || utility.length < 10) {
            alert("Por favor ingresa tu Número de Servicio de 12 dígitos.");
            return;
        }
        currentIdentifier = utility;
        payload.curp = currentIdentifier; // backend expects identifier here
    } else {
        const isManual = document.getElementById("chk-no-curp").checked;
        if (isManual) {
            const name = document.getElementById("user-name").value.trim();
            const paterno = document.getElementById("user-paterno").value.trim();
            const materno = document.getElementById("user-materno").value.trim();
            const birthdate = document.getElementById("user-birthdate").value;
            const gender = document.getElementById("user-gender").value;
            const state = document.getElementById("user-state").value;
            
            if (!name || !paterno || !birthdate) {
                alert("Por favor ingresa Nombre, Apellido Paterno y Fecha de Nacimiento.");
                return;
            }
            
            // Build pseudo identifier from names for tracking
            currentIdentifier = `${paterno.substring(0,2)}${materno.substring(0,1)}${name.substring(0,1)}${birthdate.replace(/-/g,'').substring(2)}`.toUpperCase();
            payload.curp = currentIdentifier;
            payload.ciec = `DATOS: ${name} ${paterno} ${materno} | ${birthdate} | ${gender} | ${state}`;
        } else {
            const curp = document.getElementById("user-curp").value.trim();
            if (!curp || curp.length < 18) {
                alert("Por favor ingresa tu CURP oficial de 18 caracteres.");
                return;
            }
            currentIdentifier = curp.toUpperCase();
            payload.curp = currentIdentifier;
        }
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
            
            const docNames = {
                'csf': 'Constancia SAT',
                'opinion': 'Opinión SAT 32D',
                'nss': 'Número Seguro IMSS',
                'curp': 'CURP Oficial',
                'acta': 'Acta de Nacimiento',
                'penales': 'Antecedentes Penales',
                'cfe': 'Recibo CFE / Luz',
                'citas': 'Cita Oficial'
            };

            document.getElementById("pay-concept").innerText = docNames[currentDocType] || "Trámite Express";
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
    
    // 1. If DIY Mode ($10): Redirect INSTANTLY to the copy-paste assistant
    if (currentServiceMode === 'diy') {
        try {
            await fetch(`${API_BASE}/orders/${currentOrderUuid}/trigger-fulfillment`, { method: "GET" });
            alert("¡Pago aprobado! Redirigiendo a tu Asistente de Descarga...");
            window.location.href = `admin.html?search=${encodeURIComponent(currentIdentifier)}`;
        } catch(e) {
            console.error(e);
            alert("Error de conexión.");
        }
        return;
    }
    
    // 2. If Full Mode ($50): Show the pending receipt screen instantly (no spinner wait)
    switchScreen("step-payment", "step-progress");
    try {
        await fetch(`${API_BASE}/orders/${currentOrderUuid}/trigger-fulfillment`, { method: "GET" });
        
        document.getElementById("success-identifier").innerText = currentIdentifier;
        document.getElementById("success-doc").innerText = document.getElementById("pay-concept").innerText;
        document.getElementById("success-status").innerText = "PENDIENTE";
        document.getElementById("success-message").innerText = "Nuestro equipo procesará tu documento en 5 minutos y te lo enviará por WhatsApp.";
        
        // Hide download button since we process it manually
        document.getElementById("btn-success-download").classList.add("hidden");
        
        setTimeout(() => {
            switchScreen("step-progress", "step-success");
        }, 1000);
    } catch(e) {
        console.error(e);
        switchScreen("step-progress", "step-payment");
    }
}

// Polling removed since we use direct client redirection and manual processing
function startPollingStatus() {}

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
    document.getElementById("user-utility").value = "";
    document.getElementById("chk-no-curp").checked = false;
    toggleNoCurpFields();
    switchScreen("step-success", "step-form");
}

function switchScreen(fromId, toId) {
    document.getElementById(fromId).classList.add("hidden");
    document.getElementById(toId).classList.remove("hidden");
}
