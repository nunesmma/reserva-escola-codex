const currentUser = window.APP_USER || null;
const appConfig = window.APP_CONFIG || {};
const appTimezone = appConfig.timezone || "America/Sao_Paulo";
const areaSelect = document.getElementById("area");
const dataInput = document.getElementById("data");
const inicioInput = document.getElementById("inicio");
const fimInput = document.getElementById("fim");
const duracaoEl = document.getElementById("duracao");
const listaEl = document.getElementById("lista");
const feedbackEl = document.getElementById("feedback");
const totalEl = document.getElementById("total");
const hojeEl = document.getElementById("hoje");
const topEl = document.getElementById("top");
const formEl = document.getElementById("reserva-form");
const submitButton = document.getElementById("submit-button");
const searchUserInput = document.getElementById("search-user");
const adminFeedbackEl = document.getElementById("admin-feedback");
const usuariosListaEl = document.getElementById("usuarios-lista");
const themeToggleButtons = document.querySelectorAll("[data-theme-toggle]");
const calendarToggleButton = document.querySelector("[data-calendar-toggle]");
const calendarCard = document.querySelector(".calendar-card");
let reservasCache = [];
let usuariosCache = [];

function atualizarTextoTema(theme) {
    themeToggleButtons.forEach((botao) => {
        botao.textContent = theme === "dark" ? "Modo claro" : "Modo escuro";
    });
}

function aplicarTema(theme) {
    document.body.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
    atualizarTextoTema(theme);
}

function alternarTema() {
    const temaAtual = document.body.getAttribute("data-theme") || "light";
    aplicarTema(temaAtual === "dark" ? "light" : "dark");
}

function iniciarTema() {
    const temaSalvo = localStorage.getItem("theme");
    const prefereEscuro = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    aplicarTema(temaSalvo || (prefereEscuro ? "dark" : "light"));
    themeToggleButtons.forEach((botao) => botao.addEventListener("click", alternarTema));
}

function atualizarEstadoCalendario() {
    if (!calendarToggleButton || !calendarCard) return;
    const mobile = window.innerWidth <= 640;

    if (!mobile) {
        calendarCard.hidden = false;
        calendarToggleButton.hidden = true;
        calendarToggleButton.setAttribute("aria-expanded", "true");
        calendarToggleButton.textContent = "Ocultar calendário";
        return;
    }

    calendarToggleButton.hidden = false;
    const recolhido = document.body.getAttribute("data-calendar-collapsed") === "true";
    calendarCard.hidden = recolhido;
    calendarToggleButton.setAttribute("aria-expanded", String(!recolhido));
    calendarToggleButton.textContent = recolhido ? "Mostrar calendário" : "Ocultar calendário";
}

function alternarCalendario() {
    if (!calendarCard) return;
    const recolhido = document.body.getAttribute("data-calendar-collapsed") === "true";
    document.body.setAttribute("data-calendar-collapsed", recolhido ? "false" : "true");
    atualizarEstadoCalendario();
}

function mostrarFeedback(mensagem, tipo = "info") {
    if (!feedbackEl) return;
    feedbackEl.textContent = mensagem;
    feedbackEl.className = `feedback feedback--${tipo}`;
}

function limparFeedback() {
    if (!feedbackEl) return;
    feedbackEl.textContent = "";
    feedbackEl.className = "feedback";
}

function mostrarAdminFeedback(mensagem, tipo = "info") {
    if (!adminFeedbackEl) return;
    adminFeedbackEl.textContent = mensagem;
    adminFeedbackEl.className = `feedback feedback--${tipo}`;
}

function calcularDuracao() {
    if (!duracaoEl) return;
    if (!inicioInput.value || !fimInput.value) {
        duracaoEl.textContent = "Defina um horário para ver a duração.";
        duracaoEl.classList.remove("duration--error");
        return;
    }

    const [horaInicio, minutoInicio] = inicioInput.value.split(":").map(Number);
    const [horaFim, minutoFim] = fimInput.value.split(":").map(Number);
    const diferenca = (horaFim * 60 + minutoFim) - (horaInicio * 60 + minutoInicio);

    if (diferenca <= 0) {
        duracaoEl.textContent = "Horário inválido. O fim precisa ser maior que o início.";
        duracaoEl.classList.add("duration--error");
        return;
    }

    const horas = Math.floor(diferenca / 60);
    const minutos = diferenca % 60;
    duracaoEl.textContent = `Duração: ${horas}h ${minutos}min`;
    duracaoEl.classList.remove("duration--error");
}

