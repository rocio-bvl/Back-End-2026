/* ==========================================================================================================
   Animaciones del SGR (static/js/animaciones.js). JavaScript puro, sin librerías: se carga al final de
   templates/base.html, después de Bootstrap, en todas las páginas.
   0. Ubica la barra de pestañas fija justo bajo la barra roja superior.
   1. Aparición al desplazar: tarjetas, tablas y alertas entran cuando llegan a la pantalla.
   2. Conteo: los números de las tarjetas de avance suben de 0 a su valor.
   Si la persona pidió "reducir movimiento" en su sistema, no hace nada (ver también sgr-moderno.css).
   ========================================================================================================== */
(function () {
    'use strict';

    // 0. Alto de la barra roja superior ----------------------------------------------------------------------
    // La barra de pestañas se fija justo debajo de ella (sgr-moderno.css, top: var(--sgr-alto-navbar)).
    // ResizeObserver vuelve a medir cuando cambia de alto (por ejemplo, al abrir su menú en celular).
    // Va antes del chequeo de movimiento porque no es una animación: ubica la barra.
    var barraRoja = document.querySelector('nav.navbar.sticky-top');
    if (barraRoja) {
        var medir = function () {
            document.documentElement.style.setProperty('--sgr-alto-navbar', barraRoja.offsetHeight + 'px');
        };
        medir();
        if ('ResizeObserver' in window) {
            new ResizeObserver(medir).observe(barraRoja);
        }
    }

    var reducirMovimiento = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reducirMovimiento) {
        return;
    }

    // 1. Aparición al desplazar ------------------------------------------------------------------------------
    // IntersectionObserver avisa cuando un elemento entra en la pantalla (sin revisar la posición en cada
    // evento de scroll, que es más costoso). Navegadores muy antiguos sin esta API ven todo sin animación.
    if ('IntersectionObserver' in window) {
        var elementos = document.querySelectorAll('main .card, main .tarjeta-tabla, main .alert');

        var observador = new IntersectionObserver(function (entradas) {
            entradas.forEach(function (entrada) {
                if (!entrada.isIntersecting) {
                    return;
                }
                var elemento = entrada.target;
                elemento.classList.add('sgr-visible');
                observador.unobserve(elemento);  // cada elemento se anima una sola vez
                // Terminada la entrada se quitan las clases: así el retraso escalonado no frena después la
                // elevación al pasar el mouse ni las transiciones propias de la tarjeta
                elemento.addEventListener('transitionend', function limpiar(evento) {
                    if (evento.propertyName !== 'transform') {
                        return;
                    }
                    elemento.classList.remove('sgr-revelar', 'sgr-visible');
                    elemento.style.removeProperty('--sgr-retraso');
                    elemento.removeEventListener('transitionend', limpiar);
                });
            });
        }, { threshold: 0.08 });  // basta con que se vea el 8% del elemento

        elementos.forEach(function (elemento, indice) {
            elemento.classList.add('sgr-revelar');
            // Escalonado: 0, 70, 140 y 210 ms, y se repite (las tarjetas van de a 4 por fila)
            elemento.style.setProperty('--sgr-retraso', (indice % 4) * 70 + 'ms');
            observador.observe(elemento);
        });
    }

    // 2. Conteo de los números de las tarjetas ---------------------------------------------------------------
    // Solo los <h3> de tarjetas cuyo texto es únicamente un número, con o sin %: "4", "52,2%", "0,2%".
    // Textos como "Rojo" o "48 / 52,2%" no calzan con la expresión regular y no se tocan.
    var patron = /^(\d+(?:[.,]\d+)?)(%?)$/;
    var duracion = 600;  // milisegundos

    document.querySelectorAll('main .card h3').forEach(function (titulo) {
        var partes = titulo.textContent.trim().match(patron);
        if (!partes) {
            return;
        }
        var texto = partes[1];
        var sufijo = partes[2];
        var usaComa = texto.indexOf(',') !== -1;              // Django muestra 52,2 (coma decimal chilena)
        var valorFinal = parseFloat(texto.replace(',', '.'));
        var decimales = (texto.split(/[.,]/)[1] || '').length;
        var inicio = performance.now();

        function paso(ahora) {
            var progreso = Math.min((ahora - inicio) / duracion, 1);
            var suavizado = 1 - Math.pow(1 - progreso, 3);   // ease-out cúbico: rápido al inicio, frena al final
            var valor = (valorFinal * suavizado).toFixed(decimales);
            titulo.textContent = (usaComa ? valor.replace('.', ',') : valor) + sufijo;
            if (progreso < 1) {
                requestAnimationFrame(paso);                  // siguiente cuadro, sincronizado con la pantalla
            }
        }
        requestAnimationFrame(paso);
    });
})();

/* Etiquetas de columna para el celular: bajo 768 px cada fila de una tabla SGR se ve como tarjeta y cada dato
   muestra arriba el nombre de su columna (CSS: td[data-cell]::before en sgr-moderno.css). Si una celda no trae
   data-cell en la plantilla, se toma del encabezado de su columna. Solo agrega un atributo: no cambia datos. */
(function () {
    document.querySelectorAll('table.tabla-sgr').forEach(function (tabla) {
        var titulos = [];
        tabla.querySelectorAll('thead tr:last-child th').forEach(function (th) {
            var span = parseInt(th.getAttribute('colspan') || '1', 10);
            for (var i = 0; i < span; i++) { titulos.push(th.textContent.trim()); }
        });
        if (!titulos.length) { return; }
        tabla.querySelectorAll('tbody tr').forEach(function (fila) {
            var columna = 0;
            Array.prototype.forEach.call(fila.children, function (celda) {
                if (!celda.hasAttribute('data-cell') && titulos[columna] && !celda.hasAttribute('colspan')) {
                    celda.setAttribute('data-cell', titulos[columna]);
                }
                columna += parseInt(celda.getAttribute('colspan') || '1', 10);
            });
        });
    });
})();
