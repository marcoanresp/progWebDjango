// Tema claro/escuro do site (Bootstrap 5.3 usa o atributo data-bs-theme no <html>).
// A escolha fica salva no navegador; na primeira visita segue o tema do sistema operacional.
(function () {
    const CHAVE = "edumarket-tema";

    function temaInicial() {
        try {
            const salvo = localStorage.getItem(CHAVE);
            if (salvo) return salvo;
        } catch (e) { /* localStorage indisponível */ }
        return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }

    function aplicar(tema) {
        document.documentElement.setAttribute("data-bs-theme", tema);
        const icone = document.querySelector("#botaoTema i");
        if (icone) icone.className = tema === "dark" ? "fas fa-sun" : "fas fa-moon";
    }

    aplicar(temaInicial());

    document.addEventListener("DOMContentLoaded", function () {
        aplicar(document.documentElement.getAttribute("data-bs-theme"));
        const botao = document.getElementById("botaoTema");
        if (!botao) return;
        botao.addEventListener("click", function () {
            const novo = document.documentElement.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
            aplicar(novo);
            try { localStorage.setItem(CHAVE, novo); } catch (e) { /* ignora */ }
        });
    });
})();