function formatarData(dataIso) {
    if (!dataIso) return "-";
    const [ano, mes, dia] = dataIso.split("-");
    return `${dia}/${mes}/${ano}`;
}

function getHojeNoTimezone() {
    const partes = new Intl.DateTimeFormat("en-CA", {
        timeZone: appTimezone,
        year: "numeric",
        month: "2-digit",
        day: "2-digit"
    }).formatToParts(new Date());

    const mapa = Object.fromEntries(
        partes.filter((parte) => parte.type !== "literal").map((parte) => [parte.type, parte.value])
    );

    return `${mapa.year}-${mapa.month}-${mapa.day}`;
}

function definirDataMinima() {
    dataInput.min = getHojeNoTimezone();
}

function horarioJaPassou(data, hora) {
    if (!data || !hora) return false;
    if (data > getHojeNoTimezone()) return false;
    if (data < getHojeNoTimezone()) return true;

    const agoraNoTimezone = new Intl.DateTimeFormat("en-GB", {
        timeZone: appTimezone,
        hour: "2-digit",
        minute: "2-digit",
        hour12: false
    }).format(new Date());

    return hora <= agoraNoTimezone;
}

function atualizarResumo(reservas) {
    const hoje = getHojeNoTimezone();
    const contagemAreas = {};
    let reservasHoje = 0;

    reservas.forEach((reserva) => {
        contagemAreas[reserva.area] = (contagemAreas[reserva.area] || 0) + 1;
        if (reserva.data === hoje) reservasHoje += 1;
    });

    totalEl.textContent = reservas.length;
    hojeEl.textContent = reservasHoje;
    const areaTop = Object.entries(contagemAreas).sort((a, b) => b[1] - a[1])[0];
    topEl.textContent = areaTop ? areaTop[0] : "-";
}

function criarItemReserva(reserva) {
    const item = document.createElement("article");
    item.className = "reserva-item";
    const podeExcluir = currentUser && (currentUser.perfil === "admin" || currentUser.id === reserva.user_id);
    const perfilLabel = reserva.perfil ? ` • ${reserva.perfil}` : "";

    item.innerHTML = `
        <div class="reserva-item__content">
            <strong>${reserva.area}</strong>
            <p>${formatarData(reserva.data)} - ${reserva.inicio} às ${reserva.fim}</p>
            <span>Reservado por ${reserva.nome || "Usuário removido"}${perfilLabel}</span>
        </div>
    `;

    if (podeExcluir) {
        const botaoExcluir = document.createElement("button");
        botaoExcluir.type = "button";
        botaoExcluir.className = "delete";
        botaoExcluir.textContent = "Excluir";
        botaoExcluir.addEventListener("click", () => excluirReserva(reserva.id));
        item.appendChild(botaoExcluir);
    }

    return item;
}

function renderizarReservas(reservas) {
    listaEl.innerHTML = "";
    if (!reservas.length) {
        listaEl.innerHTML = '<p class="empty-state">Nenhuma reserva encontrada.</p>';
        return;
    }
    reservas.forEach((reserva) => listaEl.appendChild(criarItemReserva(reserva)));
}

function criarItemUsuario(usuario) {
    const item = document.createElement("article");
    item.className = "usuario-item";
    const criadoEm = usuario.criado_em ? usuario.criado_em.replace("T", " ").slice(0, 16) : "-";

    item.innerHTML = `
        <div class="usuario-item__content">
            <strong>${usuario.nome}</strong>
            <p>${usuario.email}</p>
            <span>${usuario.perfil} • criado em ${criadoEm}</span>
        </div>
    `;

    if (!usuario.is_current_user) {
        const botaoExcluir = document.createElement("button");
        botaoExcluir.type = "button";
        botaoExcluir.className = "delete";
        botaoExcluir.textContent = "Excluir cadastro";
        botaoExcluir.addEventListener("click", () => excluirUsuario(usuario.id));
        item.appendChild(botaoExcluir);
    }

    return item;
}

function renderizarUsuarios(usuarios) {
    if (!usuariosListaEl) return;
    usuariosListaEl.innerHTML = "";
    if (!usuarios.length) {
        usuariosListaEl.innerHTML = '<p class="empty-state">Nenhum usuário encontrado.</p>';
        return;
    }
    usuarios.forEach((usuario) => usuariosListaEl.appendChild(criarItemUsuario(usuario)));
}

function aplicarFiltroReservas() {
    const termo = (searchUserInput.value || "").trim().toLowerCase();
    const reservasFiltradas = termo
        ? reservasCache.filter((reserva) => (reserva.nome || "").toLowerCase().includes(termo))
        : reservasCache;
    renderizarReservas(reservasFiltradas);
}

async function carregarReservas() {
    const resposta = await fetch("/reservas");
    if (!resposta.ok) {
        mostrarFeedback("Não foi possível carregar as reservas.", "error");
        return;
    }

    reservasCache = await resposta.json();
    atualizarResumo(reservasCache);
    aplicarFiltroReservas();
}

async function carregarUsuarios() {
    if (!usuariosListaEl || !currentUser || currentUser.perfil !== "admin") return;
    const resposta = await fetch("/usuarios");
    if (!resposta.ok) {
        mostrarAdminFeedback("Não foi possível carregar os usuários.", "error");
        return;
    }
    usuariosCache = await resposta.json();
    renderizarUsuarios(usuariosCache);
}

async function excluirReserva(id) {
    const resposta = await fetch(`/excluir/${id}`, { method: "DELETE" });
    const resultado = await resposta.json();
    if (!resposta.ok) {
        mostrarFeedback(resultado.msg || "Não foi possível excluir a reserva.", "error");
        return;
    }
    mostrarFeedback(resultado.msg, "success");
    await carregarReservas();
}

async function excluirUsuario(id) {
    const resposta = await fetch(`/usuarios/${id}`, { method: "DELETE" });
    const resultado = await resposta.json();
    if (!resposta.ok) {
        mostrarAdminFeedback(resultado.msg || "Não foi possível excluir o cadastro.", "error");
        return;
    }
    mostrarAdminFeedback(resultado.msg, "success");
    await carregarUsuarios();
    await carregarReservas();
}

async function reservar(event) {
    event.preventDefault();
    limparFeedback();
    calcularDuracao();

    if (horarioJaPassou(dataInput.value, inicioInput.value)) {
        mostrarFeedback("Não é permitido reservar datas ou horários que já passaram.", "error");
        return;
    }

    submitButton.disabled = true;
    submitButton.textContent = "Salvando...";

    try {
        const resposta = await fetch("/reservar", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                area: areaSelect.value,
                data: dataInput.value,
                inicio: inicioInput.value,
                fim: fimInput.value
            })
        });

        const resultado = await resposta.json();
        if (!resposta.ok) {
            mostrarFeedback(resultado.msg || "Não foi possível concluir a reserva.", "error");
            return;
        }

        mostrarFeedback(resultado.msg, "success");
        formEl.reset();
        duracaoEl.textContent = "Defina um horário para ver a duração.";
        duracaoEl.classList.remove("duration--error");
        definirDataMinima();
        await carregarReservas();
    } catch (erro) {
        mostrarFeedback("Erro de conexão ao tentar salvar a reserva.", "error");
    } finally {
        submitButton.disabled = false;
        submitButton.textContent = "Reservar horário";
    }
}

if (formEl) {
    inicioInput.addEventListener("input", calcularDuracao);
    fimInput.addEventListener("input", calcularDuracao);
    formEl.addEventListener("submit", reservar);
    searchUserInput.addEventListener("input", aplicarFiltroReservas);
    definirDataMinima();
    carregarReservas();
    carregarUsuarios();
}

iniciarTema();
if (calendarToggleButton) {
    calendarToggleButton.addEventListener("click", alternarCalendario);
    window.addEventListener("resize", atualizarEstadoCalendario);
    if (window.innerWidth <= 640) {
        document.body.setAttribute("data-calendar-collapsed", "true");
    }
    atualizarEstadoCalendario();
}
